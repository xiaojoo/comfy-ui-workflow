"""Keypoints for one or more images, as JSON on stdout, using the engine's own SDPose weights.

Run inside the distro with ComfyUI's venv, passing the images in POSE_IMAGES (space
separated, use /mnt/h/... for files on the Windows drive):

    POSE_IMAGES=/mnt/h/workflow/.probe/shot/x.png /data/ComfyUI/venv/bin/python \\
        /mnt/h/workflow/icon-pipeline/tools/pose_keys.py

Why not through the engine's graph: SDPose's POSE_KEYPOINT is a custom type, and linking
it to a text writer is silently dropped at validation -- the run reports success with no
keypoints in it. A ruler that reports nothing and looks green is worse than no ruler.

The image list comes from the environment, not argv: ComfyUI parses argv with argparse on
import, and would refuse to start on our own arguments.
"""
import json
import os
import sys
from pathlib import Path

COMFY = "/data/ComfyUI"
if COMFY not in sys.path:
    sys.path.insert(0, COMFY)

import numpy as np  # noqa: E402
import torch  # noqa: E402
from PIL import Image  # noqa: E402
import nodes  # noqa: E402
from comfy_extras.nodes_sdpose import SDPoseKeypointExtractor  # noqa: E402

CKPT = "sdpose_wholebody_fp16.safetensors"


def as_tensor(path):
    """An IMAGE the way ComfyUI hands it around: [1, H, W, 3] float in 0..1."""
    a = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32) / 255.0
    return torch.from_numpy(a).unsqueeze(0)


def main(paths):
    model, _clip, vae = nodes.CheckpointLoaderSimple().load_checkpoint(CKPT)
    extractor = SDPoseKeypointExtractor()
    out = {}
    for p in paths:
        kp = extractor.execute(model=model, vae=vae, image=as_tensor(p), batch_size=1)[0]
        out[str(p)] = kp
    json.dump(out, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main([Path(a) for a in os.environ.get("POSE_IMAGES", "").split()])
