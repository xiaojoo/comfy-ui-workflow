"""S1 vertical slice: submit a batch, poll, read the same gate table the CLI prints.

The startup guard is the non-negotiable part. Every number this API returns comes
from a ruler that was itself validated against known-truth fixtures; if that ruler
goes blind -- a dependency changes, a metric stops discriminating -- the service
must refuse to serve rather than hand out confident-looking PASSes.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from . import comfy, flows, gates, runner, tasks, templates
from .config import COMFY_OUTPUT_ROOT, FIXTURES
from .db import init_db
from .gates import Kit
from .models import Asset, Batch, Flow, FlowRun, Task
from .db import Session

RULER_FIXTURES = [("gear_gt.png", "gear.svg"), ("shield_gt.png", "shield.svg")]


def check_ruler():
    """Re-derive the numbers, don't trust the last run's."""
    kit = Kit.load()
    bad = {}
    for png, svg in RULER_FIXTURES:
        ok, failures = gates.ruler_selftest(FIXTURES / png, (FIXTURES / svg).read_text(encoding="utf-8"), kit)
        if not ok:
            bad[svg] = failures
    if bad:
        detail = "; ".join(f"{k}: {v}" for k, v in bad.items())
        raise RuntimeError(f"ruler not discriminating - refusing to serve. {detail}")


@asynccontextmanager
async def lifespan(_app):
    init_db()
    check_ruler()
    yield


app = FastAPI(title="comfy-ui-workflow", version="0.1.0", lifespan=lifespan)


class Item(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    source_png: Path
    raw_svg: Path

    @field_validator("source_png", "raw_svg")
    @classmethod
    def must_exist(cls, v: Path):
        if not v.is_file():
            raise ValueError(f"not a readable file: {v}")
        return v


class BatchIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    items: list[Item] = Field(min_length=1, max_length=500)


@app.get("/health")
def health():
    return {"ok": True, "queued_ahead": runner.runner.depth()}


@app.post("/batches", status_code=202)
def create_batch(body: BatchIn):
    k = Kit.load()
    # Persist the *effective* budget: the gate judges against Kit.budget, which
    # injects target_fill and grid. Storing the raw file instead gives a batch two
    # budgets, and fill_ratio silently stops being checkable in the viewer.
    kit = {**k.raw, "budget": k.budget}
    with Session() as s:
        b = Batch(name=body.name, kit=kit, state="queued")
        b.assets = [Asset(name=i.name, source_png=str(i.source_png), raw_svg=i.raw_svg.read_text(encoding="utf-8"))
                    for i in body.items]
        s.add(b)
        s.commit()
        bid, n = b.id, len(b.assets)
    pos = runner.runner.submit(bid)
    return {"batch_id": bid, "assets": n, "queue_position": pos}


@app.get("/batches")
def list_batches(limit: int = Query(default=50, ge=1, le=500)):
    """Board view: one row per batch with the counts a reviewer scans for."""
    with Session() as s:
        out = []
        for b in s.scalars(select(Batch).order_by(Batch.id.desc()).limit(limit)):
            out.append({
                "batch_id": b.id, "name": b.name, "state": b.state, "error": b.error,
                "created_at": b.created_at, "finished_at": b.finished_at,
                "assets": len(b.assets),
                "passed": sum(1 for a in b.assets if a.verdict == "PASS"),
                "approved": sum(1 for a in b.assets if a.approval == "approved"),
            })
        return {"batches": out}


@app.get("/batches/{batch_id}")
def get_batch(batch_id: int):
    with Session() as s:
        b = s.get(Batch, batch_id)
        if b is None:
            raise HTTPException(404, "no such batch")
        return {
            "batch_id": b.id, "name": b.name, "state": b.state, "error": b.error,
            "assets": [{"id": a.id, "name": a.name, "verdict": a.verdict, "approval": a.approval,
                        "fails": a.gate.get("fails", [])} for a in b.assets],
        }


@app.get("/batches/{batch_id}/gate")
def gate_table(batch_id: int):
    """The per-asset table, in the same columns the CLI prints."""
    cols = gates.COLUMNS
    with Session() as s:
        b = s.get(Batch, batch_id)
        if b is None:
            raise HTTPException(404, "no such batch")
        rows = [{"id": a.id, "name": a.name, "verdict": a.verdict, "approval": a.approval,
                 "fails": a.gate.get("fails", []),
                 "checks": gates.column_checks(a.gate, b.kit["budget"]),
                 "before_stages": a.meta.get("before_stages", {}),
                 **{c: a.gate.get(c) for c in cols}} for a in b.assets]
        passed = sum(1 for r in rows if r["verdict"] == "PASS")
        return {"state": b.state, "columns": cols, "rows": rows,
                "summary": f"{passed}/{len(rows)} PASS",
                "budget": b.kit["budget"], "optical_fill": b.kit["optical_fill"],
                "column_budget": {c: gates.budget_for(c, b.kit["budget"]) for c in cols}}


class Approval(BaseModel):
    approve: bool


@app.post("/batches/{batch_id}/assets/{asset_id}/approve")
def approve(batch_id: int, asset_id: int, body: Approval):
    with Session() as s:
        a = s.get(Asset, asset_id)
        if a is None or a.batch_id != batch_id:
            raise HTTPException(404, "no such asset in batch")
        if body.approve and a.verdict != "PASS":
            raise HTTPException(409, f"asset is {a.verdict}, not shippable: {a.gate.get('fails')}")
        a.approval = "approved" if body.approve else "rejected"
        s.commit()
        return {"id": a.id, "approval": a.approval}


@app.get("/batches/{batch_id}/assets/{asset_id}/svg")
def svg_of(batch_id: int, asset_id: int, stage: str = "flat"):
    with Session() as s:
        a = s.get(Asset, asset_id)
        if a is None or a.batch_id != batch_id:
            raise HTTPException(404, "no such asset in batch")
        text = {"raw": a.raw_svg, "norm": a.norm_svg, "flat": a.flat_svg}.get(stage)
        if text is None:
            raise HTTPException(400, f"stage must be raw|norm|flat, got {stage}")
        return {"name": a.name, "stage": stage, "svg": text}


# ---------------------------------------------------------------- studio surface

@app.get("/models")
def models():
    """What the live engine can load. Names come from ComfyUI, never from a list here."""
    return {"catalog": comfy.catalog(), "engine": comfy.engine(), "storage": comfy.storage()}


@app.get("/templates")
def template_list():
    return {"templates": templates.public()}


@app.post("/tasks", status_code=202)
def create_task(body: tasks.TaskIn):
    return tasks.create(body)


@app.get("/tasks")
def list_tasks(limit: int = Query(default=20, ge=1, le=200)):
    with Session() as s:
        rows = s.scalars(select(Task).order_by(Task.id.desc()).limit(limit)).all()
        return {"tasks": [tasks.row(t) for t in rows]}


@app.get("/tasks/{task_id}")
def get_task(task_id: int):
    with Session() as s:
        t = s.get(Task, task_id)
        if t is None:
            raise HTTPException(404, "no such task")
        return tasks.row(t, full=True)


class Favorite(BaseModel):
    favorite: bool


@app.post("/tasks/{task_id}/favorite")
def favorite(task_id: int, body: Favorite):
    with Session() as s:
        t = s.get(Task, task_id)
        if t is None:
            raise HTTPException(404, "no such task")
        t.favorite = body.favorite
        s.commit()
        return {"id": t.id, "favorite": t.favorite}


class OutputIn(BaseModel):
    index: int
    filename: str


@app.post("/tasks/{task_id}/delete-output")
def delete_output(task_id: int, body: OutputIn):
    """Take one produced file off the disk for good, and mark its slot as gone.

    Two rules hold this down. The request names an index plus the filename it expects
    there and the path is rebuilt from the row, so no call can name a file the database
    does not know about, and the resolved path still has to sit under the engine's
    output root. And the slot is tombstoned rather than removed: a later run's input
    binding stores that index, so closing the gap would hand it its neighbour's picture
    with nothing to show it happened.
    """
    with Session() as s:
        t = s.get(Task, task_id)
        if t is None:
            raise HTTPException(404, "no such task")
        outs = [dict(o) for o in (t.outputs or [])]
        if not 0 <= body.index < len(outs) or outs[body.index].get("filename") != body.filename:
            raise HTTPException(409, "这一项的内容已经变了，重新读取后再试")
        if not outs[body.index].get("deleted"):
            e = outs[body.index]
            root = COMFY_OUTPUT_ROOT.resolve()
            path = (root / e.get("subfolder", "") / e["filename"]).resolve()
            if not path.is_relative_to(root):
                raise HTTPException(400, "产物路径不在引擎输出目录内，拒绝删除")
            path.unlink(missing_ok=True)
            e["deleted"] = True
            t.outputs = outs
            s.commit()
        return tasks.row(t, full=True)


# ---------------------------------------------------------------- canvas surface
#
# A flow is an arrangement of the templates above, and a run of it is a row of Tasks:
# every structural rule lives in flows.validate, and every parameter rule is the one
# POST /tasks already applies. Nothing here is a second copy of either.

@app.get("/flows")
def list_flows(limit: int = Query(default=50, ge=1, le=200)):
    with Session() as s:
        out = []
        for f in s.scalars(select(Flow).order_by(Flow.updated_at.desc()).limit(limit)):
            g = f.graph or {}
            out.append({"id": f.id, "name": f.name, "updated_at": f.updated_at,
                        "nodes": len(g.get("nodes") or []), "edges": len(g.get("edges") or [])})
        return {"flows": out}


@app.post("/flows", status_code=201)
def create_flow(body: flows.FlowIn):
    order = flows.validate(body.graph)
    with Session() as s:
        f = Flow(name=body.name, graph=body.graph)
        s.add(f)
        s.commit()
        return {"flow_id": f.id, "steps": len(order)}


@app.get("/flows/runs/{run_ref}")
def get_flow_run(run_ref: str):
    return flows.status(run_ref)


@app.get("/flows/{flow_id}")
def get_flow(flow_id: int):
    with Session() as s:
        f = s.get(Flow, flow_id)
        if f is None:
            raise HTTPException(404, "没有这条画布")
        runs = s.scalars(select(FlowRun).where(FlowRun.flow_id == flow_id)
                         .order_by(FlowRun.id.desc()).limit(10)).all()
        return {"id": f.id, "name": f.name, "graph": f.graph,
                "runs": [{"run": r.ref, "state": r.state, "error": r.error,
                          "created_at": r.created_at, "finished_at": r.finished_at} for r in runs]}


@app.put("/flows/{flow_id}")
def update_flow(flow_id: int, body: flows.FlowIn):
    order = flows.validate(body.graph)
    with Session() as s:
        f = s.get(Flow, flow_id)
        if f is None:
            raise HTTPException(404, "没有这条画布")
        f.name, f.graph = body.name, body.graph
        s.commit()
        return {"flow_id": f.id, "steps": len(order)}


@app.delete("/flows/{flow_id}")
def delete_flow(flow_id: int):
    """Forget the arrangement. Its runs stay: they are the record of what was generated."""
    with Session() as s:
        f = s.get(Flow, flow_id)
        if f is None:
            raise HTTPException(404, "没有这条画布")
        s.delete(f)
        s.commit()
        return {"deleted": flow_id}


@app.post("/flows/{flow_id}/run", status_code=202)
def run_flow(flow_id: int):
    return flows.start(flow_id)
