"""Canvas validation and the executor that walks a chain one step at a time.

Two rules shape this module. A step is a whole measured template, never a ComfyUI node --
see the note on ``models.Flow``. And steps run in order, each waiting for the previous
one's artefacts, because the engine holds one graph at a time and the binding a
downstream step needs (``image_task``) is an id that only exists once the upstream run is
done.
"""

import time
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from . import templates
from . import tasks as task_svc
from .db import Session
from .models import Flow, FlowRun, Task

MAX_NODES = 12
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
                    steps=[{"node": n["id"], "template": n["template"], "task_id": None, "error": None}
                           for n in order])
        s.add(r)
        s.commit()
        rid = r.id
    _flows.submit(_walk, rid, graph, order)
    return {"run": run_ref, "flow_id": flow_id, "steps": len(order)}


def _walk(run_id, graph, order):
    edges = graph.get("edges") or []
    media_of = {n["id"]: templates.BY_ID[n["template"]]["media"] for n in order}
    produced = {}
    steps = None
    current = None
    try:
        for node in order:
            current = node["id"]
            tpl = templates.BY_ID[node["template"]]
            params = dict(node.get("params") or {})
            # Output folders are per step, not per template: two steps on one template
            # would otherwise share a prefix and the provenance would be a lie.
            params["prefix"] = f"studio/run{run_id}/{current}"
            for e in edges:
                if e["to"] != current:
                    continue
                src = produced.get(e["from"])
                if src is None:
                    raise RuntimeError(f"上游步骤 {e['from']} 没有产物，这一步没有输入")
                # The literal filename has to go: the runner only takes the task-id route
                # for a step that has no file of its own, and the canvas stores the whole
                # form, a stale pick included.
                params.pop(e["in"], None)
                params[f"{media_of[e['from']]}_task"] = src
                params[f"{media_of[e['from']]}_index"] = int(e.get("index") or 0)
            made = task_svc.create(task_svc.TaskIn(template=node["template"],
                                                   prompt=str(params.get("prompt") or ""),
                                                   params=params))
            produced[current] = made["task_id"]
            steps = _patch(steps, run_id, current, made["task_id"])
            state = _await(made["task_id"], tpl.get("timeout", 900) + GRACE)
            if state != "done":
                reason = _reason(made["task_id"], state)
                steps = _patch(steps, run_id, current, error=reason)
                _close(run_id, "error", f"步骤 {current}（{tpl['name']}）{reason}")
                return
        _close(run_id, "done")
    except HTTPException as exc:
        steps = _patch(steps, run_id, current, error=str(exc.detail))
        _close(run_id, "error", str(exc.detail))
    except Exception as exc:
        steps = _patch(steps, run_id, current, error=f"{type(exc).__name__}: {exc}")
        _close(run_id, "error", f"{type(exc).__name__}: {exc}")


def _await(task_id, budget):
    """Poll the task row until it settles, or until the budget says it is not coming back."""
    deadline = time.monotonic() + budget
    while time.monotonic() < deadline:
        with Session() as s:
            state = s.get(Task, task_id).state
        if state in ("done", "error"):
            return state
        time.sleep(POLL)
    return "STALLED"


def _reason(task_id, state):
    if state == "done":
        return None
    with Session() as s:
        err = s.get(Task, task_id).error
    return err or f"在 {state} 状态停留过久（超过自身时限仍未落定）"


def _patch(steps, run_id, nid, task_id=None, error=None):
    """Update one step and persist the whole list, so a refresh mid-run sees the truth."""
    steps = steps or _load(run_id).steps
    out = [dict(x) for x in steps]
    for x in out:
        if x["node"] == nid:
            if task_id is not None:
                x["task_id"] = task_id
            if error is not None:
                x["error"] = error
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
            steps.append({**{k: st[k] for k in ("node", "template", "task_id", "error")},
                          "state": t.state if t else "pending",
                          "progress": t.progress if t else 0,
                          "seconds": t.seconds if t else None,
                          "outputs": t.outputs if t else [],
                          "log_tail": (t.log[-1]["msg"] if t and t.log else None)})
        return {"run": r.ref, "flow_id": r.flow_id, "state": r.state, "error": r.error,
                "created_at": r.created_at, "finished_at": r.finished_at, "steps": steps}
