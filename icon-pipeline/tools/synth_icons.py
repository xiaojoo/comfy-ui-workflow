"""Ground-truth flat icons: exact palette, exact alpha, no photographic noise.

The QA gate is only trustworthy if it is scored against something whose true
values are known, so the ruler gets calibrated here rather than on model output.
"""

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 512


def new_canvas():
    return Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))


def settings_icon(pal):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    cx = cy = SIZE // 2
    teeth = 8
    import math

    outer, inner = 200, 150
    pts = []
    for i in range(teeth * 2):
        r = outer if i % 2 == 0 else inner
        a = math.pi * i / teeth
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    d.polygon(pts, fill=pal)
    d.ellipse([cx - 60, cy - 60, cx + 60, cy + 60], fill=(0, 0, 0, 0))
    return im


def bell_icon(pal, accent):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    d.pieslice([96, 96, 416, 416], 180, 360, fill=pal)
    d.rectangle([96, 256, 416, 380], fill=pal)
    d.ellipse([226, 380, 286, 440], fill=accent)
    d.rectangle([244, 60, 268, 100], fill=pal)
    return im


def shield_icon(pal, dark):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    d.polygon([(256, 56), (432, 128), (432, 268), (256, 456), (80, 268), (80, 128)], fill=pal)
    d.polygon([(256, 116), (380, 166), (380, 258), (256, 396), (132, 258), (132, 166)], fill=dark)
    return im


def cloud_icon(pal):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    d.ellipse([120, 200, 260, 340], fill=pal)
    d.ellipse([200, 140, 372, 312], fill=pal)
    d.ellipse([280, 208, 424, 344], fill=pal)
    d.rectangle([160, 280, 384, 344], fill=pal)
    return im


def monochrome_arrow(pal):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    d.polygon([(256, 88), (424, 280), (332, 280), (332, 424), (180, 424), (180, 280), (88, 280)], fill=pal)
    return im


def hex_badge(pal, accent, neutral):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    import math

    cx = cy = 256
    pts = [(cx + 210 * math.cos(math.pi / 3 * i + math.pi / 6), cy + 210 * math.sin(math.pi / 3 * i + math.pi / 6)) for i in range(6)]
    d.polygon(pts, fill=neutral)
    d.polygon([(cx + 150 * math.cos(math.pi / 3 * i + math.pi / 6), cy + 150 * math.sin(math.pi / 3 * i + math.pi / 6)) for i in range(6)], fill=pal)
    d.ellipse([216, 216, 296, 296], fill=accent)
    return im


def main():
    kit = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    p = kit["palette"]

    jobs = {
        "gear": lambda: settings_icon(p["brand/primary"]),
        "bell": lambda: bell_icon(p["brand/primary"], p["brand/accent"]),
        "shield": lambda: shield_icon(p["brand/primary"], p["brand/primary-dark"]),
        "cloud": lambda: cloud_icon(p["brand/neutral"]),
        "arrow_mono": lambda: monochrome_arrow(p["brand/neutral"]),
        "hex_badge": lambda: hex_badge(p["brand/success"], p["brand/accent"], p["brand/neutral"]),
    }
    manifest = {}
    for name, fn in jobs.items():
        im = fn()
        path = out / f"{name}_gt.png"
        im.save(path)
        alphas = {px[3] for px in im.getdata()}
        colors = {"#%02X%02X%02X" % c[:3] for c in im.getdata() if c[3] == 255}
        manifest[name] = {"file": path.name, "true_colors": sorted(colors), "alpha_levels": sorted(alphas)}
    (out / "gt_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    for k, v in manifest.items():
        print(f"{k:12} colors={len(v['true_colors'])} alpha_levels={v['alpha_levels']} {v['true_colors']}")


if __name__ == "__main__":
    main()
