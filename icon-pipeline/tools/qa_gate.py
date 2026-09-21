"""L6 quality gate: measures a produced SVG against its raster source.

Every threshold comes from brand-kit.budget. Run --selftest first: it perturbs a
passing SVG in ways that each target exactly one metric, and asserts the metric
moves. A gate whose ruler cannot discriminate is worse than no gate.
"""

import argparse
import json
import math
import re
import sys
from pathlib import Path

import cv2
import numpy as np
import pymupdf
import xml.etree.ElementTree as ET

SVG_NS = "http://www.w3.org/2000/svg"
RASTER = 512
CMD_RE = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]")
FILL_RE = re.compile(r'(?:\bfill="|fill:\s*)(#[0-9a-fA-F]{6})')


# ---------- colour science ----------
def srgb_to_lab(rgb):
    c = np.asarray(rgb, dtype=np.float64) / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124564, 0.3575761, 0.1804375],
                  [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    xyz = m @ c
    wp = np.array([0.95047, 1.0, 1.08883])
    v = xyz / wp
    v = np.where(v > 0.008856, np.cbrt(v), 7.787 * v + 16 / 116)
    x, y, z = v
    return np.array([116 * y - 16, 500 * (x - y), 200 * (y - z)])


def delta_e(hex_a, hex_b):
    a = srgb_to_lab([int(hex_a.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)])
    b = srgb_to_lab([int(hex_b.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)])
    return float(np.linalg.norm(a - b))


def ssim_gray(a, b, ksize=5, sigma=1.2):
    a = a.astype(np.float64)
    b = b.astype(np.float64)
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    k = (ksize, ksize)
    mu_a = cv2.GaussianBlur(a, k, sigma)
    mu_b = cv2.GaussianBlur(b, k, sigma)
    aa, bb, ab = mu_a * mu_a, mu_b * mu_b, mu_a * mu_b
    sa = cv2.GaussianBlur(a * a, k, sigma) - aa
    sb = cv2.GaussianBlur(b * b, k, sigma) - bb
    sab = cv2.GaussianBlur(a * b, k, sigma) - ab
    m = ((2 * mu_a * mu_b + c1) * (2 * sab + c2)) / ((aa + bb + c1) * (sa + sb + c2))
    return float(m.mean())


# ---------- svg ----------
def rasterize(svg_text, size=RASTER):
    root = re.search(r'<svg[^>]*\bwidth="([\d.]+)"', svg_text)
    vb = re.search(r'viewBox="([\d.\- ]+)"', svg_text)
    native = float(root.group(1)) if root else (float(vb.group(1).split()[2]) if vb else size)
    zoom = size / native
    doc = pymupdf.open(stream=svg_text.encode("utf-8"), filetype="svg")
    pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=True)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    return arr.copy()


def svg_structure(svg_text):
    paths = 0
    nodes = 0
    for m in re.finditer(r"<path\b[^>]*\bd=\"([^\"]+)\"", svg_text):
        paths += 1
        nodes += len(CMD_RE.findall(m.group(1)))
    tag_hits = {}
    try:
        tree = ET.fromstring(svg_text)
        for el in tree.iter():
            name = el.tag.split("}")[-1]
            if name in ("linearGradient", "radialGradient", "filter", "image", "clipPath", "mask", "foreignObject", "style"):
                tag_hits[name] = tag_hits.get(name, 0) + 1
    except ET.ParseError as e:
        tag_hits["PARSE_ERROR"] = str(e)[:80]
    colors = sorted({c.upper() for c in FILL_RE.findall(svg_text)})
    return paths, nodes, colors, tag_hits


# ---------- metrics ----------
def load_rgba(path, size=RASTER):
    import PIL.Image

    im = PIL.Image.open(path).convert("RGBA")
    if im.size != (size, size):
        im = im.resize((size, size), PIL.Image.Resampling.LANCZOS)
    return np.asarray(im).copy()


def on_white(rgb, alpha):
    a = alpha.astype(np.float64) / 255.0
    return rgb * a[..., None] + (1 - a[..., None]) * 255.0


