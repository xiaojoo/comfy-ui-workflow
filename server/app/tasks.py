"""Where a generation run is validated, stored and queued -- the only such place.

The drawer's POST /tasks and a canvas step go through `create` so a chain cannot be
refused for a reason the UI has never seen, or accepted past a check the UI enforces.
"""

from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import BaseModel, Field

from . import runner, templates
from .db import Session
from .models import Task


class TaskIn(BaseModel):
    template: str
    prompt: str = Field(default="", max_length=2000)
    params: dict = Field(default_factory=dict)


def _qwen_grid(params, tpl):
    """Qwen-Image-2.1 sizes everything on a 32-grid and its own budget stops at 2K.

    Refused here rather than at the engine: a bad canvas otherwise comes back as a
    latent-shape error no caller can trace back to a number box.
    """
    edit = tpl["map"] is templates.QWEN_EDIT_MAP
    keys = ("resolution",) if edit else ("width", "height")
    for k in keys:
        v = params.get(k)
        if not isinstance(v, int):
            raise HTTPException(422, f"{k} 要填整数")
        if v % 32:
            raise HTTPException(422, f"{k} 必须是 32 的倍数")
    if edit:
        if params["resolution"] > 2048:
            raise HTTPException(422, "resolution 是总像素预算，官方上限 2048（≈2K 直出）")
    elif params["width"] * params["height"] > 2048 * 2048:
        raise HTTPException(422, "超过原生 2K 的像素预算（2048×2048）")


def create(body: TaskIn):
    tpl = templates.BY_ID.get(body.template)
    if tpl is None:
        raise HTTPException(422, f"unknown template {body.template!r}")
    # Only prompt-taking templates require one; the 3D chain is driven by an image.
    if "prompt" in tpl["fields"] and not body.prompt.strip():
        raise HTTPException(422, "this template needs a prompt")
    params = {**tpl["defaults"], **body.params}
    # An image-driven template with nothing bound would fail inside ComfyUI as
    # "image not in list"; the caller can act on this instead.
    if "image" in tpl["fields"] and not (params.get("image") or params.get("image_task")):
        raise HTTPException(422, "这条工作流要先有一张图：在参数里选图，或在结果里点「做成视频」")
    if "video" in tpl["fields"] and not (params.get("video") or params.get("video_task")):
        raise HTTPException(422, "这条工作流要先有一个视频：在参数里上传，或在结果里点「做成高清」")
    # ref1 is the edit target; the rest are optional references, so only this one is required.
    if "ref1" in tpl["fields"] and not (params.get("ref1") or params.get("image_task")):
        raise HTTPException(422, "这条工作流要先有一张参考图：ref1 是被改的对象，或在结果里点「拿去改」")
    if tpl["map"] in (templates.QWEN_MAP, templates.QWEN_EDIT_MAP):
        _qwen_grid(params, tpl)
    if "prompt" in tpl["fields"]:
        params["prompt"] = body.prompt
    # A caller that names its own output folder wins: a canvas step does, so that two
    # steps running the same template do not write into each other's files.
    params.setdefault("prefix", f"studio/{body.template}")
    title = body.prompt[:60] if "prompt" in tpl["fields"] else str(params.get("image") or params.get("video") or tpl["name"])
    with Session() as s:
        t = Task(template=body.template, title=title, model=tpl["model"],
                 params=params, state="queued")
        s.add(t)
        s.commit()
        tid = t.id
        # The readable id is derived from the row id so it cannot collide, and the
        # queue position a caller sees is this task's, not the engine's.
        t.ref = f"task_{datetime.now(timezone.utc):%Y%m%d}_{tid:03d}"
        s.commit()
        ref = t.ref
    pos = runner.runner.submit_task(tid)
    return {"task_id": tid, "ref": ref, "queue_position": pos}


def row(t, full=False):
    tpl = templates.BY_ID.get(t.template)
    out = {"id": t.id, "ref": t.ref, "template": t.template, "title": t.title, "model": t.model,
           "media": tpl["media"] if tpl else "image",
           "state": t.state, "progress": t.progress, "error": t.error,
           "favorite": t.favorite, "seconds": t.seconds,
           "created_at": t.created_at, "finished_at": t.finished_at,
           "params": {k: t.params.get(k) for k in
                      ("width", "height", "steps", "cfg", "seed", "batch", "length", "fps", "octree")
                      if t.params.get(k) is not None}}
    if full:
        # The single-task view carries the whole parameter set: the form restores
        # itself from it, and a summary missing unet/clip would blank the model select.
        out["params"] = t.params
        out["outputs"] = t.outputs
        out["log"] = t.log
        out["comfy_id"] = t.comfy_id
    return out
