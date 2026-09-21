import re
import sys
from pathlib import Path

import numpy as np
import pymupdf

BASE = ('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
        '<rect x="10" y="10" width="20" height="20" fill="#FF0000"/></svg>')


def bbox_of(svg, size=200):
    doc = pymupdf.open(stream=svg.encode(), filetype="svg")
    pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(size / 100, size / 100), alpha=True)
    a = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
    red = (a[..., 0] > 150) & (a[..., 1] < 90)
    ys, xs = np.nonzero(red)
    return None if not len(xs) else (round(xs.min() / pix.width, 3), round(xs.max() / pix.width, 3))


print("expect norm 0.10..0.30 ; nudged 0.40..0.60")
print("  g_transform_real ", bbox_of(BASE.replace('<rect ', '<g transform="translate(30,0)"><rect ')
                                     .replace("/>", "/></g>")))
print("  matrix_on_g      ", bbox_of(BASE.replace('<rect ', '<g transform="matrix(1,0,0,1,30,0)"><rect ')
                                     .replace("/>", "/></g>")))
print("  g_scale2         ", bbox_of(BASE.replace('<rect ', '<g transform="scale(2)"><rect ').replace("/>", "/></g>")))

print("\n=== transform attrs across produced svgs ===")
pat = re.compile(r'transform="([^"]*)"')
names = re.compile(r"<(\w+)[^>]*\btransform=")
for p in sorted(Path("run/svg").glob("*/*.svg")):
    t = p.read_text(encoding="utf-8")
    vals = pat.findall(t)
    kinds = {}
    for v in vals:
        kinds[re.sub(r"[-\d.,]+", "n", v)] = kinds.get(re.sub(r"[-\d.,]+", "n", v), 0) + 1
    owners = {}
    for m in names.finditer(t):
        owners[m.group(1)] = owners.get(m.group(1), 0) + 1
    rel = t.count(" M") + len(re.findall(r"[a-z]", re.sub(r"<[^>]+>", "", t)))
    if p.parent.name in ("default", "polygon"):
        print(f"  {p.parent.name:9} {p.name:18} n={len(vals)} owners={owners} shapes={kinds}")
