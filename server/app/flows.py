"""Canvas validation and the executor that walks a chain one step at a time.

Two rules shape this module. A step is a whole measured template, never a ComfyUI node --
see the note on ``models.Flow``. And steps run in order, each waiting for the previous
one's artefacts, because the engine holds one graph at a time and the binding a
downstream step needs (``image_task``) is an id that only exists once the upstream run is
done.
"""

import random
import time
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from pathlib import PurePosixPath

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from . import comfy, gates, templates
from . import tasks as task_svc
from .config import COMFY_OUTPUT_ROOT, WORK
from .db import Session
from .models import Flow, FlowRun, Task

MAX_NODES = 12
# A step may be asked to try again this many times after its first attempt. Small on
# purpose: each attempt is a whole measured run (a clip is 30 minutes of budget here),
# so "retry until it works" is a way to spend an afternoon by accident.
MAX_RETRY = 3
# How many times one step runs to give a choice of pictures. Eight is the ceiling the
# card can still show as a row of thumbnails, and each one is a real generation.
MAX_REPEAT = 8
ON_ERROR = ("stop", "skip")
# What a step does with its picture once the engine has handed it back. "off" is the
# ordinary run; "check" measures and reports but lets the chain through; "sweep" holds
# the line until the gate signs off. See gates.sweep for what that costs.
GATE = ("off", "check", "sweep")
GATE_ROOT = WORK / "gates"
# A control wire carries no picture: it says when the step at its far end is allowed to
# run. "fail" is the useful one -- a fallback workflow that only fires when the first one
# did not produce anything.
WHEN = ("ok", "fail", "always")
WHEN_CN = {"ok": "上游成功", "fail": "上游失败", "always": "无条件"}
# A step is polled, not watched: the runner records TIMEOUT in its own task row, so this
# only covers the case where that worker died with the row still open. Deliberately
# longer than the slowest template's own budget (2700s for a long clip).
GRACE = 600
POLL = 2.0

# One worker, and not the generation pool. A flow thread spends its life waiting on tasks
# the generation pool runs; putting both on the same single worker deadlocks silently --
# the queue depth would show one job ahead and never move.
_flows = ThreadPoolExecutor(max_workers=1, thread_name_prefix="flow")


class FlowIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    graph: dict = Field(default_factory=dict)


