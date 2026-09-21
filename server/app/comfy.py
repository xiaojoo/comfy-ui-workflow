"""The ComfyUI side: what is actually installed, and where the bytes are.

Nothing here guesses a model name. The catalog is read from the live engine, so a
weight that was deleted yesterday stops appearing today, and the UI cannot offer a
model that would fail at run time.
"""

import json
import shutil
import sys
import urllib.parse
import urllib.request

from .config import COMFY, TOOLS

if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import run_graph  # noqa: E402  the same client gen_icons.py uses

# The only pairing we have measured end to end (8/8 icons, 4s/image warm). Everything
# else in the catalog is selectable but flagged: it exists, we have not gated its output.
VERIFIED = {"unet": "z_image_turbo_int8_convrot.safetensors",
            "clip": "qwen_3_4b_fp8_mixed.safetensors",
            "vae": "ae.safetensors"}

# /object_info node -> input key -> what the UI calls it
SOURCES = {"UNETLoader": ("unet_name", "unet"),
           "CLIPLoader": ("clip_name", "clip"),
           "VAELoader": ("vae_name", "vae")}

# WSL's ext4 volume is only reachable by UNC path from here; disk_usage on it returns
# the real numbers, so the storage meter does not need a shell-out into the distro.
COMFY_ROOT = "//wsl.localhost/ComfyUI/data/ComfyUI"


def _get(path, params=None):
    url = f"{COMFY}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    return json.loads(urllib.request.urlopen(url, timeout=30).read())


def submit(graph, client_id):
    """Hand a graph to ComfyUI. Raises on a rejected graph, before we wait."""
    r = run_graph.post(graph, client_id)
    if "error" in r:
        raise RuntimeError(f"graph rejected: {json.dumps(r.get('error') or r.get('node_errors'))[:400]}")
    return r["prompt_id"]


def collect(pid, timeout=900):
    """(status, files, seconds) once the engine reports the prompt finished.

    Every saved file is returned, not just images: this line's deliverables are
    mp4 and glb as often as png, and filtering on kind silently produced tasks
    that reported success with nothing attached.
    """
    status, outputs, secs = run_graph.wait(pid, timeout=timeout)
    return status, run_graph.saved_files(outputs), secs


def alive():
    try:
        _get("/system_stats")
        return True
    except Exception:
        return False


def catalog():
    """Model files the running engine can actually load, split by role.

    One request per node: this engine answers /object_info/A,B,C with an empty
    object, so a combined query would silently return a catalogue with nothing in
    it and the UI would offer no models at all.
    """
    out = {}
    for node, (key, role) in SOURCES.items():
        info = _get("/object_info/" + node)
        opts = []
        for sec in ("required", "optional"):
            v = info.get(node, {}).get("input", {}).get(sec, {}).get(key)
            if isinstance(v, list) and v and isinstance(v[0], list):
                opts = v[0]
        out[role] = [{"name": n, "verified": n == VERIFIED[role]} for n in sorted(opts)]
    return out


def engine():
    s = _get("/system_stats")
    d = s["devices"][0]
    sysd = s.get("system", {})
    return {"version": sysd.get("comfyui_version"), "device": d.get("name"),
            "vram_total_gb": round(d["vram_total"] / 2**30, 1),
            "vram_free_gb": round(d["vram_free"] / 2**30, 1),
            "ram_total_gb": round(sysd.get("ram_total", 0) / 2**30, 1),
            "ram_free_gb": round(sysd.get("ram_free", 0) / 2**30, 1)}


def storage():
    total, used, free = shutil.disk_usage(COMFY_ROOT)
    return {"total_gb": round(total / 2**30, 1), "used_gb": round(used / 2**30, 1),
            "free_gb": round(free / 2**30, 1), "pct": round(used / total * 100, 1),
            "root": COMFY_ROOT}


def view_url(subfolder, filename):
    """A browser-loadable URL for a saved output, routed through the vite proxy."""
    q = urllib.parse.urlencode({"filename": filename, "subfolder": subfolder, "type": "output"})
    return f"/comfy/view?{q}"
