"""Thin wrapper over the icon-pipeline tools -- deliberately no re-implementation.

The gate is the product. Importing the same modules the CLI uses means the API
cannot drift from the numbers in the README, which is the failure mode worth
avoiding most: two rulers, one of them quietly wrong.
"""

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import BRAND_KIT, TOOLS

if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import qa_gate  # noqa: E402
import svg_flat  # noqa: E402
import svg_norm  # noqa: E402


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