def validate(graph):
    """Check the arrangement against the live registry and return the run order.

    Called on save *and* on run. A canvas authored last week can name a template that has
    since been removed, or an input slot that has been renamed; refusing before the first
    submission is what keeps that from becoming a chain that ran twice and then stopped.
    """
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    if not nodes:
        raise HTTPException(422, "画布上还没有步骤")
    if len(nodes) > MAX_NODES:
        raise HTTPException(422, f"一条链最多 {MAX_NODES} 步，现在有 {len(nodes)} 步")

    by_id = {}
    for n in nodes:
        nid = n.get("id")
        tpl = templates.BY_ID.get(n.get("template"))
        if not nid or nid in by_id:
            raise HTTPException(422, "步骤编号缺失或重复")
        if tpl is None:
            raise HTTPException(422, f"步骤 {nid} 的模板 {n.get('template')!r} 已经不在模板库里")
        if not isinstance(n.get("params", {}), dict):
            raise HTTPException(422, f"步骤 {nid} 的参数必须是对象")
        # The step's own failure policy is part of the arrangement, so a canvas that
        # asks for 9 retries is refused where it is written rather than at the fourth
        # hour of running it.
        r = n.get("retries", 0)
        if isinstance(r, bool) or not isinstance(r, int) or not 0 <= r <= MAX_RETRY:
            raise HTTPException(422, f"步骤 {nid} 的重试次数要是 0–{MAX_RETRY} 的整数")
        if n.get("on_error", "stop") not in ON_ERROR:
            raise HTTPException(422, f"步骤 {nid} 失败时怎么办，只能是 {'、'.join(ON_ERROR)}")
        rep = n.get("repeat", 1)
        if isinstance(rep, bool) or not isinstance(rep, int) or not 1 <= rep <= MAX_REPEAT:
            raise HTTPException(422, f"步骤 {nid} 的执行次数要是 1–{MAX_REPEAT} 的整数")
        gt = n.get("gate", "off")
        if gt not in GATE:
            raise HTTPException(422, f"步骤 {nid} 的交付门禁只能是 {'、'.join(GATE)}")
        # The gate judges a vectorised icon. Hanging it on a step that hands back a clip
        # or a mesh would be a switch wired to nothing, so it is refused where it is set.
        if gt != "off" and tpl["media"] != "image":
            raise HTTPException(422, f"步骤 {nid} 出的是 {tpl['media']}，"
                                     f"矢量门禁只能挂在出图的步骤上")
        by_id[nid] = tpl

    wired = set()
    ctrl = {}
    data_pairs = set()
    for e in edges:
        src, dst = by_id.get(e.get("from")), by_id.get(e.get("to"))
        if src is None or dst is None:
            raise HTTPException(422, f"有一根线连到了不存在的步骤：{e.get('from')} → {e.get('to')}")
        if e.get("from") == e.get("to"):
            raise HTTPException(422, f"步骤 {e['from']} 不能连到自己")
        if e.get("kind") == "control":
            if e.get("when", "ok") not in WHEN:
                raise HTTPException(422, f"{e['from']} → {e['to']} 这根条件线只能是 "
                                         f"{'、'.join(WHEN)}，现在是 {e.get('when')!r}")
            key = (e["to"], e["from"])
            if key in ctrl:
                raise HTTPException(422, f"步骤 {e['to']} 已经有一条来自 {e['from']} 的条件线，"
                                         f"两条条件只能留一条")
            ctrl[key] = e.get("when", "ok")
            continue
        if e.get("out") != src["media"]:
            raise HTTPException(422, f"步骤 {e['from']} 只有 {src['media']} 输出口，没有 {e.get('out')!r}")
        port = next((p for p in templates.ports_of(dst)["in"] if p["name"] == e.get("in")), None)
        if port is None:
            names = [p["name"] for p in templates.ports_of(dst)["in"]] or ["无"]
            raise HTTPException(422, f"步骤 {e['to']} 没有 {e.get('in')!r} 这个输入，能接的是 {'、'.join(names)}")
        if port["type"] != src["media"]:
            raise HTTPException(422, f"{e['from']} 出的是 {src['media']}，接不进 {e['to']} 的 "
                                     f"{port['name']}（它要 {port['type']}）")
        key = (e["to"], e["in"])
        if key in wired:
            raise HTTPException(422, f"步骤 {e['to']} 的 {e['in']} 已经有一根线：一个输入只能有一个来源")
        wired.add(key)
        data_pairs.add((e["to"], e["from"]))
        a = e.get("attempt", 0)
        if isinstance(a, bool) or not isinstance(a, int) or not 0 <= a < MAX_REPEAT:
            raise HTTPException(422, f"步骤 {e['to']} 的这根线要取上游第几遍，只能是 1–{MAX_REPEAT}")

    # A step cannot both consume a picture and wait for the step that makes it to fail:
    # the branch it is on would have no input the moment it is the one allowed to run.
    for (dst, src), when in ctrl.items():
        if when == "fail" and (dst, src) in data_pairs:
            raise HTTPException(422, f"步骤 {dst} 既接了 {src} 的产物，又设成「{src} 失败时才走」："
                                     f"这两件事不能同时成立")

    return _order(nodes, edges)


def _order(nodes, edges):
    """Topological order, ties broken by authored order so a chain runs left to right.

    Kahn rather than a DFS because whatever is left after the queue drains *is* the cycle,
    which is the list worth showing; a DFS back-edge names one edge inside a loop nobody
    drew as a loop.
    """
    pending = defaultdict(int)
    downstream = defaultdict(list)
    for e in edges:
        pending[e["to"]] += 1
        downstream[e["from"]].append(e["to"])
    ready = [n["id"] for n in nodes if not pending[n["id"]]]
    order, done = [], set()
    while ready:
        nid = ready.pop(0)
        order.append(next(n for n in nodes if n["id"] == nid))
        done.add(nid)
        for nxt in downstream[nid]:
            pending[nxt] -= 1
            if pending[nxt] == 0:
                ready.append(nxt)
    if len(order) != len(nodes):
        stuck = sorted({n["id"] for n in nodes} - done)
        raise HTTPException(422, f"这些步骤互相等待，链里有环：{'、'.join(stuck)}")
    return order


