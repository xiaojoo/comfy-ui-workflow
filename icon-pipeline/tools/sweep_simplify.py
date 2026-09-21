"""Tolerance vs fidelity: sweep the shipped TS_SVGPathSimplify, not a re-write.

Starts from the *_flat.svg deliverables so it measures the last stage only.
Calls the real node class; whether it survives multi-subpath paths is exactly
what this is meant to find out, so nothing here pre-corrects for it.
"""

import argparse
import json
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, "/data/ComfyUI")
sys.path.insert(0, "/data/ComfyUI/custom_nodes/comfyui-tosvg")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import qa_gate
import svgnode

TOLS = [0.5, 1, 2, 3, 5, 8, 12, 20, 40]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="run/ic")
    ap.add_argument("--kit", default="brand-kit.example.json")
    ap.add_argument("--suffix", default="_flat")
    args = ap.parse_args()

    kit = json.loads(Path(args.kit).read_text(encoding="utf-8"))
    b = dict(kit["budget"])
    b["target_fill"] = kit["optical_fill"]
    b["grid"] = kit["grid"]
    d = Path(args.dir)
    sides = {}
    for p in sorted(d.glob(f"*{args.suffix}.svg")):
        sides[p.stem[: -len(args.suffix)]] = p.read_text(encoding="utf-8")

    node = svgnode.TS_SVGPathSimplify()
    vb = next(iter(sides.values()))
    import re
    side = float(re.search(r'viewBox="[^"]*"', vb).group(0).split()[-1].strip('"'))
    gperunit = kit["grid"] / side
    print(f"{len(sides)} assets, viewBox side {side:g} units -> 1 unit = {gperunit:.4f} grid px; "
          f"chamfer budget {b['max_chamfer_grid_px']} = {b['max_chamfer_grid_px']/gperunit:.1f} units\n")

    rows = []
    for tol in TOLS:
        ms = []
        for stem, svg in sides.items():
            try:
                res = node.simplify_svg_paths(svg, tol, False)
                out = res[0] if isinstance(res, (tuple, list)) else res
                if not isinstance(out, str) or "<svg" not in out:
                    print(f"  tol={tol} {stem}: unexpected return {type(res).__name__}/{type(out).__name__}")
                    out = svg
            except Exception as e:
                print(f"  tol={tol} {stem}: RAISED {type(e).__name__} {e}")
                out = svg
            ms.append(qa_gate.measure(d / f"{stem}_gt.png", out, b, kit["palette"]))
        ok = sum(1 for m in ms if m["verdict"] == "PASS")
        rows.append(dict(tol=tol, ok=ok, n=len(ms),
                         nodes_max=max(m["path_nodes"] for m in ms),
                         nodes_med=st.median(m["path_nodes"] for m in ms),
                         cham_max=max(m["chamfer_grid_px"] for m in ms),
                         haus_max=max(m["hausdorff_p95_grid_px"] for m in ms),
                         iou_min=min(m["alpha_iou"] for m in ms),
                         ssim_min=min(m["thumb_ssim_16"] for m in ms),
                         rmse_max=max(m["interior_rmse_vs_snapped"] for m in ms),
                         paths_max=max(m["paths"] for m in ms),
                         fails=sorted({f.split()[0] for m in ms for f in m["fails"]})))
        r = rows[-1]
        print(f"tol {tol:>5}  nodes max {r['nodes_max']:>5} med {r['nodes_med']:>5.0f}  "
              f"cham {r['cham_max']:.3f}  haus {r['haus_max']:.3f}  iou {r['iou_min']:.3f}  "
              f"ssim {r['ssim_min']:.3f}  rmseS {r['rmse_max']:5.1f}  pass {ok}/{len(ms)}  "
              f"{','.join(r['fails']) or '-'}", flush=True)

    print("\n" + f"{'tol':>6}{'nodes max':>11}{'nodes med':>11}{'cham max':>10}{'haus max':>10}"
          f"{'iou min':>9}{'ssim min':>10}{'rmseS max':>11}{'PASS':>7}  fails")
    print("-" * 104)
    for r in sorted(rows, key=lambda x: x["tol"]):
        print(f"{r['tol']:>6}{r['nodes_max']:>11}{r['nodes_med']:>11.0f}{r['cham_max']:>10.3f}"
              f"{r['haus_max']:>10.3f}{r['iou_min']:>9.3f}{r['ssim_min']:>10.3f}{r['rmse_max']:>11.1f}"
              f"{r['ok']:>4}/{r['n']:<2}  {','.join(r['fails']) or '-'}")


if __name__ == "__main__":
    main()
