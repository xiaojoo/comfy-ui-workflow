"""The three things a person may set on a workflow row: name, note, cover.

Everything here is an override on top of the registry in templates.py, which stays the
source of the graph, the fields and the defaults. An unset column falls back to that
default, so dropping a custom name in the drawer cannot leave the card blank.

The cover is the uploaded picture itself, copied into work/covers -- not a reference to
wherever the file came from. A card that breaks because a file moved or was deleted three
weeks later is not a cover.
"""

from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select

from . import comfy, templates
from .config import WORK
from .db import Session
from .models import Task, WorkflowMeta

COVERS = WORK / "covers"
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
MAX_BYTES = 8 * 1024 * 1024
# The magic number decides, not the extension in the filename: what comes back out of
# GET /covers is rendered as an image by the browser, and a name is whatever whoever saved
# the file typed.
MAGIC = ((b"\x89PNG\r\n\x1a\n", ".png"), (b"\xff\xd8\xff", ".jpg"), (b"GIF8", ".gif"),
         (b"RIFF", ".webp"))
# How far back to look for the automatic cover. The result track pages through the same
# number of rows, so this is the same ceiling, stated where it is used.
SCAN = 200
MAX_NAME, MAX_DESC = 60, 400


def _tpl(tpl_id):
    tpl = templates.BY_ID.get(tpl_id)
    if tpl is None:
        raise HTTPException(422, f"没有这条工作流：{tpl_id!r}")
    return tpl


def _get(tpl_id):
    with Session() as s:
        return s.get(WorkflowMeta, tpl_id)


def save(tpl_id, name=None, desc=None):
    """Set the label and the note. Empty strings clear back to the registry's own copy."""
    _tpl(tpl_id)
    name, desc = (name or "").strip(), (desc or "").strip()
    if len(name) > MAX_NAME:
        raise HTTPException(422, f"名称最多 {MAX_NAME} 字")
    if len(desc) > MAX_DESC:
        raise HTTPException(422, f"说明最多 {MAX_DESC} 字")
    with Session() as s:
        row = s.get(WorkflowMeta, tpl_id) or WorkflowMeta(template=tpl_id)
        row.name, row.desc = name or None, desc or None
        s.merge(row)
        s.commit()
    return {"template": tpl_id, "name": name, "desc": desc}


def _kind(data):
    for head, ext in MAGIC:
        if data.startswith(head) and (ext != ".webp" or data[8:12] == b"WEBP"):
            return ext
    return None


def set_cover(tpl_id, filename, data):
    """Store the uploaded picture as this row's cover, replacing whatever was there."""
    _tpl(tpl_id)
    if len(data) > MAX_BYTES:
        raise HTTPException(422, f"封面图有 {len(data) // 1024} KB，上限 8 MB，先压一下")
    ext = _kind(data)
    if ext is None:
        raise HTTPException(422, "封面要的是 PNG / JPEG / WebP / GIF 图片")
    COVERS.mkdir(parents=True, exist_ok=True)
    drop(tpl_id)
    dst = COVERS / f"{tpl_id}{ext}"
    dst.write_bytes(data)
    with Session() as s:
        row = s.get(WorkflowMeta, tpl_id) or WorkflowMeta(template=tpl_id)
        row.cover = dst.name
        s.merge(row)
        s.commit()
    return {"template": tpl_id, "cover": cover_url(tpl_id, dst.name), "from": filename,
            "bytes": len(data), "type": ext[1:]}


def drop(tpl_id):
    """Delete this row's stored cover file, if it has one. Used by clear and by a replace."""
    row = _get(tpl_id)
    if row and row.cover:
        (COVERS / row.cover).unlink(missing_ok=True)
    return row


def clear_cover(tpl_id):
    _tpl(tpl_id)
    drop(tpl_id)
    with Session() as s:
        row = s.get(WorkflowMeta, tpl_id)
        if row:
            row.cover = None
            s.merge(row)
            s.commit()
    return {"template": tpl_id, "cover": None}


def cover_path(tpl_id):
    """The stored cover, for GET /covers/{tpl}. None when nothing was pinned."""
    row = _get(tpl_id)
    p = COVERS / row.cover if row and row.cover else None
    return p if p and p.is_file() else None


def cover_url(tpl_id, name=None):
    """Versioned by the stored file's own mtime.

    Not by the row's updated_at: replacing the cover with the same filename leaves that
    column untouched (nothing else about the row changed), and a URL that does not move
    means the browser keeps painting the picture it already has.
    """
    row = _get(tpl_id)
    name = name or (row.cover if row else None)
    if not name:
        return None
    p = COVERS / name
    return f"/covers/{tpl_id}?v={int(p.stat().st_mtime * 1000) if p.is_file() else 0}"


def images(limit=SCAN):
    """(template -> newest picture) over the recent runs, as (url, filename) -- the row's
    label is the file it points at, so the two arrive together."""
    auto = {}
    with Session() as s:
        for t in s.scalars(select(Task).where(Task.state == "done").order_by(Task.id.desc()).limit(limit)):
            if t.template in auto:
                continue
            for o in (t.outputs or []):
                if not o.get("deleted") and Path(o["filename"]).suffix.lower() in IMAGE_EXT:
                    auto[t.template] = (comfy.view_url(o.get("subfolder", ""), o["filename"]),
                                        o["filename"])
                    break
    return auto


def merge(rows):
    """The registry's public rows with the overrides applied, so one call feeds the page."""
    meta = {m.template: m for m in _all()}
    auto = images()
    for r in rows:
        m = meta.get(r["id"])
        if m and m.name:
            r["name"] = r["name_en"] = m.name
        if m and m.desc:
            r["desc"] = r["desc_en"] = m.desc
        # A pinned cover whose file has gone (work/ is disposable) is not a pinned cover:
        # say so here rather than handing the page a URL that 404s into a blank tile.
        pinned = bool(m and m.cover and (COVERS / m.cover).is_file())
        url, name = (cover_url(r["id"], m.cover), m.cover) if pinned else auto.get(r["id"], (None, None))
        r["cover_pinned"] = pinned
        r["cover"], r["cover_name"] = url, name
        r["custom"] = {"name": m.name if m else None, "desc": m.desc if m else None}
    return rows


def _all():
    with Session() as s:
        return list(s.scalars(select(WorkflowMeta)))