def start(flow_id):
    """Open the run row and hand the walk to the flow worker.

    Every step becomes a task only when its turn comes, so a chain that dies at step two
    never left a step-three task sitting in the queue to be mistaken for work in progress.
    """
    with Session() as s:
        f = s.get(Flow, flow_id)
        if f is None:
            raise HTTPException(404, "没有这条画布")
        graph = dict(f.graph or {})
    order = validate(graph)
    run_ref = f"run_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}"
    with Session() as s:
        r = FlowRun(flow_id=flow_id, ref=run_ref, state="running",
                    steps=[{"node": n["id"], "template": n["template"], "task_id": None, "error": None,
                            "retries": n.get("retries", 0), "on_error": n.get("on_error", "stop"),
                            "repeat": n.get("repeat", 1), "gate": None, "runs": [],
                            "attempts": 0, "skipped": False} for n in order])
        s.add(r)
        s.commit()
        rid = r.id
    _flows.submit(_walk, rid, graph, order)
    return {"run": run_ref, "flow_id": flow_id, "steps": len(order)}


def _walk(run_id, graph, order):
    edges = graph.get("edges") or []
    data = [e for e in edges if e.get("kind") != "control"]
    gates = defaultdict(list)
    for e in edges:
        if e.get("kind") == "control":
            gates[e["to"]].append(e)
    media_of = {n["id"]: templates.BY_ID[n["template"]]["media"] for n in order}
    # node -> the task ids that finished, in repetition order. A step that failed or was
    # skipped stays out of here, so its downstream reads as "no input" and is skipped too
    # rather than being wired to a task with no artefacts.
    delivered = {}
    # node -> how it ended, which is all a control wire is allowed to look at.
    outcome = {}
    steps = None
    current = None
    try:
        for node in order:
            current = node["id"]
            tpl = templates.BY_ID[node["template"]]
            held = [f"{g['from']}（要 {WHEN_CN[g.get('when', 'ok')]}）" for g in gates.get(current, [])
                    if not _passes(outcome.get(g["from"]), g.get("when", "ok"))]
            if held:
                outcome[current] = "skipped"
                steps = _patch(steps, run_id, current, skipped=True,
                               error=f"条件线没满足：{'、'.join(held)}，这一步跳过")
                continue
            gone = [f'{e["from"]}第{int(e.get("attempt") or 0) + 1}遍'
                    if int(e.get("attempt") or 0) else e["from"]
                    for e in data if e["to"] == current and not _has(delivered, e)]
            if gone:
                outcome[current] = "skipped"
                steps = _patch(steps, run_id, current, skipped=True,
                               error=f"上游 {'、'.join(gone)} 没有产物，这一步跳过")
                continue
            if _stopping(run_id):
                return _close(run_id, "cancelled")
            params = dict(node.get("params") or {})
            # Output folders are per step, not per template: two steps on one template
            # would otherwise share a prefix and the provenance would be a lie.
            params["prefix"] = f"studio/run{run_id}/{current}"
            for e in data:
                if e["to"] != current:
                    continue
                src = delivered[e["from"]][int(e.get("attempt") or 0)]
                # The literal filename has to go: the runner only takes the task-id route
                # for a step that has no file of its own, and the canvas stores the whole
                # form, a stale pick included.
                params.pop(e["in"], None)
                params[f"{media_of[e['from']]}_task"] = src
                params[f"{media_of[e['from']]}_index"] = int(e.get("index") or 0)
            runs = []
            reason, state, tried = None, "done", 0
            want = node.get("gate") or "off"
            reps = int(node.get("repeat") or 1)
            for rep in range(reps):
                if rep and "seed" in tpl["defaults"]:
                    # Every repetition is a different picture for the same reason a retry
                    # is: the engine caches an identical graph.
                    params["seed"] = random.randrange(10 ** 9)
                tid, state, reason, submissions = _attempt(run_id, node, tpl, params)
                tried += submissions
                g = _gate(run_id, current, rep, tid) if state == "done" and want != "off" else None
                runs.append({"task_id": tid, "state": state, "error": reason, "gate": g})
                steps = _patch(steps, run_id, current, task_id=tid, attempts=tried, runs=runs, gate=g)
                if state != "done":
                    break
                if g and want == "sweep" and g["verdict"] != "PASS":
                    # The picture exists and the gate will not have it. The presets are
                    # spent, so the only lever left is a different drawing -- and when the
                    # step was told to make several, the next one is that chance.
                    reason = _gate_says(g)
                    if rep + 1 < reps:
                        continue
                    # Out of pictures, so this step delivers nothing: a file the gate
                    # refused must not travel downstream behind a green card.
                    state = "error"
                    break
                delivered.setdefault(current, []).append(tid)
                if g and want == "sweep":
                    # 扫到过为止: one deliverable picture is what that asks for, and the
                    # rest of the repetitions would be GPU time spent on a choice nobody
                    # asked the gate to make.
                    break
            if state == "done":
                outcome[current] = "done"
            if state == "cancelled":
                steps = _patch(steps, run_id, current, error="已取消这次运行")
                return _close(run_id, "cancelled")
            if state != "done":
                steps = _patch(steps, run_id, current, error=reason)
                if (node.get("on_error") or "stop") == "skip":
                    outcome[current] = "error"
                    continue
                _close(run_id, "error", f"步骤 {current}（{tpl['name']}）{reason}，一共提了 {tried} 次")
                return
        _close(run_id, "partial" if any(x.get("skipped") for x in steps or []) else "done")
    except HTTPException as exc:
        steps = _patch(steps, run_id, current, error=str(exc.detail))
        _close(run_id, "error", str(exc.detail))
    except Exception as exc:
        steps = _patch(steps, run_id, current, error=f"{type(exc).__name__}: {exc}")
        _close(run_id, "error", f"{type(exc).__name__}: {exc}")


