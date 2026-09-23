"""Thin wrapper over the icon-pipeline tools -- deliberately no re-implementation.

The gate is the product. Importing the same modules the CLI uses means the API
cannot drift from the numbers in the README, which is the failure mode worth
avoiding most: two rulers, one of them quietly wrong.
"""

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from .config import BRAND_KIT, TOOLS

if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import qa_gate  # noqa: E402
import svg_flat  # noqa: E402
import svg_norm  # noqa: E402
import vectorize_local  # noqa: E402

COLUMNS = qa_gate.COLUMNS


@dataclass
class Kit:
    raw: dict

    @classmethod
    def load(cls, path=BRAND_KIT):
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    @property
    def budget(self):
        b = dict(self.raw["budget"])
        b["target_fill"] = self.raw["optical_fill"]
        b["grid"] = self.raw["grid"]
        return b

    @property
    def palette(self):
        return self.raw["palette"]


def measure(source_png, svg_text, kit):
    return qa_gate.measure(Path(source_png), svg_text, kit.budget, kit.palette)


def normalise(svg_text, kit):
    text, viewBox, baked, bbox = svg_norm.normalise(svg_text, kit.raw)
    return text, {"viewBox": viewBox, "transforms_baked": baked, "bbox": list(bbox)}


def flatten(svg_text, kit, snap=True, group=True, min_area=0.0):
    text, drift = svg_flat.flatten(svg_text, kit.raw, snap, group, min_area)
    return text, drift


# ---------------------------------------------------------------- the vectoriser
# The preset table is imported from the CLI rather than copied: two copies of nine
# numbers is how one ruler starts quietly judging a different drawing than the other.
PRESETS = vectorize_local.PRESETS
# Fine to coarse. Ordered this way because the failure a preset can fix is too many
# paths, and tightening is what a designer would try first.
SWEEP = ("tight", "default", "coarse")


def vectorize(png, svg_path, preset="default"):
    """One picture to one SVG at one of the CLI's presets.

    The existence check is not defensive padding: vtracer is a Rust extension and raises
    a PanicException for a path it cannot read, which arrives at the caller as a crash
    with no sentence in it.
    """
    src, dst = Path(png), Path(svg_path)
    if not src.is_file():
        raise FileNotFoundError(f"矢量化找不到输入图：{src.name}")
    return vectorize_local.run_vtracer(src, dst, PRESETS[preset])


def sweep(pngs, out_dir, kit=None, presets=SWEEP):
    """vectorise -> norm -> flat -> gate, preset by preset, until the gate accepts.

    This is the cheap retry: measured 0.19s of CPU per preset on a 1024² icon (1.6s on a
    832×1216 photograph), against 20-90s on the GPU for another seed. It only buys what the
    vectoriser controls -- path, node and colour counts. A picture that fails on interior
    fidelity fails under every preset, and the reported columns say exactly that.

    Every picture is judged, not just the first: a step that returns four of them has to
    say which four it is willing to deliver.
    """
    kit = kit or Kit.load()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    todo, svgs, worst, tried = [Path(p) for p in pngs], [], None, []
    for preset in presets:
        tried.append(preset)
        left = []
        for png in todo:
            # vtracer writes a file and hands back its text; what gets kept is the
            # *finished* SVG, because that is the drawing the gate just signed off --
            # the raw vectorisation would fail the same table it was measured against.
            raw = out_dir / f"{png.stem}-{preset}.raw.svg"
            norm, _ = normalise(vectorize(png, raw, preset), kit)
            raw.unlink()
            flat, _ = flatten(norm, kit)
            where = out_dir / f"{png.stem}-{preset}.svg"
            where.write_text(flat, encoding="utf-8")
            gate = measure(png, flat, kit)
            if gate["verdict"] == "PASS":
                svgs.append({"name": png.name, "preset": preset, "file": str(where)})
            else:
                left.append(png)
                if worst is None or len(gate["fails"]) > len(worst["fails"]):
                    worst = {"name": png.name, "fails": gate["fails"], "preset": preset}
        todo = left
        if not todo:
            break
    return {"verdict": "PASS" if not todo else "FAIL", "tries": tried,
            "presets": sorted({s["preset"] for s in svgs}), "svgs": svgs,
            "bad": [p.name for p in todo],
            "worst": worst["name"] if worst else None,
            "fails": worst["fails"] if worst else [],
            "seconds": round(time.perf_counter() - t0, 2)}


def budget_for(column, budget):
    """The limit a column is judged against -- same table the gate enforces with."""
    return qa_gate.budget_for_column(column, budget)


def column_checks(measurement, budget):
    return qa_gate.column_checks(measurement, budget)


def ruler_selftest(source_png, svg_text, kit):
    """Returns (ok, failures). Used as a startup guard: a blind ruler must not serve.

    Failures are described with their before/after values, because "the ruler is
    blind" without the numbers is not actionable from a log line.
    """
    variants = {"clean": svg_text}
    for kind in qa_gate.VARIANTS:
        variants[kind] = qa_gate.perturb(svg_text, kind)
    res = {k: measure(source_png, v, kit) for k, v in variants.items()}

    failures = []
    for kind, key, expect, axis in qa_gate.CHECKS:
        b, v = qa_gate._val(res["clean"], key), qa_gate._val(res[kind], key)
        tol = qa_gate.TOL.get(key, 0.0)
        if expect == "up":
            moved = v > b + tol
        elif expect == "down":
            moved = v < b - tol
        else:
            moved = abs(v - b) <= 3 * tol
        if not moved:
            failures.append(f"{kind}->{key}[{expect}] {b} vs {v} (tol {tol})")
    return not failures, failures
