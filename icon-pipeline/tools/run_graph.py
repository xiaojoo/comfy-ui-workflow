"""Drive a ComfyUI API-format workflow headlessly and report timing + VRAM."""

import json
import sys
import time
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
    err = None
    while True:
        h = json.loads(urllib.request.urlopen(f"{SERVER}/history/{pid}", timeout=30).read())
        if pid in h:
            err = h[pid].get("status", {}).get("status_str")
            break
        if time.time() - t0 > 600:
            print("TIMEOUT")
            sys.exit(1)
        time.sleep(1.0)
    dur = time.time() - t0
    after = stats()
    print(f"elapsed {dur:.1f}s  status={err}")
    print(f"vram free before {before['vram_free']/2**20:.0f}MiB  after {after['vram_free']/2**20:.0f}MiB")
    out = h[pid].get("outputs", {})
    for nid in sorted(out, key=int):
        for kind, items in out[nid].items():
            for it in items:
                p = it.get("subfolder", "") + "/" if it.get("subfolder") else ""
                print(f"  node{nid} {kind}: {p}{it.get('filename')} {it.get('type')}")


if __name__ == "__main__":
    main()
