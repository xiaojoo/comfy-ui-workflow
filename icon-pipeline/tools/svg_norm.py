"""L5.5 SVG normaliser -- what turns a vtracer dump into a shippable icon.

vtracer emits no viewBox and one transform="translate(x,y)" per path. Icon build
pipelines (SVGO, Android VectorDrawable, Qt SVG, react-native-svg) treat per-path
transforms inconsistently, so they get baked into the path data. vtracer only ever
emits pure translate over absolute M/L/C/Z, which makes baking exactly lossless --
anything else raises rather than silently shifting geometry by a rounding error.
"""

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qa_gate

NUM = r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?"
TRANSLATE_RE = re.compile(r'^translate\(\s*(' + NUM + r")[, ]+(" + NUM + r")\s*\)$")
TRANSFORM_RE = re.compile(r'\btransform="([^"]*)"')
PATH_RE = re.compile(r'<path\b[^>]*/?>')
D_RE = re.compile(r'\bd="([^"]*)"')
CMD_RE = re.compile(r"([MLCZHVAQSTmlczhvaqst])([^MLCZHVAQSTmlczhvaqst]*)")


def bake_translate(svg_text):
    """Fold per-path translate() into absolute path coordinates."""
    baked = [0]
    for tag in PATH_RE.findall(svg_text):
        m = TRANSFORM_RE.search(tag)
        if not m:
            continue
        tm = TRANSLATE_RE.match(m.group(1).strip())
        if not tm:
            raise ValueError(f"unsupported transform, refusing to guess: {m.group(1)!r}")
        dx, dy = float(tm.group(1)), float(tm.group(2))
        new = tag

        def shift(dm):
            out = []
            for cmd, body in CMD_RE.findall(dm.group(1)):
                nums = [float(x) for x in re.findall(NUM, body)]
                if cmd in "HhVvAaQqTtSs":
                    raise ValueError(f"command {cmd!r} present; baking it is not lossless")
                if cmd.islower():
                    raise ValueError(f"relative command {cmd!r} present; cannot bake translate")
                shifted = []
                for i, v in enumerate(nums):
                    if i % 2 == 0:
                        v += dx
                    else:
                        v += dy
                    shifted.append(f"{v:.3f}".rstrip("0").rstrip("."))
                out.append(cmd + " ".join(shifted))
            return 'd="' + " ".join(out) + '"'

        new = D_RE.sub(shift, new, count=1)
        new = new.replace(m.group(0), "")
        new = re.sub(r"\s+/?>", "/>", new)
        new = re.sub(r"\s{2,}", " ", new)
        svg_text = svg_text.replace(tag, new, 1)
        baked[0] += 1

    left = TRANSFORM_RE.findall(svg_text)
    if left:
        raise ValueError(f"{len(left)} transform attr(s) survived baking")
    ET.fromstring(svg_text)
    return svg_text, baked[0]


HEADER_RE = re.compile(r"<svg\b[^>]*>")


def native_width(svg_text):
    m = re.search(r'<svg\b[^>]*\bwidth="([\d.]+)"', svg_text)
    if m:
        return float(m.group(1))
    m = re.search(r'viewBox="([\d.\- ]+)"', svg_text)
    return float(m.group(1).split()[2]) if m else float(qa_gate.RASTER)


def content_bbox(svg_text, size=qa_gate.RASTER):
    """Content box in the SVG's own user units.

    The raster is rendered at `size`, which is not the native width once the
    source image is anything other than `size` px -- vtracer writes the real
    pixel width, so 512-space measurements must be scaled back or the viewBox
    lands at the wrong magnitude.
    """
    a = qa_gate.rasterize(svg_text, size)
    ys, xs = np.nonzero(a[..., 3] >= 128)
    if not len(xs):
        raise ValueError("svg rasterises to nothing")
    k = native_width(svg_text) / size
    return (int(xs.min() * k), int(ys.min() * k),
            int((xs.max() - xs.min() + 1) * k), int((ys.max() - ys.min() + 1) * k))


def normalise(svg_text, kit):
    grid, fill = kit["grid"], kit["optical_fill"]
    svg_text, n = bake_translate(svg_text)
    svg_text = re.sub(r"<\?xml[^>]*\?>|<!--.*?-->", "", svg_text, flags=re.S).strip()
    x, y, w, h = content_bbox(svg_text)
    side = max(w, h) / fill
    cx, cy = x + w / 2, y + h / 2
    vb = f"{cx - side / 2:.4g} {cy - side / 2:.4g} {side:.4g} {side:.4g}"
    head = HEADER_RE.search(svg_text).group(0)
    new = re.sub(r'\b(width|height|viewBox)="[^"]*"', "", head)
    new = re.sub(r"\s+", " ", new).strip().rstrip(">")
    new = f'<svg xmlns="http://www.w3.org/2000/svg" width="{grid}" height="{grid}" viewBox="{vb}">'
    return svg_text.replace(head, new, 1).strip(), vb, n, (x, y, w, h)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--kit", default=str(Path(__file__).resolve().parent.parent / "brand-kit.example.json"))
    args = ap.parse_args()

    kit = json.loads(Path(args.kit).read_text(encoding="utf-8"))
    d = Path(args.dir)
    rows = []
    for s in sorted(p for p in d.glob("*.svg") if not p.name.endswith("_norm.svg")):
        gt = d / (s.stem + "_gt.png")
        if not gt.exists():
            continue
        raw = s.read_text(encoding="utf-8")
        norm, vb, n, bbox = normalise(raw, kit)
        s.with_name(s.stem + "_norm.svg").write_text(norm, encoding="utf-8")
        rows.append((s.name, n, vb,
                     qa_gate.measure(gt, raw, kit["budget"], kit["palette"]),
                     qa_gate.measure(gt, norm, kit["budget"], kit["palette"])))

    hdr = (f"{'asset':22}{'baked':>6}{'bboxOff% b/a':>16}{'fill b/a':>14}{'cham b/a':>15}"
           f"{'IoU b/a':>18}{'bytes b/a':>14}{'verdict b/a':>16}")
    print(hdr)
    print("-" * len(hdr))
    fixed = broken = 0
    for name, n, vb, b, a in rows:
        fixed += b["verdict"] == "FAIL" and a["verdict"] == "PASS"
        broken += b["verdict"] == "PASS" and a["verdict"] == "FAIL"
        raw_sz = len((d / name).read_bytes())
        nrm_sz = len((d / name.replace(".svg", "_norm.svg")).read_bytes())
        print(f"{name:22}{n:>6}{b['bbox_center_offset_pct']:>7}/{a['bbox_center_offset_pct']:<8}"
              f"{b['fill_ratio']:>6.2f}/{a['fill_ratio']:<7.2f}"
              f"{b['chamfer_grid_px']:>6.3f}/{a['chamfer_grid_px']:<7.3f}"
              f"{b['alpha_iou']:>8.3f}/{a['alpha_iou']:<9.3f}"
              f"{raw_sz:>6}/{nrm_sz:<6}{b['verdict']:>6}/{a['verdict']:<9}")
    print("-" * len(hdr))
    pb = sum(1 for *_, b, _ in rows if b["verdict"] == "PASS")
    pa = sum(1 for *_, _, a in rows if a["verdict"] == "PASS")
    print(f"PASS {pb}/{len(rows)} -> {pa}/{len(rows)}   (repaired {fixed}, regressed {broken})")


if __name__ == "__main__":
    main()
