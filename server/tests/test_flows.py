"""S-canvas: a chain must wire the right file to the right step, or refuse first.

The interesting failure here is silent mis-wiring: a step reading a stale filename its
author left in the form instead of the upstream output, or a chain submitting step two
and only then noticing it has no input. So the structural refusals are asserted by their
message, and the happy path is asserted by *which file reached the engine*.
"""

import time
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import flows
from app import runner as runner_mod
from app import templates
from app.db import Session
from app.flows import _order, validate
from app.main import app
from app.models import Flow, FlowRun, Task


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


def test_deleting_a_canvas_takes_its_run_bookkeeping_with_it():
    """SQLite gives the id back to the next canvas; the old run must not follow it there."""
    with Session() as s:
        f = Flow(name="gone", graph={})
        s.add(f)
        s.commit()
        fid = f.id
        s.add(FlowRun(flow_id=fid, ref="run_orphan", state="done", steps=[]))
        s.commit()
    with TestClient(app) as c:
        assert c.get(f"/flows/{fid}").json()["runs"]
        assert c.delete(f"/flows/{fid}").status_code == 200
        with Session() as s:
            assert s.scalar(select(FlowRun).where(FlowRun.ref == "run_orphan")) is None


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


# ------------------------------------------------------- what a step does when it fails

def step(nid, tpl, retries=0, on_error="stop", repeat=1, **params):
    return {"id": nid, "template": tpl, "params": params, "position": {"x": 0, "y": 0},
            "retries": retries, "on_error": on_error, "repeat": repeat}