def _gate(run_id, nid, rep, task_id):
    """Vectorise what this repetition handed back and put it through the gate.

    Runs on the flow thread, and is cheap there: 0.19s of CPU per preset for a 1024² icon,
    against 20-90s on the GPU for another seed. That asymmetry is the whole design -- a
    path-count failure is chased with a preset, and only when every preset has failed
    does the step fall back on asking the model for a different drawing.
    """
    with Session() as s:
        outs = [o for o in (s.get(Task, task_id).outputs or [])
                if str(o.get("filename", "")).lower().endswith(".png")]
    if not outs:
        return {"verdict": "FAIL", "tries": [], "presets": [], "svgs": [], "bad": [],
                "worst": None, "fails": ["这一步没有交回 png，无从矢量化"], "seconds": 0.0}
    pics = [COMFY_OUTPUT_ROOT / o.get("subfolder", "") / o["filename"] for o in outs]
    try:
        g = gates.sweep(pics, GATE_ROOT / f"run{run_id}" / f"{nid}-{rep}")
    except BaseException as exc:
        # vtracer is a Rust extension: it panics rather than raising, and a PanicException
        # is not an Exception, so it would walk straight past the handler in _walk and leave
        # the run row saying "running" with nothing left running it. A gate that could not
        # measure is a failure with a reason, recorded like any other verdict.
        return {"verdict": "FAIL", "tries": [], "presets": [], "svgs": [],
                "bad": [p.name for p in pics], "worst": pics[0].name,
                "fails": [f"矢量化没能跑完：{type(exc).__name__}: {exc}"], "seconds": 0.0}
    # Storing the path relative to the gate root rather than as given means moving
    # WORK_DIR does not strand every SVG this chain ever delivered.
    for v in g["svgs"]:
        v["file"] = PurePosixPath(f"run{run_id}", f"{nid}-{rep}", Path(v["file"]).name).as_posix()
    return g


def _gate_says(g):
    """The refusal names the columns, because that is what decides the next move: a path
    count is a vectoriser setting, an interior mismatch is the drawing itself."""
    bad = f"{len(g['bad'])} 张都没过" if len(g["bad"]) > 1 else (g["bad"][0] if g["bad"] else "没有产物")
    return (f"矢量门禁未过（{bad}，试过 {'→'.join(g['tries']) or '无预设'}）："
            f"{'、'.join(g['fails'])}")


