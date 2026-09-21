"""Silhouette agreement between RenderMesh views of the same asset at different densities.

RenderMesh's IMAGE output on a black background carries no alpha, so the
silhouette is recovered as "not near-black". That derivation is identical for
every input, so pairwise comparison is fair even though the mask is inferred.
Reuses the icon gate's registration and distance code -- one ruler, two lines.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import PIL.Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qa_gate


def silhouette(png, mode="auto"):
    """mode=mask uses RenderMesh's own MASK output.

    The RGB-derived variant below is known-bad for shaded renders: `solid`
    shading has dark faces that fall under any global brightness threshold, so
    the "silhouette" tracks lighting, not geometry. Kept only for old captures.
    """
    im = PIL.Image.open(png)
    if mode == "mask":
        m = np.asarray(im.convert("L")) >= 128
        a = np.asarray(im.convert("RGB"), dtype=np.uint8)
        return qa_gate.crop_to_bbox_fill(np.dstack([a, (m * 255).astype(np.uint8)])), m.sum()
    a = np.asarray(im.convert("RGB"), dtype=np.int16)
    m = (a.sum(-1) > 40)
    rgba = np.dstack([a.astype(np.uint8), (m * 255).astype(np.uint8)])
    return qa_gate.crop_to_bbox_fill(rgba), m.sum()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="+")
    ap.add_argument("--ref", default=None)
    ap.add_argument("--mode", default="rgb", choices=["rgb", "mask"])
    args = ap.parse_args()

    # Key on the given path, not the basename: each run writes render_00001_.png
    # inside its own subfolder, so basenames collide.
    loaded = {}
    for p in args.images:
        s, fg = silhouette(Path(p), args.mode)
        loaded[str(p)] = (s, fg)
        print(f"{str(p):56} fg px {fg}")

    matches = [k for k in loaded if args.ref in k]
    if len(matches) != 1:
        sys.exit(f"--ref {args.ref!r} matched {len(matches)} inputs, need exactly 1")
    ref = matches[0]
    print(f"\nvs {ref} (bbox-registered)")
    print(f"{'candidate':56}{'IoU':>9}{'cham px':>10}{'haus95 px':>12}")
    for name, (s, _) in loaded.items():
        if name == ref:
            continue
        r, _ = loaded[ref]
        m1, m2 = r[..., 3] >= 128, s[..., 3] >= 128
        inter = np.logical_and(m1, m2).sum()
        union = np.logical_or(m1, m2).sum()
        iou = inter / union if union else 1.0
        ch, ha = qa_gate.silhouette_distance(m1, m2)
        print(f"{name:26}{iou:>9.4f}{ch:>10.3f}{ha:>12.3f}")


if __name__ == "__main__":
    main()
