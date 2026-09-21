import sys
from pathlib import Path

import numpy as np
import cv2
sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
import qa_gate as Q

gt = Path("run/gt/gear_gt.png")
svg = Path("run/svg/default/gear.svg").read_text(encoding="utf-8")
src = Q.crop_to_bbox_fill(Q.load_rgba(gt))
dst = Q.crop_to_bbox_fill(Q.rasterize(svg))
s, d = src[..., 3] >= 128, dst[..., 3] >= 128
print("src fg px", s.sum(), "dst fg px", d.sum(), "xor", np.logical_xor(s, d).sum())

dt_to_d = cv2.distanceTransform(1 - d.astype(np.uint8), cv2.DIST_L2, 3)
dt_to_s = cv2.distanceTransform(1 - s.astype(np.uint8), cv2.DIST_L2, 3)
a = dt_to_d[s & ~d]
b = dt_to_s[d & ~s]
for nm, arr in (("src-only", a), ("dst-only", b)):
    if arr.size == 0:
        print(nm, "empty")
        continue
    print(f"{nm}: n={arr.size} p50={np.percentile(arr,50):.1f} p90={np.percentile(arr,90):.1f} "
          f"p99={np.percentile(arr,99):.1f} max={arr.max():.1f} mean={arr.mean():.1f}")

ys, xs = np.nonzero(s & ~d)
if len(xs):
    print("src-only bbox x", xs.min(), xs.max(), "y", ys.min(), ys.max())
ys, xs = np.nonzero(d & ~s)
if len(xs):
    print("dst-only bbox x", xs.min(), xs.max(), "y", ys.min(), ys.max())
print("connected comps dst-only:", cv2.connectedComponents((~s & d).astype(np.uint8))[0])

print("\n-- same inputs through the real helper --")
print("silhouette_distance(s,d) =", Q.silhouette_distance(s, d))
print("per_px =", Q.budget if False else (24 / Q.RASTER))
ch, hs = Q.silhouette_distance(s, d)
print(f"chamfer_grid = {ch * 24 / Q.RASTER:.4f}  haus_grid = {hs * 24 / Q.RASTER:.4f}")

print("\n-- through the full measure() --")
import json
kit = json.loads(Path("brand-kit.example.json").read_text(encoding="utf-8"))
b = dict(kit["budget"])
b["target_fill"] = kit["optical_fill"]
b["grid"] = kit["grid"]
m = Q.measure(gt, svg, b, kit["palette"])
print({k: m[k] for k in ("alpha_iou", "chamfer_grid_px", "hausdorff_p95_grid_px", "fill_ratio", "bbox_center_offset_pct")})
