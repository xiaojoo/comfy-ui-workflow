"""Analytically shaded object renders -- a clean input for the 3D chain.

Hunyuan3D assumes one object on a plain background. The earlier test image had a
halo ring, two holographic panels and a floor reflection, and all three came back
as geometry (323 shells, 44% non-manifold edges). This produces an input that
cannot be blamed, so whatever shells remain are the model's, not the photo's.
"""

import json
import math
import sys
from pathlib import Path

import numpy as np
import PIL.Image

S = 768


def shade(spheres, bg=(245, 245, 245), light=(-0.45, 0.55, 0.7)):
    n = np.linalg.norm(light)
    lx, ly, lz = [v / n for v in light]
    yy, xx = np.mgrid[0:S, 0:S]
    u = (xx + 0.5) / S * 2 - 1
    v = 1 - (yy + 0.5) / S * 2
    img = np.zeros((S, S, 3), np.float64)
    acc = np.zeros((S, S), bool)
    for (cx, cy, r, col) in spheres:
        dx, dy = u - cx, v - cy
        d2 = dx * dx + dy * dy
        m = d2 <= r * r
        z = np.sqrt(np.clip(r * r - d2, 0, None))
        nx_, ny_, nz_ = dx / r, dy / r, z / r
        lam = np.clip(nx_ * lx + ny_ * ly + nz_ * lz, 0, 1)
        lum = 0.18 + 0.82 * lam
        for c in range(3):
            img[..., c] = np.where(m & ~acc, col[c] * lum, img[..., c])
        acc |= m
    out = np.where(acc[..., None], img, np.array(bg, np.float64))
    return PIL.Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "run/solid")
    out.mkdir(parents=True, exist_ok=True)
    shade([(0.0, 0.0, 0.62, (210, 170, 120))]).save(out / "obj_sphere.png")
    shade([(0.0, -0.28, 0.40, (200, 150, 110)), (0.0, 0.28, 0.28, (200, 150, 110))]).save(out / "obj_snowman.png")
    (out / "obj_truth.json").write_text(json.dumps({
        "obj_sphere": {"kind": "sphere", "radius_norm": 0.62, "silhouette_area_px": math.pi * (0.62 * S / 2) ** 2},
        "obj_snowman": {"kind": "two spheres", "radii_norm": [0.40, 0.28], "expected_shells": 2},
        "background": "flat 245 grey, no shadow, no reflection, single object, no overlapping props",
    }, indent=2), encoding="utf-8")
    print("wrote obj_sphere.png obj_snowman.png obj_truth.json")


if __name__ == "__main__":
    main()
