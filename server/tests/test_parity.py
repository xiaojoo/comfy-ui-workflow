"""S1 acceptance: the HTTP table must be the CLI table, not a reinterpretation.

Two independent paths -- a subprocess writing qa_report.json, and the server going
through queue -> SQLite -> JSON -- are compared field by field. Same source module
on both sides, so this catches plumbing damage and column renaming, which is what
actually breaks a gate product.
"""

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import FIXTURES, TOOLS
from app.gates import COLUMNS as NUMERIC
from app.main import app, check_ruler


def cli_report(tmp_path):
    d = tmp_path / "cli"
    d.mkdir(exist_ok=True)
    shutil.copy(FIXTURES / "gear_gt.png", d / "gear_gt.png")
    shutil.copy(FIXTURES / "gear.svg", d / "gear.svg")
    r = subprocess.run([sys.executable, str(TOOLS / "qa_gate.py"), "--dir", str(d)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-800:]
    return json.loads((d / "qa_report.json").read_text(encoding="utf-8"))


def test_ruler_is_live_on_fixtures():
    check_ruler()


def test_api_table_matches_cli(tmp_path):
    cli = cli_report(tmp_path)["gear.svg"]

    with TestClient(app) as c:
        body = {"name": "parity", "items": [{"name": "gear",
                                             "source_png": str(FIXTURES / "gear_gt.png"),
                                             "raw_svg": str(FIXTURES / "gear.svg")}]}
        r = c.post("/batches", json=body)
        assert r.status_code == 202, r.text
        bid = r.json()["batch_id"]

        for _ in range(60):
            st = c.get(f"/batches/{bid}").json()["state"]
            if st in ("done", "error"):
                break
            time.sleep(0.25)
        assert st == "done", c.get(f"/batches/{bid}").json()

        g = c.get(f"/batches/{bid}/gate").json()
        row = g["rows"][0]
        before = row["before_stages"]
        for k in NUMERIC:
            assert before[k] == pytest.approx(cli[k]), f"{k}: api {before[k]} != cli {cli[k]}"
        # The CLI measures the raw SVG, so parity is against the raw reading; the
        # row's own verdict is post-stage and legitimately differs.
        assert before["verdict"] == cli["verdict"]
        assert before["fails"] == cli["fails"]

        # Stages may only resolve violations, never invent ones -- gear's raw
        # fill-ratio breach is exactly what the flatten stage is there to fix.
        assert set(row["fails"]) <= set(before["fails"]), f"stages introduced {set(row['fails']) - set(before['fails'])}"
        assert row["name"] == "gear"
        assert g["summary"].endswith("PASS") or g["summary"].endswith("FAIL")


def test_cell_checks_cannot_contradict_the_verdict():
    """The viewer colours cells from row.checks, so a false check must mean FAIL.

    Only one direction is guaranteed: forbidden tags and non-transparent corners
    fail the gate without owning a column, so FAIL with all-true checks is legal.
    Two budgets is the regression this guards -- the batch stores the effective
    one, and fill_ratio goes unjudgeable if it ever stores the raw file again.
    """
    with TestClient(app) as c:
        body = {"name": "checks", "items": [{"name": "gear",
                                             "source_png": str(FIXTURES / "gear_gt.png"),
                                             "raw_svg": str(FIXTURES / "gear.svg")}]}
        bid = c.post("/batches", json=body).json()["batch_id"]
        for _ in range(60):
            j = c.get(f"/batches/{bid}").json()
            if j["state"] in ("done", "error"):
                break
            time.sleep(0.25)
        row = c.get(f"/batches/{bid}/gate").json()["rows"][0]
        assert any(v is not None for v in row["checks"].values()), "no column is judged at all"
        if any(v is False for v in row["checks"].values()):
            assert row["verdict"] == "FAIL", row["checks"]


def test_approve_guard_blocks_failing_asset(tmp_path):
    with TestClient(app) as c:
        body = {"name": "guard", "items": [{"name": "gear",
                                            "source_png": str(FIXTURES / "gear_gt.png"),
                                            "raw_svg": str(FIXTURES / "gear.svg")}]}
        bid = c.post("/batches", json=body).json()["batch_id"]
        for _ in range(60):
            j = c.get(f"/batches/{bid}").json()
            if j["state"] in ("done", "error"):
                break
            time.sleep(0.25)
        a = j["assets"][0]
        r = c.post(f"/batches/{bid}/assets/{a['id']}/approve", json={"approve": True})
        if a["verdict"] == "PASS":
            assert r.status_code == 200
        else:
            assert r.status_code == 409
            assert "not shippable" in r.text


def test_rejects_missing_input(tmp_path):
    with TestClient(app) as c:
        body = {"name": "bad", "items": [{"name": "x",
                                          "source_png": str(tmp_path / "nope.png"),
                                          "raw_svg": str(FIXTURES / "gear.svg")}]}
        assert c.post("/batches", json=body).status_code == 422