def fake_engine(monkeypatch, tmp_path, fail=None, count=None, fail_nodes=None):
    """A stand-in engine. `fail` counts failed attempts per step kind, `fail_nodes` per node id."""
    fail, count, fail_nodes = fail or {}, count or {}, fail_nodes or {}
    attempts, per_node, kind_of, node_of = {}, {}, {}, {}

    def submit(graph, client_id):
        kind_of[client_id] = _kinds_of(graph)
        # Each step writes into its own output folder, and that folder names the node --
        # so a test can fail one step of a chain that repeats a template.
        node_of[client_id] = next((v["inputs"]["filename_prefix"].rsplit("/", 1)[-1]
                                   for v in graph.values()
                                   if v.get("inputs", {}).get("filename_prefix", "").startswith("studio/run")),
                                  kind_of[client_id])
        return client_id

    def collect(pid, timeout=900):
        kind, n = kind_of[pid], node_of[pid]
        attempts[kind] = attempts.get(kind, 0) + 1
        per_node[n] = per_node.get(n, 0) + 1
        if attempts[kind] <= fail.get(kind, 0) or per_node[n] <= fail_nodes.get(n, 0):
            return "error", [], 0.1
        files = []
        for i in range(count.get(kind, 1)):
            name = f"{kind}_{i}.{'mp4' if kind == 'clip' else 'png'}"
            (tmp_path / name).write_bytes(b"\x89PNG\r\n\x1a\n")
            files.append({"subfolder": "", "filename": name, "type": "output"})
        return "success", files, 0.1

    monkeypatch.setattr(runner_mod, "COMFY_OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(runner_mod.comfy, "submit", submit)
    monkeypatch.setattr(runner_mod.comfy, "collect", collect)
    monkeypatch.setattr(runner_mod.comfy, "upload", lambda src, name=None: Path(src).name)
    return attempts


def ctl(f, t, when):
    return {"from": f, "to": t, "kind": "control", "when": when}


def settle(c, run, secs=40):
    deadline = time.time() + secs
    while time.time() < deadline:
        st = c.get(f"/flows/runs/{run}").json()
        if st["state"] in ("done", "error", "cancelled", "partial"):
            return st
        time.sleep(0.2)
    raise AssertionError(f"这次运行停在 {st['state']}：{st}")


def run_chain(graph):
    with TestClient(app) as c:
        fid = c.post("/flows", json={"name": "chain", "graph": graph}).json()["flow_id"]
        return settle(c, c.post(f"/flows/{fid}/run").json()["run"])


def test_a_retry_submits_a_different_picture(tmp_path, monkeypatch):
    """The load-bearing detail: a resubmitted seed is answered from the engine's cache.

    Measured on the live engine -- identical graph, `seconds` 0.0 and the output filename
    does not advance -- so a retry that keeps the seed would report two attempts and show
    the same picture twice.
    """
    attempts = fake_engine(monkeypatch, tmp_path, fail={"portrait": 1})
    st = run_chain({"nodes": [step("n1", "char_portrait", retries=2, prompt="x")], "edges": []})
    assert st["state"] == "done", st
    assert st["steps"][0]["attempts"] == 2 and attempts["portrait"] == 2
    with Session() as s:
        # Only this run's two attempts: the shared test database still holds the other
        # tests' tasks, and the step's own output folder is what identifies them.
        rid = s.scalar(select(FlowRun.id).where(FlowRun.ref == st["run"]))
        mine = f"studio/run{rid}/"
        seeds = [t.params["seed"] for t in s.scalars(select(Task).where(Task.template == "char_portrait"))
                 if str(t.params.get("prefix", "")).startswith(mine)]
    assert len(seeds) == 2 and seeds[0] != seeds[1], f"两次同一个 seed = 白重试一次：{seeds}"


def test_a_step_that_never_lands_stops_the_chain_after_its_retries(tmp_path, monkeypatch):
    fake_engine(monkeypatch, tmp_path, fail={"portrait": 9})
    graph = {"nodes": [step("n1", "char_portrait", retries=2, prompt="x"),
                       step("n2", "upscale_image")],
             "edges": [edge("n1", "n2", "image", "image")]}
    st = run_chain(graph)
    assert st["state"] == "error" and "一共提了 3 次" in st["error"], st
    assert st["steps"][0]["attempts"] == 3
    assert st["steps"][1]["task_id"] is None and st["steps"][1]["state"] == "pending"


def test_a_failed_step_can_be_walked_past(tmp_path, monkeypatch):
    """on_error=skip: the step is written off, the chain says how far it got."""
    fake_engine(monkeypatch, tmp_path, fail={"portrait": 9})
    graph = {"nodes": [step("n1", "char_portrait", on_error="skip", prompt="x"),
                       step("n2", "upscale_image")],
             "edges": [edge("n1", "n2", "image", "image")]}
    st = run_chain(graph)
    assert st["state"] == "partial", st
    assert st["steps"][0]["state"] == "error" and st["steps"][0]["error"]
    assert st["steps"][1]["task_id"] is None and st["steps"][1]["state"] == "skipped"
    assert "上游" in st["steps"][1]["error"] and "n1" in st["steps"][1]["error"]


def test_a_branch_whose_sibling_was_walked_past_is_skipped_too(tmp_path, monkeypatch):
    """Two steps on one chain: the one past the gap must not be handed a missing file."""
    fake_engine(monkeypatch, tmp_path, fail={"portrait": 9})
    graph = {"nodes": [step("n1", "char_portrait", on_error="skip", prompt="x"),
                       step("n2", "upscale_image"), step("n3", "upscale_image")],
             "edges": [edge("n1", "n2", "image", "image"), edge("n2", "n3", "image", "image")]}
    st = run_chain(graph)
    assert [s["state"] for s in st["steps"]] == ["error", "skipped", "skipped"]
    assert "n2" in st["steps"][2]["error"], "the reason names which upstream is gone"


def test_a_step_can_run_several_times_and_a_wire_picks_which_time(tmp_path, monkeypatch):
    """循环: N repetitions of one step, and the downstream says which one it feeds from."""
    fake_engine(monkeypatch, tmp_path, count={"portrait": 1, "hd": 1})
    graph = {"nodes": [step("n1", "char_portrait", repeat=3, prompt="x"), step("n2", "upscale_image")],
             "edges": [edge("n1", "n2", "image", "image")]}
    graph["edges"][0]["attempt"] = 1
    st = run_chain(graph)
    assert st["state"] == "done", st
    runs = st["steps"][0]["runs"]
    assert [r["state"] for r in runs] == ["done"] * 3 and len({r["task_id"] for r in runs}) == 3
    assert st["steps"][0]["attempts"] == 3
    with Session() as s:
        seeds = [s.get(Task, r["task_id"]).params["seed"] for r in runs]
        hd = s.get(Task, st["steps"][1]["task_id"])
    assert len(set(seeds)) == 3, f"三遍同一个 seed 只会得到同一张图：{seeds}"
    assert hd.params["image_task"] == runs[1]["task_id"], "the wire takes the second repetition"
    assert hd.params["image_index"] == 0


def test_a_wire_pointing_at_a_repetition_that_never_ran_is_skipped(tmp_path, monkeypatch):
    """Three repetitions asked for, the second one dies: there is no 第 2 遍 to take."""
    fake_engine(monkeypatch, tmp_path, count={"portrait": 1, "hd": 1}, fail={"portrait": 2})
    graph = {"nodes": [step("n1", "char_portrait", repeat=3, on_error="skip", prompt="x"),
                       step("n2", "upscale_image")],
             "edges": [dict(edge("n1", "n2", "image", "image"), attempt=1)]}
    st = run_chain(graph)
    assert st["steps"][0]["state"] == "error"
    assert st["steps"][1]["state"] == "skipped"
    assert "n1第2遍" in st["steps"][1]["error"], st["steps"][1]["error"]
    assert st["state"] == "partial"


def test_a_fallback_step_waits_for_the_first_one_to_fail(tmp_path, monkeypatch):
    """判断: a control wire runs the other branch only when the first branch did not land."""
    fake_engine(monkeypatch, tmp_path, count={"portrait": 1}, fail_nodes={"s1": 9})
    graph = {"nodes": [step("s1", "char_portrait", on_error="skip", prompt="x"),
                       step("s2", "icon_flat", prompt="fallback"),
                       step("s3", "upscale_image")],
             "edges": [ctl("s1", "s2", "fail"), edge("s1", "s3", "image", "image")]}
    st = run_chain(graph)
    assert st["steps"][0]["state"] == "error"
    assert st["steps"][1]["state"] == "done" and st["steps"][1]["task_id"], "the fallback ran"
    assert st["steps"][1]["error"] is None
    assert st["steps"][2]["state"] == "skipped"
    assert st["state"] == "partial"


def test_a_fallback_is_skipped_when_the_step_it_waits_on_succeeded(tmp_path, monkeypatch):
    fake_engine(monkeypatch, tmp_path, count={"portrait": 1})
    graph = {"nodes": [step("s1", "char_portrait", prompt="x"), step("s2", "icon_flat", prompt="fallback")],
             "edges": [ctl("s1", "s2", "fail")]}
    st = run_chain(graph)
    assert st["steps"][0]["state"] == "done"
    assert st["steps"][1]["state"] == "skipped" and st["steps"][1]["task_id"] is None
    assert "条件线没满足" in st["steps"][1]["error"] and "上游失败" in st["steps"][1]["error"]
    assert st["state"] == "partial"


def test_an_unconditional_control_wire_runs_whatever_happened_upstream(tmp_path, monkeypatch):
    fake_engine(monkeypatch, tmp_path, count={"portrait": 1}, fail_nodes={"s1": 9})
    graph = {"nodes": [step("s1", "char_portrait", on_error="skip", prompt="x"),
                       step("s2", "icon_flat", prompt="y")],
             "edges": [ctl("s1", "s2", "always")]}
    st = run_chain(graph)
    assert st["steps"][1]["state"] == "done"


def test_an_ok_control_wire_holds_the_step_back_until_the_upstream_lands(tmp_path, monkeypatch):
    fake_engine(monkeypatch, tmp_path, count={"portrait": 1}, fail_nodes={"s1": 9})
    graph = {"nodes": [step("s1", "char_portrait", on_error="skip", prompt="x"),
                       step("s2", "icon_flat", prompt="y")],
             "edges": [ctl("s1", "s2", "ok")]}
    st = run_chain(graph)
    assert st["steps"][1]["state"] == "skipped" and st["steps"][1]["task_id"] is None


@pytest.mark.parametrize("edges, says", [
    ([ctl("s1", "s2", "maybe")], "ok、fail、always"),
    ([ctl("s1", "s2", "fail"), ctl("s1", "s2", "ok")], "只能留一条"),
    # Taking the picture and waiting for the failure of the step that makes it cannot both hold.
    ([edge("s1", "s2", "image", "image"), ctl("s1", "s2", "fail")], "不能同时成立"),
])
def test_a_condition_that_cannot_be_evaluated_is_refused_at_save(edges, says):
    graph = {"nodes": [step("s1", "char_portrait", prompt="x"), step("s2", "upscale_image")],
             "edges": edges}
    with pytest.raises(Exception) as e:
        validate(graph)
    assert says in str(e.value.detail), e.value.detail


@pytest.mark.parametrize("bad, says", [
    (step("n1", "char_portrait", retries=9, prompt="x"), "0–3"),    (step("n1", "char_portrait", retries="2", prompt="x"), "0–3"),
    (step("n1", "char_portrait", retries=True, prompt="x"), "0–3"),
    (step("n1", "char_portrait", on_error="continue", prompt="x"), "stop、skip"),
    (step("n1", "char_portrait", repeat=9, prompt="x"), "1–8"),
    (step("n1", "char_portrait", repeat=0, prompt="x"), "1–8"),
])
def test_a_step_policy_that_cannot_be_honoured_is_refused_where_it_is_written(bad, says):
    with pytest.raises(Exception) as e:
        validate({"nodes": [bad], "edges": []})
    assert says in str(e.value.detail), e.value.detail


def test_a_wire_that_asks_for_a_repetition_beyond_the_ceiling_is_refused():
    graph = {"nodes": [step("n1", "char_portrait", prompt="x"), step("n2", "upscale_image")],
             "edges": [dict(edge("n1", "n2", "image", "image"), attempt=8)]}
    with pytest.raises(Exception) as e:
        validate(graph)
    assert "1–8" in str(e.value.detail), e.value.detail


def test_cancelling_a_chain_stops_where_it_is_and_gives_the_engine_back(tmp_path, monkeypatch):
    """取消 has to reach the step in flight, not just the ones after it."""
    hold = threading.Event()
    dropped = []
    monkeypatch.setattr(runner_mod.comfy, "submit", lambda graph, client_id: client_id)
    # No timeout on the hold: the generation worker is shared and serial, so this fake may
    # start long after the test began, and a capped wait would end the step as "error"
    # before the cancel was ever noticed.
    monkeypatch.setattr(runner_mod.comfy, "collect",
                        lambda pid, timeout=900: (hold.wait(180), ("error", [], 0.1))[1])
    monkeypatch.setattr(flows.comfy, "cancel", lambda pid: dropped.append(pid) or "removed")

    graph = {"nodes": [step("n1", "char_portrait", prompt="x"), step("n2", "upscale_image")],
             "edges": [edge("n1", "n2", "image", "image")]}
    with TestClient(app) as c:
        fid = c.post("/flows", json={"name": "chain", "graph": graph}).json()["flow_id"]
        run = c.post(f"/flows/{fid}/run").json()["run"]
        try:
            deadline = time.time() + 90
            while time.time() < deadline:
                if c.get(f"/flows/runs/{run}").json()["steps"][0]["task_id"]:
                    break
                time.sleep(0.2)
            assert c.post(f"/flows/runs/{run}/cancel").status_code == 200
            st = settle(c, run, secs=90)
        finally:
            hold.set()

        assert st["state"] == "cancelled", st
        assert st["steps"][0]["error"] == "已取消这次运行"
        assert st["steps"][1]["task_id"] is None, "the next step never became a task"
        assert dropped == [f"studio-{st['steps'][0]['task_id']}"], "the engine job was let go"
        assert c.post(f"/flows/runs/{run}/cancel").status_code == 409, "already over"


def test_a_step_still_queued_is_settled_so_the_gpu_never_picks_it_up(monkeypatch):
    """The runner takes tasks off its own worker; a cancelled one must not survive that."""
    dropped = []
    monkeypatch.setattr(flows.comfy, "cancel", lambda pid: dropped.append(pid) or "removed")
    with Session() as s:
        t = Task(template="char_portrait", title="x", model="m", params={}, state="queued")
        s.add(t)
        s.commit()
        tid = t.id
    flows._abandon(tid)
    with Session() as s:
        t = s.get(Task, tid)
        assert t.state == "error" and "排队" in t.error
    assert dropped == [], "nothing was submitted, so there is nothing to interrupt"


def test_a_run_recorded_before_the_step_policy_still_reads():
    """His existing rows carry four keys; the reader must not ask for the other three."""
    with Session() as s:
        f = Flow(name="old", graph={})
        s.add(f)
        s.commit()
        s.add(FlowRun(flow_id=f.id, ref="run_legacy", state="done",
                      steps=[{"node": "n1", "template": "char_portrait",
                              "task_id": None, "error": None}]))
        s.commit()
    with TestClient(app) as c:
        st = c.get("/flows/runs/run_legacy").json()
    assert st["steps"][0]["state"] == "pending"
    assert st["steps"][0]["attempts"] is None and st["steps"][0]["retries"] is None
