"""L5 vectoriser + parameter sweep.

vtracer for multi-colour icons, potrace for monochrome. The sweep exists because
"vectorised" is not a pass/fail state: corner_threshold and filter_speckle trade
path count against edge fidelity, so the gate has to be run per setting.
"""

import argparse
import subprocess
import sys
from pathlib import Path

import vtracer


def run_vtracer(png, out_svg, preset):
    vtracer.convert_image_to_svg_py(str(png), str(out_svg), colormode="color", **preset)
    return Path(out_svg).read_text(encoding="utf-8")


PRESETS = {
    "tight": dict(hierarchical="stacked", mode="spline", filter_speckle=2, color_precision=6,
                  layer_difference=16, corner_threshold=80, length_threshold=2.0,
                  max_iterations=10, splice_threshold=45, path_precision=2),
    "default": dict(hierarchical="stacked", mode="spline", filter_speckle=4, color_precision=6,
                    layer_difference=16, corner_threshold=60, length_threshold=4.0,
                    max_iterations=10, splice_threshold=45, path_precision=3),
    "coarse": dict(hierarchical="stacked", mode="spline", filter_speckle=8, color_precision=4,
                   layer_difference=32, corner_threshold=40, length_threshold=8.0,
                   max_iterations=6, splice_threshold=45, path_precision=2),
    "polygon": dict(hierarchical="stacked", mode="polygon", filter_speckle=4, color_precision=5,
                    layer_difference=24, corner_threshold=60, length_threshold=4.0,
                    max_iterations=10, splice_threshold=45, path_precision=2),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--presets", default="tight,default,coarse,polygon")
    ap.add_argument("--gate", default=str(Path(__file__).resolve().parent / "qa_gate.py"))
    ap.add_argument("--kit", default=str(Path(__file__).resolve().parent.parent / "brand-kit.example.json"))
    args = ap.parse_args()

    indir, outdir = Path(args.in_dir), Path(args.out_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    py = sys.executable

    made = []
    for preset in args.presets.split(","):
        p = PRESETS[preset.strip()]
        sub = outdir / preset.strip()
        sub.mkdir(exist_ok=True)
        for gt in sorted(indir.glob("*_gt.png")):
            name = gt.name.replace("_gt.png", "")
            svg_path = sub / f"{name}.svg"
            run_vtracer(gt, svg_path, p)
            (sub / f"{name}_gt.png").write_bytes(gt.read_bytes())
            made.append((preset.strip(), name, svg_path))
        print(f"[{preset.strip()}] {len([m for m in made if m[0]==preset.strip()])} svg -> {sub}")

    print()
    for preset in args.presets.replace(" ", "").split(","):
        sub = outdir / preset.strip()
        print(f"===== preset: {preset.strip()} =====")
        subprocess.run([py, args.gate, "--kit", args.kit, "--dir", str(sub)], check=False)


if __name__ == "__main__":
    main()
