"""L5.6 vector-side palette reduction.

Real model output is anti-aliased gradient art, so vtracer faithfully emits
hundreds of paths and a hundred-odd colours. Reducing the raster first destroys
alpha (measured); reducing the vectors does not. Run this after svg_norm, when
path data is already in absolute user units with no per-path transform.

Three operations, each independently switchable because each trades a different
fidelity metric for budget:

  --snap      every fill -> nearest brand palette entry. Drives max_delta_e to
              0 by construction; costs interior_rmse, which is the real price.
  --group     merge same-colour paths into one multi-subpath <path>. Collapses
              path count to <= palette size, but reorders stacking, so it is the
              operation most likely to break occlusion -- measured, not assumed.
  --min-area  drop speckle paths. Bounding-box area, not true area: control
              points over-extend curved paths, so this over-estimates and is
              conservative about what it deletes.
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qa_gate
import svg_norm

PATH_RE = re.compile(r"<path\b[^>]*/?>")
D_RE = re.compile(r'\bd="([^"]*)"')
FILL_RE = re.compile(r'\bfill="(#[0-9a-fA-F]{6})"')
NUM_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def snap_color(hexv, palette):
    best, bd = None, 1e9
    for name, tok in palette.items():
        d = qa_gate.delta_e(hexv, tok)
        if d < bd:
            best, bd = tok, d
    return best, bd


def bbox_area_fraction(d, canvas):
    nums = [float(x) for x in NUM_RE.findall(d)]
    if len(nums) < 4:
        return 0.0
    xs, ys = nums[0::2], nums[1::2]
    w = max(xs) - min(xs)
    h = max(ys) - min(ys)
    return max(0.0, w) * max(0.0, h) / (canvas * canvas)


def flatten(svg_text, kit, snap=True, group=True, min_area=0.0):
    palette = kit["palette"]
    vb = re.search(r'viewBox="([^"]+)"', svg_text)
    canvas = float(vb.group(1).split()[2]) if vb else svg_norm.native_width(svg_text)
    drift = {}
    kept = []

    for tag in PATH_RE.findall(svg_text):
        dm, fm = D_RE.search(tag), FILL_RE.search(tag)
        if not dm or not fm:
            kept.append(tag)
            continue
        if min_area and bbox_area_fraction(dm.group(1), canvas) < min_area:
            drift.setdefault("dropped", 0)
            drift["dropped"] = drift.get("dropped", 0) + 1
            continue
        fill = fm.group(1)
        new = tag
        if snap:
            tok, d = snap_color(fill, palette)
            new = new.replace(fm.group(0), f'fill="{tok}"')
            drift[fill.upper()] = round(max(drift.get(fill.upper(), 0), d), 2)
        kept.append(new)

    if group:
        order, buckets = [], {}
        plain = []
        for tag in kept:
            fm = FILL_RE.search(tag)
            dm = D_RE.search(tag)
            if not fm or not dm:
                plain.append(tag)
                continue
            c = fm.group(1).upper()
            if c not in buckets:
                buckets[c] = []
                order.append(c)
            buckets[c].append(dm.group(1))
        kept = plain + [
            f'<path d="{" ".join(buckets[c])}" fill="{c}" fill-rule="nonzero" stroke="none"/>'
            for c in order
        ]

    head_end = svg_text.index(">") + 1
    body = "".join(kept)
    return svg_text[:head_end] + "\n" + body + "</svg>", drift


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--kit", default=str(Path(__file__).resolve().parent.parent / "brand-kit.example.json"))
    ap.add_argument("--min-area", type=float, default=0.0)
    ap.add_argument("--no-snap", action="store_true")
    ap.add_argument("--no-group", action="store_true")
    ap.add_argument("--in-suffix", default="_norm")
    ap.add_argument("--out-suffix", default="_flat")
    args = ap.parse_args()

    kit = json.loads(Path(args.kit).read_text(encoding="utf-8"))
    b = dict(kit["budget"])
    b["target_fill"] = kit["optical_fill"]
    b["grid"] = kit["grid"]
    d = Path(args.dir)

    rows = []
    for src in sorted(p for p in d.glob(f"*{args.in_suffix}.svg")):
        stem = src.name[: -len(args.in_suffix + ".svg")]
        gt = d / f"{stem}_gt.png"
        if not gt.exists():
            continue
        before = src.read_text(encoding="utf-8")
        after, drift = flatten(before, kit, not args.no_snap, not args.no_group, args.min_area)
        out = d / f"{stem}{args.out_suffix}.svg"
        out.write_text(after, encoding="utf-8")
        rows.append((
            out.name,
            qa_gate.measure(gt, before, b, kit["palette"]),
            qa_gate.measure(gt, after, b, kit["palette"]),
            len(drift), drift.get("dropped", 0),
        ))

    hdr = (f"{'asset':26}{'paths b/a':>13}{'col b/a':>11}{'nodes b/a':>15}{'dE b/a':>13}"
           f"{'cham b/a':>15}{'IoU b/a':>16}{'rmse b/a':>14}{'rmseSnapped b/a':>19}{'ssim b/a':>15}{'verdict b/a':>15}")
    print(hdr)
    print("-" * len(hdr))
    pb = pa = 0
    for name, bf, af, ncol, dropped in rows:
        pb += bf["verdict"] == "PASS"
        pa += af["verdict"] == "PASS"
        print(f"{name:26}{bf['paths']:>5}/{af['paths']:<7}{bf['colors']:>4}/{af['colors']:<5}"
              f"{bf['path_nodes']:>6}/{af['path_nodes']:<8}{bf['max_delta_e']:>5.1f}/{af['max_delta_e']:<6.1f}"
              f"{bf['chamfer_grid_px']:>6.3f}/{af['chamfer_grid_px']:<7.3f}"
              f"{bf['alpha_iou']:>7.3f}/{af['alpha_iou']:<8.3f}"
              f"{bf['interior_rmse']:>5.1f}/{af['interior_rmse']:<7.1f}"
              f"{bf['interior_rmse_vs_snapped']:>8.1f}/{af['interior_rmse_vs_snapped']:<9.1f}"
              f"{bf['thumb_ssim_16']:>6.3f}/{af['thumb_ssim_16']:<8.3f}"
              f"{bf['verdict'][:3]:>6}/{af['verdict']:<8}")
    print("-" * len(hdr))
    print(f"PASS {pb}/{len(rows)} -> {pa}/{len(rows)}")


if __name__ == "__main__":
    main()
