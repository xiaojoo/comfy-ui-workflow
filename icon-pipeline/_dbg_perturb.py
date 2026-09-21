import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
import json
import xml.etree.ElementTree as ET

import numpy as np
import qa_gate

svg = Path("run/svg/default/gear.svg").read_text(encoding="utf-8")
print("has '<path ' :", "<path " in svg, "| count:", svg.count("<path "))
print("first path tag:", repr(svg[svg.index("<path"):svg.index("<path") + 70]))

n = qa_gate.perturb(svg, "nudge")
print("len clean/nudge:", len(svg), len(n), "| changed:", svg != n)
print("nudge head:", repr(n[n.index("<path"):n.index("<path") + 100]))
try:
    ET.fromstring(n)
    print("ET parse: OK")
except ET.ParseError as e:
    print("ET parse FAIL:", e)

kit = json.loads(Path("brand-kit.example.json").read_text(encoding="utf-8"))
for kind in ["clean", "nudge", "inflate"]:
    s = svg if kind == "clean" else qa_gate.perturb(svg, kind)
    a = qa_gate.rasterize(s)
    ys, xs = np.nonzero(a[..., 3] >= 128)
    m = qa_gate.measure(Path("run/gt/gear_gt.png"), s, kit["budget"], kit["palette"])
    print(f"{kind:8} xs[{xs.min()}..{xs.max()}] bboxOff={m['bbox_center_offset_pct']} edge={m['edge_error']} iou={m['alpha_iou']} forbidden={m['forbidden']}")
