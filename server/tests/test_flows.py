"""S-canvas: a chain must wire the right file to the right step, or refuse first.

The interesting failure here is silent mis-wiring: a step reading a stale filename its
author left in the form instead of the upstream output, or a chain submitting step two
and only then noticing it has no input. So the structural refusals are asserted by their
message, and the happy path is asserted by *which file reached the engine*.
"""

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import runner as runner_mod
from app import templates
from app.db import Session
from app.flows import _order, validate
from app.main import app
from app.models import Task


def node(nid, tpl, **params):
    return {"id": nid, "template": tpl, "params": params, "position": {"x": 0, "y": 0}}


def edge(f, t, out, inp, index=0):
    return {"from": f, "out": out, "to": t, "in": inp, "index": index}


# The shape he asked for. char_video last so `video` is exercised as an output too.
PORTRAIT = node("n1", "char_portrait", prompt="a woman in a green jacket", batch=4)
# A step stores the whole form, stale file pick included -- the wire has to win.
HD = node("n2", "upscale_image", image="someone_else_upload_earlier.png")
CLIP = node("n3", "char_video", prompt="she waves once", width=480, height=864, length=124)
CHAIN = {"nodes": [PORTRAIT, HD, CLIP],
         "edges": [edge("n1", "n2", "image", "image", 2), edge("n2", "n3", "image", "image")]}


def test_ports_come_from_the_fields_the_form_already_renders():
    for t in templates.TEMPLATES:
        ports = templates.ports_of(t)
        assert [p["name"] for p in ports["in"]] == [f for f in t["fields"] if f in templates.BIND_IN]
        assert ports["out"] == [{"name": t["media"], "type": t["media"]}]


def test_extra_reference_slots_are_not_offered_as_wires():
    """ref1 is the subject of the edit; ref2-4 are companions, and one run carries one picture."""
    names = [p["name"] for p in templates.ports_of(templates.BY_ID["qwen_image_edit"])["in"]]
    assert names == ["ref1"]


def test_chain_order_is_the_authored_order():
    assert [n["id"] for n in _order(CHAIN["nodes"], CHAIN["edges"])] == ["n1", "n2", "n3"]


def test_a_branch_joins_after_the_side_that_feeds_it_ran():
    nodes = [node("a", "char_portrait", prompt="x"), node("b", "upscale_image"),
             node("c", "upscale_image"), node("d", "char_video", prompt="y")]
    edges = [edge("a", "b", "image", "image"), edge("a", "c", "image", "image"),
             edge("b", "d", "image", "image")]
    order = [n["id"] for n in _order(nodes, edges)]
    assert order[0] == "a" and order.index("d") > order.index("b")


@pytest.mark.parametrize("bad, says", [
    ({"nodes": [], "edges": []}, "还没有步骤"),
    ({"nodes": [node("n1", "no_such_template")], "edges": []}, "不在模板库里"),
    ({"nodes": [{"id": "n1", "template": "char_portrait", "params": {"prompt": "x"}},
                {"id": "n1", "template": "upscale_image", "params": {}}], "edges": []}, "重复"),
    ({"nodes": [PORTRAIT, HD], "edges": [edge("n1", "n2", "image", "video")]}, "没有 'video' 这个输入"),
    ({"nodes": [PORTRAIT, HD],
      "edges": [edge("n1", "n2", "image", "image"), edge("n1", "n2", "image", "image")]},
     "一个输入只能有一个来源"),
    # Both ends must accept the other's output or the port check stops it first: a cycle
    # is only reachable between two steps that each take what the other makes.
    ({"nodes": [node("n1", "upscale_image"), node("n2", "upscale_image")],
      "edges": [edge("n1", "n2", "image", "image"), edge("n2", "n1", "image", "image")]}, "环"),
])
def test_bad_canvas_is_refused_before_anything_runs(bad, says):
    with pytest.raises(Exception) as e:
        validate(bad)
    assert says in str(e.value.detail), e.value.detail


def test_a_video_output_does_not_plug_into_an_image_input():
    nodes = [node("n1", "char_video", prompt="x"), node("n2", "upscale_image")]
    with pytest.raises(Exception) as e:
        validate({"nodes": nodes, "edges": [edge("n1", "n2", "video", "image")]})
    assert "接不进" in str(e.value.detail)