def crop_to_bbox_fill(rgba, size=RASTER):
    """Register by content bounding box.

    Shape fidelity and canvas framing are different questions. Without this,
    re-centering an asset to spec reads as a 45% geometry regression, because
    the whole silhouette moved relative to the source frame.
    """
    ys, xs = np.nonzero(rgba[..., 3] >= 128)
    if not len(xs):
        return np.zeros((size, size, 4), np.uint8)
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    w, h = x1 - x0, y1 - y0
    side = max(w, h)
    canvas = np.zeros((side, side, 4), np.uint8)
    ox, oy = (side - w) // 2, (side - h) // 2
    canvas[oy:oy + h, ox:ox + w] = rgba[y0:y1, x0:x1]
    return cv2.resize(canvas, (size, size), interpolation=cv2.INTER_AREA)


def silhouette_distance(m_src, m_dst):
    """Symmetric chamfer + p95 hausdorff between two silhouettes, in raster px.

    A band-based binary mismatch rate was tried first and rejected: its noise
    floor measured 0.04-0.08 from anti-aliasing and sub-pixel registration alone,
    which makes it useless as a threshold. Distance transforms are stable.
    """
    fg_src = m_src.astype(np.uint8)
    fg_dst = m_dst.astype(np.uint8)
    dt_to_d = cv2.distanceTransform(1 - fg_dst, cv2.DIST_L2, 3)
    dt_to_s = cv2.distanceTransform(1 - fg_src, cv2.DIST_L2, 3)
    # Index with the bool masks only: a uint8 0/1 array is integer fancy-index,
    # which silently gathers rows instead of selecting pixels.
    a = dt_to_d[m_src & ~m_dst]
    b = dt_to_s[m_dst & ~m_src]
    if a.size == 0 and b.size == 0:
        return 0.0, 0.0
    allv = np.concatenate([a, b]) if a.size and b.size else (a if a.size else b)
    # A wholly missing shape puts the distance at the map's own scale; capping
    # keeps the reported number finite without hiding the failure (it lands on
    # the cap, far beyond any budget).
    allv = np.clip(allv, 0, RASTER)
    return float(allv.mean()), float(np.percentile(allv, 95))


