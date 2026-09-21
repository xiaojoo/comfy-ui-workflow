"""L1: generate an on-domain icon test set.

The gate's thresholds were calibrated on synthetic hard-edge shapes; they can only
be re-checked against real model output, and that output has to actually be icons
rather than the full-bleed artwork that happened to be sitting in output/.
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_graph

STYLE = ("flat vector app icon, one single centered object, solid pure white background, "
         "two or three flat colors, thick clean geometry, sharp corners, no text, "
         "no gradient, no shadow, no outline noise, high contrast, product icon style")
NEG = ("photograph, scenery, background objects, gradient, drop shadow, text, watermark, "
       "intricate detail, low contrast, multiple subjects")

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

GRAPH = {
    "62": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_3_4b.safetensors", "type": "lumina2", "device": "default"}},
    "63": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
    "66": {"class_type": "UNETLoader", "inputs": {"unet_name": "z_image_turbo_bf16.safetensors", "weight_dtype": "default"}},
    "69": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["66", 0], "shift": 3}},
    "68": {"class_type": "EmptySD3LatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
    "67": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["62", 0], "text": ""}},
    "71": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["62", 0], "text": NEG}},
    "70": {"class_type": "KSampler", "inputs": {
        "model": ["69", 0], "positive": ["67", 0], "negative": ["71", 0], "latent_image": ["68", 0],
        "seed": 42, "control_after_generate": "fixed", "steps": 8, "cfg": 1.0,
        "sampler_name": "res_multistep", "scheduler": "simple", "denoise": 1.0}},
    "65": {"class_type": "VAEDecode", "inputs": {"samples": ["70", 0], "vae": ["63", 0]}},
    "9": {"class_type": "SaveImage", "inputs": {"images": ["65", 0], "filename_prefix": "icons/gear"}},
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=list(SUBJECTS))
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--prefix-dir", default="icons")
    ap.add_argument("--unet", default="z_image_turbo_bf16.safetensors")
    ap.add_argument("--clip", default="qwen_3_4b.safetensors")
    args = ap.parse_args()

    GRAPH["66"]["inputs"]["unet_name"] = args.unet
    GRAPH["62"]["inputs"]["clip_name"] = args.clip
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
        t0 = time.time()
        r = run_graph.post(g, "icon-gen")
        if "error" in r:
            print(f"{slug:12} REJECTED {json.dumps(r.get('error') or r.get('node_errors'))[:500]}")
            continue
        pid = r["prompt_id"]
        st = "unknown"
        while True:
            h = json.loads(run_graph.urllib.request.urlopen(f"{run_graph.SERVER}/history/{pid}", timeout=30).read())
            if pid in h:
                st = h[pid].get("status", {}).get("status_str", "?")
                for m in (h[pid].get("status", {}).get("messages") or []):
                    if m[0] == "execution_error":
                        st += " " + str(m[1].get("exception_message", ""))[:120]
                break
            if time.time() - t0 > 600:
                st = "TIMEOUT"
                break
            time.sleep(2)
        print(f"{slug:12} {time.time()-t0:5.1f}s  {st}")


if __name__ == "__main__":
    main()
