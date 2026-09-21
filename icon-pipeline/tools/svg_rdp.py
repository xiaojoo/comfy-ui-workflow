"""Per-subpath Ramer-Douglas-Peucker over the flattened deliverable.

Written because TS_SVGPathSimplify destroys geometry: it flattens every command
of a path into one point list, which bridges separate subpaths and degrades
Beziers into vertices. Two rules make this one safe, and both are asserted at
runtime rather than relied upon:

  1. every M...Z subpath is simplified on its own -- nothing is ever connected
     to a different island or hole;
  2. a path containing any command other than M/L/Z raises instead of silently
     converting curves, since converting them is a geometry change, not a
     simplification.

Closed rings are RDP'd with the first point re-appended so the seam cannot drift.

--sweep prints the tolerance/node/fidelity trade-off, which is the point of the
exercise: the usable tolerance is bounded by the chamfer budget, not by taste.
"""

import argparse
import json
import math
import re
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qa_gate

PATH_RE = re.compile(r"<path\b[^>]*/?>")
D_RE = re.compile(r'\bd="([^"]*)"')
# Everything the rebuild cannot express losslessly: curve/shortcut commands in
# either case, plus relative m/l/z, since emitting absolute coordinates for those
# would change the geometry rather than simplify it.
OTHER_CMD_RE = re.compile(r"[CSTQAHVcstqahvmlz]")
SUBPATH_RE = re.compile(r"M\s*([-\d.]+)[\s,]+([-\d.]+)(.*?)(?=M[-\d.\s,]|$)", re.S)


def rdp(points, eps):
    if len(points) < 3:
        return points
    start, end = points[0], points[-1]
    dmax, idx = -1.0, 0
    for i in range(1, len(points) - 1):
        d = perp(points[i], start, end)
        if d > dmax:
            dmax, idx = d, i
    if dmax > eps:
        a = rdp(points[:idx + 1], eps)
        b = rdp(points[idx:], eps)
        return a[:-1] + b
    return [start, end]


def perp(p, a, b):
    x0, y0 = p
    x1, y1 = a
    x2, y2 = b
    dx, dy = x2 - x1, y2 - y1
    n = math.hypot(dx, dy)
    if n == 0:
        return math.hypot(x0 - x1, y0 - y1)
    return abs(dy * x0 - dx * y0 + x2 * y1 - y2 * x1) / n


def simplify_d(d, eps):
    total = kept = 0
    out = []
    for m in SUBPATH_RE.finditer(d):
        x, y = float(m.group(1)), float(m.group(2))
        body = m.group(3)
        nums = [float(v) for v in re.findall(r"[-+]?\d*\.?\d+", body)]
        pts = [(x, y)] + [(nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]
        closed = "Z" in body.upper()
        total += len(pts)
        ring = pts + [pts[0]] if closed and pts[0] != pts[-1] else pts
        simp = rdp(ring, eps)
        if closed and len(simp) > 1 and simp[0] == simp[-1]:
            simp = simp[:-1]
        kept += len(simp)
        out.append("M " + " L ".join(f"{px:.2f} {py:.2f}" for px, py in simp) + (" Z" if closed else ""))
    return " ".join(out), total, kept


def simplify(svg_text, eps):
    if OTHER_CMD_RE.search("".join(D_RE.findall(svg_text))):
        raise ValueError("path data contains non-M/L/Z commands; refusing to convert curves")
    tot = kep = 0
    def sub(m):
        nonlocal tot, kep
        d = m.group(1)
        new, t, k = simplify_d(d, eps)
        if "M" not in new:
            raise ValueError(f"parsed no subpath out of d={d[:60]!r}")
        tot += t
        kep += k
        return f'd="{new}"'
    body = D_RE.sub(sub, svg_text)
    return body, tot, kep


def sweep(d, kit, b, eps_list):
    files = sorted(p for p in d.glob("*_flat.svg"))
    stems = [p.name[: -len("_flat.svg")] for p in files]
    srcs = {s: (d / f"{s}_flat.svg").read_text(encoding="utf-8") for s in stems}
    print(f"{len(stems)} assets, starting from *_flat.svg\n")
    rows = []
    for eps in eps_list:
        ms = []
        failed = None
        for s in stems:
            try:
                out, _, _ = simplify(srcs[s], eps)
            except ValueError as e:
                failed = str(e)
                out = srcs[s]
            ms.append(qa_gate.measure(d / f"{s}_gt.png", out, b, kit["palette"]))
        r = dict(eps=eps, ok=sum(m["verdict"] == "PASS" for m in ms), n=len(ms),
                 nodes_max=max(m["path_nodes"] for m in ms),
                 nodes_med=st.median(m["path_nodes"] for m in ms),
                 cham_max=max(m["chamfer_grid_px"] for m in ms),
                 haus_max=max(m["hausdorff_p95_grid_px"] for m in ms),
                 iou_min=min(m["alpha_iou"] for m in ms),
                 ssim_min=min(m["thumb_ssim_16"] for m in ms),
                 fails=sorted({f.split()[0] for m in ms for f in m["fails"]}), err=failed)
        rows.append(r)
        print(f"eps {eps:>5}  nodes max {r['nodes_max']:>5} med {r['nodes_med']:>5.0f}  "
              f"cham {r['cham_max']:.3f}  haus {r['haus_max']:.3f}  iou {r['iou_min']:.3f}  "
              f"ssim {r['ssim_min']:.3f}  pass {r['ok']}/{r['n']}  "
              f"{','.join(r['fails']) or '-'}{'' if not r['err'] else '  [REFUSED: ' + r['err'] + ']'}", flush=True)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="run/ic")
    ap.add_argument("--kit", default="brand-kit.example.json")
    ap.add_argument("--eps", type=float, default=None)
    ap.add_argument("--in-suffix", default="_flat")
    ap.add_argument("--out-suffix", default="_rdp")
    ap.add_argument("--sweep", default="0,0.5,1,1.5,2,2.5,3,4,6,10")
    args = ap.parse_args()

    kit = json.loads(Path(args.kit).read_text(encoding="utf-8"))
    b = dict(kit["budget"])
    b["target_fill"] = kit["optical_fill"]
    b["grid"] = kit["grid"]
    d = Path(args.dir)

    if args.eps is not None:
        for p in sorted(d.glob(f"*{args.in_suffix}.svg")):
            stem = p.name[: -len(args.in_suffix + ".svg")]
            out, tot, kep = simplify(p.read_text(encoding="utf-8"), args.eps)
            (d / f"{stem}{args.out_suffix}.svg").write_text(out, encoding="utf-8")
            m = qa_gate.measure(d / f"{stem}_gt.png", out, b, kit["palette"])
            print(f"{stem:26} verts {tot:>6}->{kep:<6} nodes {m['path_nodes']:>5} "
                  f"cham {m['chamfer_grid_px']:.3f} iou {m['alpha_iou']:.3f} "
                  f"ssim {m['thumb_ssim_16']:.3f} {m['verdict']}  {','.join(m['fails'])[:56]}")
        return

    sweep(d, kit, b, [float(x) for x in args.sweep.split(",")])


if __name__ == "__main__":
    main()