def measure(source_png, svg_text, budget, palette):
    src_full = load_rgba(source_png)
    dst_full = rasterize(svg_text)
    src = crop_to_bbox_fill(src_full)
    dst = crop_to_bbox_fill(dst_full)
    s_a, d_a = src[..., 3], dst[..., 3]
    s_m = s_a >= 128
    d_m = d_a >= 128

    inter = np.logical_and(s_m, d_m).sum()
    union = np.logical_or(s_m, d_m).sum()
    iou = float(inter / union) if union else 1.0

    k = np.ones((7, 7), np.uint8)
    band = cv2.dilate(s_m.astype(np.uint8), k).astype(bool) & ~cv2.erode(s_m.astype(np.uint8), k).astype(bool)
    mismatch = float(np.logical_xor(s_m, d_m)[band].mean()) if band.any() else 0.0

    chamfer_px, haus_px = silhouette_distance(s_m, d_m)
    per_px = budget.get("grid", 24) / RASTER
    chamfer_grid, haus_grid = chamfer_px * per_px, haus_px * per_px

    interior = cv2.erode(s_m.astype(np.uint8), k).astype(bool)
    if interior.any():
        rmse = float(np.sqrt(((src[..., :3][interior].astype(float) - dst[..., :3][interior].astype(float)) ** 2).mean()))
    else:
        rmse = 0.0

    # Same comparison, but against the source with its own colours snapped to the
    # palette. Deliberate flattening must not be charged as a reproduction error;
    # this isolates vectoriser colour loss from the palette reduction we intend.
    tok = np.array([[int(t.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)] for t in palette.values()], float)
    px = src[..., :3][interior].astype(float)
    snapped = tok[((px[:, None, :] - tok[None, :, :]) ** 2).sum(-1).argmin(1)]
    rmse_snapped = float(np.sqrt(((snapped - dst[..., :3][interior].astype(float)) ** 2).mean())) if interior.any() else 0.0

    tiny = 16
    s_t = cv2.resize(on_white(src[..., :3], s_a), (tiny, tiny), interpolation=cv2.INTER_AREA)
    d_t = cv2.resize(on_white(dst[..., :3], d_a), (tiny, tiny), interpolation=cv2.INTER_AREA)
    thumb = ssim_gray(cv2.cvtColor(s_t.astype(np.uint8), cv2.COLOR_RGB2GRAY),
                      cv2.cvtColor(d_t.astype(np.uint8), cv2.COLOR_RGB2GRAY))

    ys, xs = np.nonzero(dst_full[..., 3] >= 128)
    s_ys, s_xs = np.nonzero(src_full[..., 3] >= 128)
    if len(xs):
        # Framing metrics stay in the deliverable's own canvas: this is what the
        # spec governs, and it is deliberately not bbox-registered.
        bbox_cx = (xs.min() + xs.max()) / 2
        bbox_cy = (ys.min() + ys.max()) / 2
        off = max(abs(bbox_cx - RASTER / 2), abs(bbox_cy - RASTER / 2)) / (RASTER / 2)
        centroid_off = max(abs(xs.mean() - RASTER / 2), abs(ys.mean() - RASTER / 2)) / (RASTER / 2)
        bw = (xs.max() - xs.min() + 1) / RASTER
        bh = (ys.max() - ys.min() + 1) / RASTER
    else:
        off, centroid_off, bw, bh = 1.0, 1.0, 0.0, 0.0
    src_fill = (max(s_xs.max() - s_xs.min(), s_ys.max() - s_ys.min()) + 1) / RASTER if len(s_xs) else 0.0

    paths, nodes, colors, forbidden = svg_structure(svg_text)

    worst_de, off_palette = 0.0, []
    for c in colors:
        best = min((delta_e(c, t) for t in palette.values()), default=999)
        worst_de = max(worst_de, best)
        if best > budget["max_delta_e"]:
            off_palette.append(f"{c}(dE={best:.1f})")

    da_full = dst_full[..., 3]
    corners = [int(da_full[0, 0]), int(da_full[0, -1]), int(da_full[-1, 0]), int(da_full[-1, -1])]
    fill = max(bw, bh)

    m = {
        "paths": paths,
        "path_nodes": nodes,
        "colors": len(colors),
        "max_delta_e": round(worst_de, 2),
        "off_palette": off_palette,
        "alpha_iou": round(iou, 4),
        "chamfer_grid_px": round(chamfer_grid, 3),
        "hausdorff_p95_grid_px": round(haus_grid, 3),
        "edge_mismatch": round(mismatch, 4),
        "interior_rmse": round(rmse, 2),
        "interior_rmse_vs_snapped": round(rmse_snapped, 2),
        "thumb_ssim_16": round(thumb, 4),
        "bbox_center_offset_pct": round(off * 100, 2),
        "centroid_offset_pct": round(centroid_off * 100, 2),
        "fill_ratio": round(fill, 3),
        "src_fill_ratio": round(src_fill, 3),
        "bbox_wh": [round(bw, 3), round(bh, 3)],
        "forbidden": {k: v for k, v in forbidden.items()},
        "corners_alpha": corners,
    }

    fails = []
    if paths > budget["max_paths"]:
        fails.append(f"paths {paths}>{budget['max_paths']}")
    if nodes > budget["max_path_nodes"]:
        fails.append(f"nodes {nodes}>{budget['max_path_nodes']}")
    if len(colors) > budget["max_colors"]:
        fails.append(f"colors {len(colors)}>{budget['max_colors']}")
    if worst_de > budget["max_delta_e"]:
        fails.append(f"dE {worst_de:.1f}>{budget['max_delta_e']}")
    if iou < budget["min_alpha_iou"]:
        fails.append(f"IoU {iou:.3f}<{budget['min_alpha_iou']}")
    if chamfer_grid > budget["max_chamfer_grid_px"]:
        fails.append(f"chamfer {chamfer_grid:.2f}>{budget['max_chamfer_grid_px']}")
    if haus_grid > budget["max_hausdorff_grid_px"]:
        fails.append(f"hausdorff {haus_grid:.2f}>{budget['max_hausdorff_grid_px']}")
    if rmse > budget["max_interior_rmse"]:
        fails.append(f"rmse {rmse:.1f}>{budget['max_interior_rmse']}")
    if thumb < budget["min_thumb_ssim_16"]:
        fails.append(f"ssim16 {thumb:.3f}<{budget['min_thumb_ssim_16']}")
    if off * 100 > budget["max_bbox_offset_pct"]:
        fails.append(f"offset {off*100:.1f}>{budget['max_bbox_offset_pct']}")
    target = budget.get("target_fill")
    if target and abs(fill - target) > budget["max_fill_deviation"]:
        fails.append(f"fill {fill:.3f} vs {target}+-{budget['max_fill_deviation']}")
    if forbidden:
        fails.append(f"forbidden {list(forbidden)}")
    if any(c != 0 for c in corners):
        fails.append(f"corners not transparent {corners}")

    m["verdict"] = "PASS" if not fails else "FAIL"
    m["fails"] = fails
    return m


