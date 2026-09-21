"""L5 node-count sweep: what does it cost to get path_nodes under budget.

Evaluates the real deliverable, not the intermediate: vectorise -> svg_norm ->
svg_flat -> gate. Scoring the pre-flat rasteriser would report budgets the shipped
file never has.
"""

import argparse
import itertools
import json
import statistics as st
import sys
import tempfile
from pathlib import Path

import vtracer

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qa_gate
import svg_flat
import svg_norm

GRIDS = {
    "polygon-lt": [dict(hierarchical="stacked", mode="polygon", filter_speckle=f, color_precision=6,
                        layer_difference=16, corner_threshold=60, length_threshold=lt,
                        max_iterations=10, splice_threshold=45, path_precision=2)
                   for lt, f in itertools.product([4, 12, 25, 50], [4, 12, 30])],
    "spline-coarse": [dict(hierarchical="stacked", mode="spline", filter_speckle=f, color_precision=5,
                           layer_difference=32, corner_threshold=ct, length_threshold=8.0,
                           max_iterations=6, splice_threshold=60, path_precision=2)
                      for ct in (40, 60, 90) for f in (8, 20)],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="run/ic")
    ap.add_argument("--kit", default="brand-kit.example.json")
    ap.add_argument("--grid", default="polygon-lt")
    args = ap.parse_args()

    kit = json.loads(Path(args.kit).read_text(encoding="utf-8"))
    b = dict(kit["budget"])
    b["target_fill"] = kit["optical_fill"]
    b["grid"] = kit["grid"]
    d = Path(args.dir)
    assets = sorted(p.name[: -len("_gt.png")] for p in d.glob("*_gt.png"))
    print(f"{len(assets)} assets x {len(GRIDS[args.grid])} configs\n")

    rows = []
    for cfg in GRIDS[args.grid]:
        name = f"lt{cfg['length_threshold']:g}/sp{cfg['filter_speckle']}/ct{cfg['corner_threshold']}/it{cfg['max_iterations']}"
        ms = []
        bytes_tot = 0
        for stem in assets:
            gt = d / f"{stem}_gt.png"
            with tempfile.TemporaryDirectory() as td:
                out = Path(td) / "v.svg"
                vtracer.convert_image_to_svg_py(str(gt), str(out), colormode="color", **cfg)
                raw = out.read_text(encoding="utf-8")
            try:
                normed, _, _, _ = svg_norm.normalise(raw, kit)
                flat, _ = svg_flat.flatten(normed, kit)
            except Exception as e:
                print(f"  {name} {stem}: FAILED {type(e).__name__} {e}")
                continue
            bytes_tot += len(flat.encode())
            ms.append(qa_gate.measure(gt, flat, b, kit["palette"]))
        if not ms:
            continue
        ok = sum(1 for m in ms if m["verdict"] == "PASS")
        rows.append(dict(cfg=name, n=len(ms), ok=ok, bytes=bytes_tot,
                         nodes_max=max(m["path_nodes"] for m in ms),
                         nodes_med=st.median(m["path_nodes"] for m in ms),
                         paths_max=max(m["paths"] for m in ms),
                         col_max=max(m["colors"] for m in ms),
                         cham_max=max(m["chamfer_grid_px"] for m in ms),
                         iou_min=min(m["alpha_iou"] for m in ms),
                         ssim_min=min(m["thumb_ssim_16"] for m in ms),
                         rmse_max=max(m["interior_rmse_vs_snapped"] for m in ms),
                         fails=sorted({f.split()[0] for m in ms for f in m["fails"]})))
        print(f"{name:26} pass {ok}/{len(ms)}  nodes max {rows[-1]['nodes_max']:5}  "
              f"paths {rows[-1]['paths_max']:3}  col {rows[-1]['col_max']:2}  "
              f"cham {rows[-1]['cham_max']:.3f}  iou {rows[-1]['iou_min']:.3f}  "
              f"ssim {rows[-1]['ssim_min']:.3f}  rmseS {rows[-1]['rmse_max']:5.1f}  "
              f"{rows[-1]['bytes']:>9}B  {','.join(rows[-1]['fails']) or '-'}", flush=True)

    hdr = (f"{'config':26}{'PASS':>7}{'nodes max':>11}{'nodes med':>11}{'paths':>7}{'col':>5}"
           f"{'cham max':>10}{'iou min':>9}{'ssim min':>10}{'rmseS max':>11}{'bytes':>10}  remaining fails")
    print("\n" + hdr)
    print("-" * len(hdr))
    for r in sorted(rows, key=lambda x: (-x["ok"], x["nodes_max"])):
        print(f"{r['cfg']:26}{r['ok']:>4}/{r['n']:<2}{r['nodes_max']:>11}{r['nodes_med']:>11.0f}{r['paths_max']:>7}"
              f"{r['col_max']:>5}{r['cham_max']:>10.3f}{r['iou_min']:>9.3f}{r['ssim_min']:>10.3f}"
              f"{r['rmse_max']:>11.1f}{r['bytes']:>10}  {','.join(r['fails']) or '-'}")


if __name__ == "__main__":
    main()
