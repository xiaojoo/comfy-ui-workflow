"""Permanently removing one figure must not move its neighbours.

Two failures matter here. A delete that reaches outside the engine's output directory
takes the host's files instead of the run's. And a slot that is *removed* shifts every
later index, while a stored input binding names an index -- the next run would then
read the wrong picture and nothing on screen would say so.
"""

from fastapi.testclient import TestClient

from app import main as main_mod
from app.db import Session
from app.main import app
from app.models import Task


def entry(name, sub=""):
    return {"subfolder": sub, "filename": name, "url": f"/comfy/view?filename={name}"}


def make(entries):
    with Session() as s:
        t = Task(template="char_portrait", state="done", outputs=entries)
        s.add(t)
        s.commit()
        return t.id


def test_the_file_goes_and_the_slot_stays(tmp_path, monkeypatch):
    out = tmp_path / "output"
    out.mkdir()
    for n in ("a.png", "b.png", "c.png"):
        (out / n).write_bytes(b"\x89PNG fake")
    monkeypatch.setattr(main_mod, "COMFY_OUTPUT_ROOT", out)

    with TestClient(app) as c:
        tid = make([entry("a.png"), entry("b.png"), entry("c.png")])
        r = c.post(f"/tasks/{tid}/delete-output", json={"index": 1, "filename": "b.png"})
        assert r.status_code == 200, r.text
        assert not (out / "b.png").exists(), "the file has to be gone, not hidden"
        assert (out / "a.png").exists() and (out / "c.png").exists()
        outs = r.json()["outputs"]
        assert [o["filename"] for o in outs] == ["a.png", "b.png", "c.png"]
        assert outs[1].get("deleted") is True
        assert not outs[0].get("deleted") and not outs[2].get("deleted")
        # Deleting the same slot twice must not unlink a second time: the index is the
        # only thing identifying it, and a later file could have landed there.
        assert c.post(f"/tasks/{tid}/delete-output",
                      json={"index": 1, "filename": "b.png"}).status_code == 200
        assert (out / "a.png").exists() and (out / "c.png").exists()


def test_a_row_naming_a_file_outside_the_root_is_refused(tmp_path, monkeypatch):
    out = tmp_path / "output"
    out.mkdir()
    secret = tmp_path / "secret.png"
    secret.write_bytes(b"keep me")
    monkeypatch.setattr(main_mod, "COMFY_OUTPUT_ROOT", out)

    with TestClient(app) as c:
        tid = make([entry("secret.png", "../")])
        r = c.post(f"/tasks/{tid}/delete-output", json={"index": 0, "filename": "secret.png"})
        assert r.status_code == 400, r.text
        assert secret.exists()
        assert not c.get(f"/tasks/{tid}").json()["outputs"][0].get("deleted")


def test_a_stale_index_or_filename_is_refused(tmp_path, monkeypatch):
    out = tmp_path / "output"
    out.mkdir()
    (out / "a.png").write_bytes(b"\x89PNG fake")
    monkeypatch.setattr(main_mod, "COMFY_OUTPUT_ROOT", out)

    with TestClient(app) as c:
        tid = make([entry("a.png")])
        assert c.post(f"/tasks/{tid}/delete-output",
                      json={"index": 0, "filename": "other.png"}).status_code == 409
        assert c.post(f"/tasks/{tid}/delete-output",
                      json={"index": 4, "filename": "a.png"}).status_code == 409
        assert (out / "a.png").exists()