# ---------- perturbations for the ruler self-test ----------
def _xform(svg, transform):
    # vtracer already puts transform="translate(..)" on every <path>, so a second
    # one there is a duplicate attribute and the original silently wins -- the
    # perturbation has to go on a wrapper group instead.
    idx = svg.index("<path")
    svg = svg[:idx] + f'<g transform="{transform}">' + svg[idx:]
    return svg.replace("</svg>", "</g></svg>", 1)


NUM_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def perturb(svg, kind):
    if kind == "color_drift":
        def shift(m):
            h = m.group(1)
            v = [max(0, min(255, int(h.lstrip('#')[i:i + 2], 16) + 9)) for i in (0, 2, 4)]
            return m.group(0).replace(h, "#%02X%02X%02X" % tuple(v))
        return FILL_RE.sub(shift, svg)
    if kind == "nudge":
        return _xform(svg, "translate(20,0)")
    if kind == "inflate":
        return _xform(svg, "translate(256,256) scale(1.07) translate(-256,-256)")
    if kind == "gradient":
        return svg.replace("<path", '<defs><linearGradient id="g"><stop offset="0" stop-color="#fff"/></linearGradient></defs><path', 1)
    if kind == "wobble":
        # Real shape damage: a crinkled outline, at the amplitude a reviewer
        # would actually reject -- milder jitter moves the metrics less than the
        # "worth rejecting" tolerance, and correctly does not trip the gate.
        # The counter is document-wide on purpose: resetting it per command hands
        # every command the same offsets, turning the jitter into a rigid
        # translation that bbox-registration erases -- the same trap as an
        # offset sequence whose period aligns with the point stride.
        state = {"i": 0}

        def rep(mm):
            i = state["i"]
            state["i"] += 1
            frac = ((i * 2654435761) % 997) / 997.0
            return f"{float(mm.group(0)) + (frac - 0.5) * 40:.2f}"

        def per_cmd(m):
            cmd, body = m.group(1), m.group(2)
            return cmd + (NUM_RE.sub(rep, body) if cmd != "Z" else body)

        return re.sub(r"\bd=\"([^\"]*)\"",
                      lambda d: 'd="' + re.sub(r"([MLCZ])([^MLCZ]*)", per_cmd, d.group(1)) + '"',
                      svg)
    if kind == "chip":
        pairs = [(len(CMD_RE.findall(m.group(1))), m.group(0))
                 for m in re.finditer(r'<path\b[^>]*\bd="([^"]*)"[^>]*/>', svg)]
        if not pairs:
            raise ValueError("no self-closed <path/> found to drop")
        return svg.replace(max(pairs)[1], "", 1)
    raise ValueError(kind)


VARIANTS = ["color_drift", "wobble", "chip", "nudge", "inflate", "gradient"]
AXIS = {"color_drift": "palette", "wobble": "shape", "chip": "shape",
        "nudge": "framing", "inflate": "framing", "gradient": "syntax"}
METRIC_ROWS = ["max_delta_e", "chamfer_grid_px", "hausdorff_p95_grid_px", "alpha_iou", "thumb_ssim_16",
               "paths", "bbox_center_offset_pct", "fill_ratio", "forbidden_count"]
# Smallest shift that means something for each metric, in that metric's own
# units. Ratios that live near 1.0 (IoU, SSIM) need tiny absolute tolerances --
# a percentage-of-value rule writes off a real 0.7% IoU fall as noise.
TOL = {"max_delta_e": 0.3, "chamfer_grid_px": 0.005, "hausdorff_p95_grid_px": 0.02,
       "alpha_iou": 0.003, "thumb_ssim_16": 0.002, "paths": 0.5,
       "bbox_center_offset_pct": 0.2, "fill_ratio": 0.005, "forbidden_count": 0.5}


