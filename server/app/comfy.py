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
import uuid
from pathlib import Path

from .config import COMFY, TOOLS

if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import run_graph  # noqa: E402  the same client gen_icons.py uses

# The only pairing we have measured end to end (8/8 icons, 4s/image warm). Everything
# else in the catalog is selectable but flagged: it exists, we have not gated its output.
VERIFIED = {"unet": "z_image_turbo_int8_convrot.safetensors",
            "clip": "qwen_3_4b_fp8_mixed.safetensors",
            "vae": "ae.safetensors",
            "upscale": "4x-UltraSharp.pth"}

# /object_info node -> input key -> what the UI calls it
SOURCES = {"UNETLoader": ("unet_name", "unet"),
           "CLIPLoader": ("clip_name", "clip"),
           "VAELoader": ("vae_name", "vae"),
           "UpscaleModelLoader": ("model_name", "upscale")}

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
    that reported success with nothing attached. Files whose type is "input" are
    echoes of a LoadVideo's own source, not a deliverable, and are dropped.
    """
    status, outputs, secs = run_graph.wait(pid, timeout=timeout)
    files = [f for f in run_graph.saved_files(outputs) if f.get("type") != "input"]
    return status, files, secs


def upload(src, name=None):
    """Put a file we produced where LoadImage/LoadVideo can see it, and return its stored name.

    LoadImage and LoadVideo only list ComfyUI's own input/ directory, so a file this
    server generated into output/ cannot be fed straight back to a video or 3D job -- it
    has to go through the same POST /upload/image the browser's own upload button uses
    (measured: the engine accepts an mp4 there and LoadVideo lists it).
    """
    p = Path(src)
    fname = name or p.name
    mime = {".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime"}.get(p.suffix.lower(), "image/png")
    boundary = uuid.uuid4().hex
    body = b"".join([
        f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{fname}"\r\n'
        f'Content-Type: {mime}\r\n\r\n'.encode(),
        p.read_bytes(),
        f'--{boundary}\r\nContent-Disposition: form-data; name="type"\r\n\r\ninput\r\n'.encode(),
        f'--{boundary}\r\nContent-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n'.encode(),
        f"--{boundary}--\r\n".encode(),
    ])
    req = urllib.request.Request(f"{COMFY}/upload/image", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    r = json.loads(urllib.request.urlopen(req, timeout=60).read())
    return r.get("name") or fname


def put_workflow(path, body):
    """Save a workflow into the engine's own workflows/ directory -- the one its menu lists.

    The sub-directory has to ride inside the quoted filename: ``POST /userdata/workflows%2Fx.json``
    lands in ``user/default/workflows/``, while ``?dir=workflows`` is ignored on write and drops
    the file in the user root instead (both measured against 0.37.0).
    """
    url = f"{COMFY}/userdata/{urllib.parse.quote(path, safe='')}"
    req = urllib.request.Request(url + "?overwrite=true", data=body.encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    urllib.request.urlopen(req, timeout=30).read()
    return url.split("/userdata/")[1]


def running_ids():
    q = _get("/queue")
    return [item[1] for item in q.get("queue_running", [])]


def queued_ids():
    q = _get("/queue")
    return [item[1] for item in q.get("queue_pending", [])]


def cancel(pid):
    """Drop a job we have stopped waiting for.

    Without this the engine keeps burning the GPU on a task the API already
    reported as failed, and the next submission silently queues behind it.

    This engine rejects DELETE /queue with a 405; removal is POST /queue with a
    {"delete": [id]} body. Verified against the live queue, because the first two
    guesses here both returned without deleting anything -- so nothing is swallowed:
    the return value says which outcome actually happened.
    """
    try:
        req = urllib.request.Request(f"{COMFY}/queue", data=json.dumps({"delete": [pid]}).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=15).read()
    except Exception as e:
        return f"queue delete failed ({type(e).__name__})"
    if pid in queued_ids():
        return "still queued"
    if pid in running_ids():
        try:
            urllib.request.urlopen(urllib.request.Request(f"{COMFY}/interrupt", data=b"{}", method="POST"),
                                   timeout=15).read()
            return "interrupted"
        except Exception as e:
            return f"interrupt failed ({type(e).__name__})"
    return "removed from queue"


def alive():
    try:
        _get("/system_stats")
        return True
    except Exception:
        return False


def _combo(v):
    """The option list of a combo input, in whichever shape this engine reports it.

    Classic nodes answer ``[["a","b"], {...}]``; v3 ``io.Schema`` nodes answer
    ``["COMBO", {"options": ["a","b"]}]``. Reading only the first shape returns nothing
    and the UI silently offers no choices.
    """
    if isinstance(v, list) and v and isinstance(v[0], list):
        return v[0]
    if isinstance(v, list) and len(v) > 1 and isinstance(v[1], dict):
        return v[1].get("options") or []
    return []


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
            opts = opts or _combo(info.get(node, {}).get("input", {}).get(sec, {}).get(key))
        out[role] = [{"name": n, "verified": n == VERIFIED[role]} for n in sorted(opts)]
    # The sampler and schedule names are the engine's own combo, not a list kept here:
    # every studio graph samples through a plain KSampler node (70, 8, 24), so one
    # query covers all three.
    req = _get("/object_info/KSampler").get("KSampler", {}).get("input", {}).get("required", {})
    for key, role in (("sampler_name", "samplers"), ("scheduler", "schedulers")):
        out[role] = sorted(_combo(req.get(key)))
    # ref_image_size is the reference route's fidelity/speed switch. Its values come from
    # the node, so the UI cannot offer a size this build of H3 does not implement.
    v = (_get("/object_info/MiniMaxH3ReferenceToVideo")
         .get("MiniMaxH3ReferenceToVideo", {}).get("input", {}).get("required", {}))
    out["refsizing"] = sorted(_combo(v.get("ref_image_size")))
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