def _passes(up, when):
    """Does an upstream outcome satisfy one control wire? A step that never ran counts as
    not-success, so a fallback does not need to know which of the two ways it failed."""
    if when == "always":
        return True
    if when == "ok":
        return up == "done"
    return up in ("error", "skipped")


def _has(delivered, e):
    """Does the upstream task this wire points at actually exist?"""
    done = delivered.get(e["from"]) or []
    return len(done) > int(e.get("attempt") or 0)


def _attempt(run_id, node, tpl, params):
    """One repetition, retried as many times as the step asked for.

    (task_id, state, reason, submissions). A retry rolls a new seed first: resubmitting
    the same graph is answered from the engine's cache -- measured seconds 0.0 and the
    output filename not advancing -- so without a new seed the second attempt is the
    first attempt's picture and the retry is a lie.
    """
    reason, task_id = None, None
    for attempt in range(int(node.get("retries") or 0) + 1):
        if attempt and "seed" in tpl["defaults"]:
            params["seed"] = random.randrange(10 ** 9)
        made = task_svc.create(task_svc.TaskIn(template=node["template"],
                                               prompt=str(params.get("prompt") or ""),
                                               params=dict(params)))
        task_id = made["task_id"]
        state = _await(made["task_id"], tpl.get("timeout", 900) + GRACE, run_id)
        if state == "cancelled":
            _abandon(made["task_id"])
            return task_id, "cancelled", None, attempt + 1
        if state == "done":
            return task_id, "done", None, attempt + 1
        reason = _reason(made["task_id"], state)
    return task_id, "error", reason, int(node.get("retries") or 0) + 1


def _await(task_id, budget, run_id):
    """Poll the task row until it settles, the budget runs out, or the run is called off.

    The cancel flag is read in the same poll because a step can hold this loop for the
    length of a clip: checking only between steps would make 取消 mean "when the GPU
    decides to be free".
    """
    deadline = time.monotonic() + budget
    while time.monotonic() < deadline:
        with Session() as s:
            if s.get(FlowRun, run_id).state == "cancelling":
                return "cancelled"
            state = s.get(Task, task_id).state
        if state in ("done", "error"):
            return state
        time.sleep(POLL)
    return "STALLED"


def _stopping(run_id):
    with Session() as s:
        return s.get(FlowRun, run_id).state == "cancelling"


def _abandon(task_id):
    """Let go of the step we were waiting on: the engine's job first, then the task row.

    A step that never reached the engine is still queued on the runner's worker, and that
    row has to be settled here -- otherwise the GPU picks it up after we said cancelled.
    A step already running writes its own failure once the engine job is gone, so this
    does not touch it: two writers, one truth.
    """
    with Session() as s:
        t = s.get(Task, task_id)
        pid, state = t.comfy_id, t.state
    if pid:
        comfy.cancel(pid)
    if state == "queued":
        with Session() as s:
            t = s.get(Task, task_id)
            t.state, t.error = "error", "取消这次运行时它还在排队"
            t.finished_at = datetime.now(timezone.utc)
            s.commit()


def _reason(task_id, state):
    if state == "done":
        return None
    with Session() as s:
        err = s.get(Task, task_id).error
    return err or f"在 {state} 状态停留过久（超过自身时限仍未落定）"


def _patch(steps, run_id, nid, task_id=None, error=None, attempts=None, skipped=None, runs=None,
           gate=None):
    """Update one step and persist the whole list, so a refresh mid-run sees the truth."""
    steps = steps or _load(run_id).steps
    out = [dict(x) for x in steps]
    for x in out:
        if x["node"] == nid:
            if task_id is not None:
                x["task_id"] = task_id
            if error is not None:
                x["error"] = error
            if attempts is not None:
                x["attempts"] = attempts
            if skipped is not None:
                x["skipped"] = skipped
            if gate is not None:
                x["gate"] = gate
            if runs is not None:
                x["runs"] = [dict(r) for r in runs]
    with Session() as s:
        s.get(FlowRun, run_id).steps = out
        s.commit()
    return out


def _load(run_id):
    with Session() as s:
        return s.get(FlowRun, run_id)


def _close(run_id, state, error=None):
    with Session() as s:
        r = s.get(FlowRun, run_id)
        r.state, r.error = state, error
        r.finished_at = datetime.now(timezone.utc)
        s.commit()