# Each variant must move its own axis and must NOT move the others -- a gate where
# every knob moves every metric cannot tell you what to fix. Module-level so the
# CLI and the server assert against one shared list rather than two drifting ones.
CHECKS = [
    ("color_drift", "max_delta_e", "up", "palette"),
    ("color_drift", "chamfer_grid_px", "same", "shape"),
    ("wobble", "chamfer_grid_px", "up", "shape"),
    ("wobble", "hausdorff_p95_grid_px", "up", "shape"),
    ("wobble", "alpha_iou", "down", "shape"),
    ("wobble", "max_delta_e", "same", "palette"),
    ("chip", "paths", "down", "shape"),
    # no alpha_iou check for chip: in a stacked SVG a dropped layer gets
    # back-filled by the layer beneath, so the silhouette can survive it.
    ("chip", "thumb_ssim_16", "down", "shape"),
    ("nudge", "bbox_center_offset_pct", "up", "framing"),
    ("nudge", "chamfer_grid_px", "same", "shape"),
    ("nudge", "alpha_iou", "same", "shape"),
    ("inflate", "fill_ratio", "up", "framing"),
    ("inflate", "chamfer_grid_px", "same", "shape"),
    ("gradient", "forbidden_count", "up", "syntax"),
    ("gradient", "chamfer_grid_px", "same", "shape"),
]


def _val(r, key):
    return len(r["forbidden"]) if key == "forbidden_count" else r[key]


# The reported columns, in table order. One list: the CLI prints it, the API
# serialises it, and the viewer colours it. A second copy is where they drift.
COLUMNS = ["paths", "path_nodes", "colors", "max_delta_e", "alpha_iou", "chamfer_grid_px",
           "hausdorff_p95_grid_px", "interior_rmse", "interior_rmse_vs_snapped",
           "thumb_ssim_16", "bbox_center_offset_pct", "fill_ratio"]

# Which budget governs which reported column. Lives next to the checks that
# enforce it so the CLI, the API and any viewer read one table rather than
# each re-deriving the mapping -- a viewer guessing "max_" + column name gets
# fill_ratio and bbox_center_offset_pct wrong.
COLUMN_BUDGET = {
    "paths": ("max_paths", "max"),
    "path_nodes": ("max_path_nodes", "max"),
    "colors": ("max_colors", "max"),
    "max_delta_e": ("max_delta_e", "max"),
    "alpha_iou": ("min_alpha_iou", "min"),
    "chamfer_grid_px": ("max_chamfer_grid_px", "max"),
    "hausdorff_p95_grid_px": ("max_hausdorff_grid_px", "max"),
    "interior_rmse": ("max_interior_rmse", "max"),
    "thumb_ssim_16": ("min_thumb_ssim_16", "min"),
    "bbox_center_offset_pct": ("max_bbox_offset_pct", "max"),
    "fill_ratio": ("optical_fill", "band"),
}


def budget_for_column(col, budget):
    """Resolve a column to the limit it is judged against, or None if advisory."""
    spec = COLUMN_BUDGET.get(col)
    if not spec:
        return None
    key, bound = spec
    if bound == "band":
        target, dev = budget.get("target_fill"), budget.get("max_fill_deviation")
        return None if target is None else {"bound": bound, "target": target, "dev": dev}
    return None if key not in budget else {"bound": bound, "limit": budget[key]}


def column_checks(m, budget):
    """Per-column pass flags, derived from the same limits the verdict uses.

    The viewer colours cells from this rather than re-deriving the comparison:
    a second implementation of "is this within budget" is a second ruler, and
    the one place it can disagree with the verdict is a shipping decision.
    Every reported column gets a key; unjudged ones map to None so the viewer
    can tell "advisory" apart from "missing" instead of colouring it as a breach.
    """
    out = {}
    for col in COLUMNS:
        spec = budget_for_column(col, budget)
        v = m.get(col)
        if spec is None or v is None:
            out[col] = None
        elif spec["bound"] == "band":
            out[col] = abs(v - spec["target"]) <= spec["dev"] + 1e-9
        else:
            out[col] = v <= spec["limit"] + 1e-9 if spec["bound"] == "max" else v >= spec["limit"] - 1e-9
    return out


