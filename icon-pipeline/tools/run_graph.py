"""Drive a ComfyUI API-format workflow headlessly and report timing + VRAM."""

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SERVER = "http://127.0.0.1:8188"


def post(graph, client_id):
    req = urllib.request.Request(f"{SERVER}/prompt",
                                 data=json.dumps({"prompt": graph, "client_id": client_id}).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def stats():
    return json.loads(urllib.request.urlopen(f"{SERVER}/system_stats", timeout=30).read())["devices"][0]


def _get(url):
    return json.loads(urllib.request.urlopen(url, timeout=30).read())


def wait(pid, timeout=900, poll=1.0):
    """Block until ComfyUI reports the prompt, and return (status, outputs, seconds).

    status carries the execution_error message when there is one, because
    status_str alone says only 'error' and the caller has to show a reason.

    A refused or reset connection is the engine's process dying mid-job, not a reason
    to give up: the port comes back when the distro's supervisor restarts it, and the
    finished artefact is then in history again. So keep polling inside the budget and
    only report DIED when the budget runs out with the prompt never having appeared.
    """
    t0 = time.time()
    down = False
    while True:
        try:
            h = _get(f"{SERVER}/history/{pid}")
            if pid in h:
                st = h[pid].get("status", {}).get("status_str", "?")
                for m in (h[pid].get("status", {}).get("messages") or []):
                    if m[0] == "execution_error":
                        st += ": " + str(m[1].get("exception_message", ""))[:200]
                if down:
                    st += " (engine restarted mid-job)"
                return st, h[pid].get("outputs", {}), time.time() - t0
            down = False
        except (urllib.error.URLError, ConnectionError, OSError):
            down = True
        if time.time() - t0 > timeout:
            return ("DIED: engine restarted and this prompt is not in its history"
                    if down else "TIMEOUT"), {}, time.time() - t0
        time.sleep(poll)


def saved_files(outputs):
    """Every image/glb node wrote, as {subfolder, filename} for the /view endpoint."""
    out = []
    for nid in sorted(outputs, key=lambda n: int(n) if n.isdigit() else 0):
        for kind, items in outputs[nid].items():
            for it in (items or []):
                if isinstance(it, dict) and "filename" in it:
                    out.append({"kind": kind, "node": nid, "subfolder": it.get("subfolder", ""),
                                "filename": it["filename"], "type": it.get("type", "output")})
    return out


def main():
    graph = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    client = "p0-runner"
    before = stats()
    t0 = time.time()
    r = post(graph, client)
    if "error" in r:
        print(json.dumps(r, indent=2, ensure_ascii=False)[:4000])
        sys.exit(1)
    pid = r["prompt_id"]
    print("queued", pid)
    err, out, dur = wait(pid)
    after = stats()
    print(f"elapsed {dur:.1f}s  status={err}")
    print(f"vram free before {before['vram_free']/2**20:.0f}MiB  after {after['vram_free']/2**20:.0f}MiB")
    for f in saved_files(out):
        p = f["subfolder"] + "/" if f["subfolder"] else ""
        print(f"  node{f['node']} {f['kind']}: {p}{f['filename']} {f['type']}")
    if err != "success":
        sys.exit(1)


if __name__ == "__main__":
    main()