def status(run_ref):
    with Session() as s:
        r = s.scalar(select(FlowRun).where(FlowRun.ref == run_ref))
        if r is None:
            raise HTTPException(404, "没有这次运行")
        steps = []
        for st in r.steps:
            t = s.get(Task, st["task_id"]) if st.get("task_id") else None
            # A skipped step has no task at all, and "pending" would read as "still to
            # come" to a page that is about to finish.
            state = "skipped" if st.get("skipped") else (t.state if t else "pending")
            # A step can hold a picture the gate refused: the task did its job and the
            # chain still stopped. Reading "done" off the task row alone would show green
            # over a red error line.
            if st.get("error") and state == "done":
                state = "error"
            # One entry per repetition: the card shows them as a row and a wire picks
            # which one it feeds from. The task row is the truth about each, so this
            # reads through to it rather than trusting what was written mid-run.
            runs = []
            for rn in (st.get("runs") or []):
                rt = s.get(Task, rn["task_id"]) if rn.get("task_id") else None
                runs.append({"task_id": rn.get("task_id"), "state": rt.state if rt else rn.get("state"),
                             "seconds": rt.seconds if rt else None, "error": rn.get("error"),
                             "gate": rn.get("gate"), "outputs": rt.outputs if rt else []})
            steps.append({**{k: st.get(k) for k in ("node", "template", "task_id", "error",
                                                    "retries", "on_error", "repeat", "attempts")},
                          "state": state, "runs": runs,
                          "gate": _gate_out(r.ref, st["node"], st.get("gate")),
                          "progress": t.progress if t else 0,
                          "seconds": t.seconds if t else None,
                          "outputs": t.outputs if t else [],
                          "log_tail": (t.log[-1]["msg"] if t and t.log else None)})
        return {"run": r.ref, "flow_id": r.flow_id, "state": r.state, "error": r.error,
                "created_at": r.created_at, "finished_at": r.finished_at, "steps": steps}


def _gate_out(run_ref, nid, g):
    """The step's gate record, with a download link per SVG it accepted.

    The links are built here rather than stored, so the only thing a client can name is a
    position in this list and the route resolves the file from the run row.
    """
    if not g:
        return None
    out = {k: v for k, v in g.items() if k != "svgs"}
    out["svgs"] = [{**v, "dl": PurePosixPath(v["file"]).name,
                    "href": f"/flows/runs/{run_ref}/gate/{nid}/{i}"}
                   for i, v in enumerate(g.get("svgs") or [])]
    return out


def deliverable(run_ref, nid, index):
    """The SVG file one step's gate accepted, resolved out of the run row.

    Only a node id and a position in a list the database wrote come from the URL, and the
    path still has to land under the gate root -- the same rule the output delete follows,
    because a delivery endpoint that can name a file is a read of the whole disk.
    """
    with Session() as s:
        r = s.scalar(select(FlowRun).where(FlowRun.ref == run_ref))
        if r is None:
            raise HTTPException(404, "没有这次运行")
        for st in r.steps:
            svgs = (st.get("gate") or {}).get("svgs") if st["node"] == nid else None
            if svgs and index < len(svgs):
                root = GATE_ROOT.resolve()
                path = (root / svgs[index]["file"]).resolve()
                if not path.is_relative_to(root):
                    raise HTTPException(400, "门禁产物不在交付目录内，拒绝下发")
                if not path.is_file():
                    raise HTTPException(410, "这个 SVG 已经不在了，交付目录被清过")
                return path
    raise HTTPException(404, "这一步没有这个交付文件")


def cancel(run_ref):
    """Call off a live run. The worker sees it between steps and inside its own poll.

    The flag goes on the row rather than into a set in this process, so a second worker --
    or the same one after a restart that left the row running -- reads the same answer.
    """
    with Session() as s:
        r = s.scalar(select(FlowRun).where(FlowRun.ref == run_ref))
        if r is None:
            raise HTTPException(404, "没有这次运行")
        if r.state != "running":
            raise HTTPException(409, f"这次运行已经是 {r.state}，没有可取消的了")
        r.state = "cancelling"
        s.commit()
    return {"run": run_ref, "state": "cancelling"}