def selftest(source, svg_text, budget, palette):
    variants = {"clean": svg_text}
    for k in VARIANTS:
        variants[k] = perturb(svg_text, k)
    res = {k: measure(source, v, budget, palette) for k, v in variants.items()}

    print(f"{'metric':24}{'clean':>10}  " + "  ".join(f"{k:>13}" for k in VARIANTS))
    print("axis:                     (baseline)  " + "  ".join(f"{AXIS[k]:>13}" for k in VARIANTS))
    for key in METRIC_ROWS:
        print(f"{key:24}{_val(res['clean'], key):>10.4g}  " + "  ".join(f"{_val(res[k], key):>13.4g}" for k in VARIANTS))
    print(f"{'verdict':24}{res['clean']['verdict']:>10}  " + "  ".join(f"{res[k]['verdict']:>13}" for k in VARIANTS))

    # Each variant must move its own axis, and must NOT move the other axes --
    # a gate where every knob moves every metric cannot tell you what to fix.
    ok = True
    for kind, key, expect, axis in CHECKS:
        b, v = _val(res["clean"], key), _val(res[kind], key)
        tol = TOL.get(key, 0.0)
        if expect == "up":
            moved, tag = v > b + tol, "must rise "
        elif expect == "down":
            moved, tag = v < b - tol, "must fall "
        else:
            moved, tag = abs(v - b) <= 3 * tol, "must hold "
        ok = ok and moved
        print(f"  ruler {'OK ' if moved else 'BAD'} [{axis:7}] {tag} {kind:12} -> {key:24} {b:g} -> {v:g}")
    print(f"\nselftest: {'RULER LIVE AND AXIS-ORTHOGONAL' if ok else 'RULER UNTRUSTWORTHY - fix the gate before trusting any PASS'}")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kit", default=str(Path(__file__).resolve().parent.parent / "brand-kit.example.json"))
    ap.add_argument("--source")
    ap.add_argument("--svg")
    ap.add_argument("--dir", help="batch: dir holding *_gt.png and matching *.svg")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    kit = json.loads(Path(args.kit).read_text(encoding="utf-8"))
    budget, palette = kit["budget"], kit["palette"]
    budget["target_fill"] = kit["optical_fill"]
    budget["grid"] = kit["grid"]

    if args.selftest:
        src = Path(args.source)
        svg = Path(args.svg).read_text(encoding="utf-8")
        sys.exit(selftest(src, svg, budget, palette))

    if args.dir:
        rows = []
        d = Path(args.dir)
        for s in sorted(d.glob("*.svg")):
            gt = d / (s.stem.replace(".svg", "") + "_gt.png")
            if not gt.exists():
                continue
            rows.append((s.name, measure(gt, s.read_text(encoding="utf-8"), budget, palette)))
        hdr = (f"{'asset':26}{'paths':>6}{'nodes':>7}{'col':>5}{'dE':>6}{'IoU':>8}{'cham':>7}{'haus95':>8}{'rmse':>7}"
               f"{'ssim16':>8}{'bboxOff%':>9}{'fill':>7}{'verdict':>9}  fails")
        print(hdr)
        print("-" * len(hdr))
        passed = 0
        for name, r in rows:
            passed += r["verdict"] == "PASS"
            print(f"{name:26}{r['paths']:>6}{r['path_nodes']:>7}{r['colors']:>5}{r['max_delta_e']:>6}"
                  f"{r['alpha_iou']:>8}{r['chamfer_grid_px']:>7}{r['hausdorff_p95_grid_px']:>8}"
                  f"{r['interior_rmse']:>7}{r['thumb_ssim_16']:>8}"
                  f"{r['bbox_center_offset_pct']:>9}{r['fill_ratio']:>7}"
                  f"{r['verdict']:>9}  {', '.join(r['fails'])[:70]}")
        print("-" * len(hdr))
        print(f"{passed}/{len(rows)} PASS")
        out = d / "qa_report.json"
        out.write_text(json.dumps(dict(rows), indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"detail -> {out}")
        return

    if not args.source or not args.svg:
        ap.error("--source and --svg required (or --dir / --selftest)")
    r = measure(Path(args.source), Path(args.svg).read_text(encoding="utf-8"), budget, palette)
    print(json.dumps(r, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
