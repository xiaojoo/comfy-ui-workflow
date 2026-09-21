"""L1: generate an on-domain icon test set.

The gate's thresholds were calibrated on synthetic hard-edge shapes; they can only
be re-checked against real model output, and that output has to actually be icons
rather than the full-bleed artwork that happened to be sitting in output/.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_graph

STYLE = ("flat vector app icon, one single centered object, solid pure white background, "
         "two or three flat colors, thick clean geometry, sharp corners, no text, "
         "no gradient, no shadow, no outline noise, high contrast, product icon style")

SUBJECTS = {
    "gear": "a settings gear wheel with six teeth and a hollow centre",
    "bell": "a notification bell with a small clapper underneath",
    "shield": "a security shield with a checkmark inside",
    "cloud": "a rounded cloud with an upward arrow rising out of it",
    "arrow_up": "a bold upward arrow with a wide head and short shaft",
    "hex_badge": "a hexagonal badge with a star cut out of its centre",
    "trash": "a trash can with a hinged lid and three vertical ribs",
    "folder": "an open file folder with a sheet of paper rising out of it",
}

GRAPH = json.loads((Path(__file__).resolve().parents[1] / "workflows" / "gen_icon.json")
                   .read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=list(SUBJECTS))
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--prefix-dir", default="icons")
    # Default to whatever gen_icon.json already names -- the measured pair is
    # int8+fp8_mixed at 11.0 GiB, and bf16+qwen_3_4b is 18.9 GiB against a 15.5 GiB
    # WSL ceiling, which wedges the distro rather than erroring.
    ap.add_argument("--unet", default=None)
    ap.add_argument("--clip", default=None)
    args = ap.parse_args()

    if args.unet:
        GRAPH["66"]["inputs"]["unet_name"] = args.unet
    if args.clip:
        GRAPH["62"]["inputs"]["clip_name"] = args.clip
    args.unet = GRAPH["66"]["inputs"]["unet_name"]
    args.clip = GRAPH["62"]["inputs"]["clip_name"]
    roots = {"u": "/data/ComfyUI/models/diffusion_models", "c": "/data/ComfyUI/models/text_encoders"}

    def giB(which, name):
        return Path(roots[which], name).stat().st_size / 2**30

    u, c = giB("u", args.unet), giB("c", args.clip)
    print(f"weights: unet {u:.2f} GiB + clip {c:.2f} GiB = {u+c:.2f} GiB against a 15.5 GiB cap\n")

    for slug in args.only:
        g = json.loads(json.dumps(GRAPH))
        g["67"]["inputs"]["text"] = f"{SUBJECTS[slug]}, {STYLE}"
        g["70"]["inputs"]["seed"] = args.seed
        g["9"]["inputs"]["filename_prefix"] = f"{args.prefix_dir}/{slug}"
        r = run_graph.post(g, "icon-gen")
        if "error" in r:
            print(f"{slug:12} REJECTED {json.dumps(r.get('error') or r.get('node_errors'))[:500]}")
            continue
        pid = r["prompt_id"]
        st, _, el = run_graph.wait(pid, timeout=600)
        print(f"{slug:12} {el:5.1f}s  {st}")


if __name__ == "__main__":
    main()