def test_canvas_crud_keeps_the_graph_as_authored():
    with TestClient(app) as c:
        r = c.post("/flows", json={"name": "人物三件套", "graph": CHAIN})
        assert r.status_code == 201, r.text
        fid = r.json()["flow_id"]
        assert r.json()["steps"] == 3
        got = c.get(f"/flows/{fid}").json()
        assert got["graph"]["edges"][0]["index"] == 2, "the picked frame is part of the canvas"
        assert c.put(f"/flows/{fid}", json={"name": "改名", "graph": {"nodes": [HD], "edges": []}}).status_code == 200
        assert c.get(f"/flows/{fid}").json()["name"] == "改名"
        assert c.post("/flows", json={"name": "坏", "graph": {"nodes": [], "edges": []}}).status_code == 422
        assert c.delete(f"/flows/{fid}").status_code == 200
        assert c.get(f"/flows/{fid}").status_code == 404


def _kinds_of(graph):
    """Which step this is, read off the assembled graph rather than trust a call order."""
    cls = {v.get("class_type") for v in graph.values()}
    if "MiniMaxH3ImageToVideo" in cls:
        return "clip"
    if "ImageUpscaleWithModel" in cls:
        return "hd"
    return "portrait"


def test_chain_hands_the_chosen_picture_to_the_next_step(tmp_path, monkeypatch):
    """The whole point of the canvas, proven without a GPU.

    Step one emits four files and the edge selects index 2, so a mis-wire shows up as the
    wrong filename reaching the upload instead of as a green test.
    """
    by_kind = {"portrait": 4, "hd": 1, "clip": 1}
    pid_kind = {}
    uploaded = []

    def fake_submit(graph, client_id):
        pid_kind[client_id] = _kinds_of(graph)
        return client_id

    def fake_collect(pid, timeout=900):
        kind = pid_kind[pid]
        files = []
        for i in range(by_kind[kind]):
            name = f"{kind}_{i}.{'mp4' if kind == 'clip' else 'png'}"
            (tmp_path / name).write_bytes(b"\x89PNG\r\n\x1a\n")
            files.append({"subfolder": "", "filename": name, "type": "output"})
        return "success", files, 0.1

    def fake_upload(src, name=None):
        uploaded.append(Path(src).name)
        return Path(src).name

    monkeypatch.setattr(runner_mod, "COMFY_OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(runner_mod.comfy, "submit", fake_submit)
    monkeypatch.setattr(runner_mod.comfy, "collect", fake_collect)
    monkeypatch.setattr(runner_mod.comfy, "upload", fake_upload)

    with TestClient(app) as c:
        fid = c.post("/flows", json={"name": "chain", "graph": CHAIN}).json()["flow_id"]
        run = c.post(f"/flows/{fid}/run").json()["run"]
        deadline = time.time() + 60
        while time.time() < deadline:
            st = c.get(f"/flows/runs/{run}").json()
            if st["state"] in ("done", "error"):
                break
            time.sleep(0.2)

        assert st["state"] == "done", st
        ids = [s["task_id"] for s in st["steps"]]
        assert ids == sorted(ids) and all(ids), "one task per step, in chain order"
        assert [s["template"] for s in st["steps"]] == ["char_portrait", "upscale_image", "char_video"]
        assert uploaded == ["portrait_2.png", "hd_0.png"], "the edge's index, not the stale pick"

        with Session() as s:
            hd = s.get(Task, ids[1])
            assert hd.params["image_task"] == ids[0] and hd.params["image_index"] == 2
            assert hd.params["image"] == "portrait_2.png", "the bound file replaces the stale one"
            assert "someone_else_upload_earlier" not in str(hd.params)
            clip = s.get(Task, ids[2])
            assert clip.params["image_task"] == ids[1] and clip.params.get("image_index", 0) == 0


def test_a_step_that_refuses_to_start_stops_the_chain(tmp_path, monkeypatch):
    """No task may be created for a step whose input never arrived."""
    def fake_submit(graph, client_id):
        return "x"

    def fake_collect(pid, timeout=900):
        return "error", [], 0.1

    monkeypatch.setattr(runner_mod.comfy, "submit", fake_submit)
    monkeypatch.setattr(runner_mod.comfy, "collect", fake_collect)

    with TestClient(app) as c:
        fid = c.post("/flows", json={"name": "chain", "graph": CHAIN}).json()["flow_id"]
        run = c.post(f"/flows/{fid}/run").json()["run"]
        deadline = time.time() + 30
        while time.time() < deadline:
            st = c.get(f"/flows/runs/{run}").json()
            if st["state"] in ("done", "error"):
                break
            time.sleep(0.2)
        assert st["state"] == "error" and "n1" in st["error"]
        assert [s["task_id"] for s in st["steps"]] == [st["steps"][0]["task_id"], None, None]
        assert st["steps"][0]["state"] == "error"
