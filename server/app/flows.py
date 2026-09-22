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

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from . import comfy, templates
from . import tasks as task_svc
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
        by_id[nid] = tpl

    wired = set()
    for e in edges:
        src, dst = by_id.get(e.get("from")), by_id.get(e.get("to"))
        if src is None or dst is None:
            raise HTTPException(422, f"有一根线连到了不存在的步骤：{e.get('from')} → {e.get('to')}")
        if e.get("from") == e.get("to"):
            raise HTTPException(422, f"步骤 {e['from']} 不能连到自己")
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
        a = e.get("attempt", 0)
        if isinstance(a, bool) or not isinstance(a, int) or not 0 <= a < MAX_REPEAT:
            raise HTTPException(422, f"步骤 {e['to']} 的这根线要取上游第几遍，只能是 1–{MAX_REPEAT}")

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
                            "repeat": n.get("repeat", 1), "runs": [],
                            "attempts": 0, "skipped": False} for n in order])
        s.add(r)
        s.commit()
        rid = r.id
    _flows.submit(_walk, rid, graph, order)
    return {"run": run_ref, "flow_id": flow_id, "steps": len(order)}


def _walk(run_id, graph, order):
    edges = graph.get("edges") or []
    media_of = {n["id"]: templates.BY_ID[n["template"]]["media"] for n in order}
    # node -> the task ids that finished, in repetition order. A step that failed or was
    # skipped stays out of here, so its downstream reads as "no input" and is skipped too
    # rather than being wired to a task with no artefacts.
    delivered = {}
    steps = None
    current = None
    try:
        for node in order:
            current = node["id"]
            tpl = templates.BY_ID[node["template"]]
            gone = [f'{e["from"]}第{int(e.get("attempt") or 0) + 1}遍'
                    if int(e.get("attempt") or 0) else e["from"]
                    for e in edges if e["to"] == current and not _has(delivered, e)]
            if gone:
                steps = _patch(steps, run_id, current, skipped=True,
                               error=f"上游 {'、'.join(gone)} 没有产物，这一步跳过")
                continue
            if _stopping(run_id):
                return _close(run_id, "cancelled")
            params = dict(node.get("params") or {})
            # Output folders are per step, not per template: two steps on one template
            # would otherwise share a prefix and the provenance would be a lie.
            params["prefix"] = f"studio/run{run_id}/{current}"
            for e in edges:
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
            for rep in range(int(node.get("repeat") or 1)):
                if rep and "seed" in tpl["defaults"]:
                    # Every repetition is a different picture for the same reason a retry
                    # is: the engine caches an identical graph.
                    params["seed"] = random.randrange(10 ** 9)
                tid, state, reason, submissions = _attempt(run_id, node, tpl, params)
                tried += submissions
                runs.append({"task_id": tid, "state": state, "error": reason})
                steps = _patch(steps, run_id, current, task_id=tid, attempts=tried, runs=runs)
                if state == "done":
                    delivered.setdefault(current, []).append(tid)
                    continue
                break
            if state == "cancelled":
                steps = _patch(steps, run_id, current, error="已取消这次运行")
                return _close(run_id, "cancelled")
            if state != "done":
                steps = _patch(steps, run_id, current, error=reason)
                if (node.get("on_error") or "stop") == "skip":
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


def _patch(steps, run_id, nid, task_id=None, error=None, attempts=None, skipped=None, runs=None):
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
            # One entry per repetition: the card shows them as a row and a wire picks
            # which one it feeds from. The task row is the truth about each, so this
            # reads through to it rather than trusting what was written mid-run.
            runs = []
            for rn in (st.get("runs") or []):
                rt = s.get(Task, rn["task_id"]) if rn.get("task_id") else None
                runs.append({"task_id": rn.get("task_id"), "state": rt.state if rt else rn.get("state"),
                             "seconds": rt.seconds if rt else None, "error": rn.get("error"),
                             "outputs": rt.outputs if rt else []})
            steps.append({**{k: st.get(k) for k in ("node", "template", "task_id", "error",
                                                    "retries", "on_error", "repeat", "attempts")},
                          "state": state, "runs": runs,
                          "progress": t.progress if t else 0,
                          "seconds": t.seconds if t else None,
                          "outputs": t.outputs if t else [],
                          "log_tail": (t.log[-1]["msg"] if t and t.log else None)})
        return {"run": r.ref, "flow_id": r.flow_id, "state": r.state, "error": r.error,
                "created_at": r.created_at, "finished_at": r.finished_at, "steps": steps}


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
