"""S1 vertical slice: submit a batch, poll, read the same gate table the CLI prints.

The startup guard is the non-negotiable part. Every number this API returns comes
from a ruler that was itself validated against known-truth fixtures; if that ruler
goes blind -- a dependency changes, a metric stops discriminating -- the service
must refuse to serve rather than hand out confident-looking PASSes.
"""

import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from . import gates, runner
from .config import FIXTURES
from .db import init_db
from .gates import Kit
from .models import Asset, Batch
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
