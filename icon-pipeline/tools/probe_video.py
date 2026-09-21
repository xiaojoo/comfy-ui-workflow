"""Does Wan 2.1 T2V actually need a .wslconfig bump? Measure it, don't assume.

The recorded blocker was set when the plan was a bigger model. The 1.3B T2V trio
sums to ~9.15 GiB against a 15.5 GiB ceiling, so the claim has to be re-tested
before it is repeated.
"""

import json
import sys
import threading
import time
import urllib.request

SERVER = "http://127.0.0.1:8188"
GRAPH = "/mnt/h/workflow/icon-pipeline/workflows/wan_t2v.json"

peak = {"used_kib": 0, "free_kib": 10 ** 9}
stop = threading.Event()


def sample():
    while not stop.is_set():
        kv = {}
        with open("/proc/meminfo") as fh:
            for line in fh:
                a, b = line.split(":", 1)
                kv[a] = int(b.strip().split()[0])
        used = int(kv["MemTotal"]) - int(kv["MemAvailable"])
        peak["used_kib"] = max(peak["used_kib"], used)
        peak["free_kib"] = min(peak["free_kib"], int(kv["MemAvailable"]))
        time.sleep(0.2)


def main():
    # Wan's temporal VAE compresses by 4, so a valid clip is 4k+1 frames. 33 is the
    # 2s baseline; the interesting number is how far the 15.5 GiB ceiling reaches.
    length = int(sys.argv[1]) if len(sys.argv) > 1 else 33
    steps = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    graph = json.loads(open(GRAPH, encoding="utf-8").read())
    graph["7"]["inputs"]["length"] = length
    graph["8"]["inputs"]["steps"] = steps
    graph["11"]["inputs"]["filename_prefix"] = f"video/wan_{length}f_s{steps}"
    print(f"length={length} steps={steps}  (4k+1 required)", flush=True)

    th = threading.Thread(target=sample, daemon=True)
    th.start()

    req = urllib.request.Request(f"{SERVER}/prompt",
                                 data=json.dumps({"prompt": graph, "client_id": "video-probe"}).encode(),
                                 headers={"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=60).read())
    if "error" in r:
        stop.set()
        print("REJECTED", json.dumps(r.get("error") or r.get("node_errors"))[:1200])
        return

    pid = r["prompt_id"]
    print("queued", pid, flush=True)
    t0 = time.time()
    status = "unknown"
    while time.time() - t0 < 1800:
        h = json.loads(urllib.request.urlopen(f"{SERVER}/history/{pid}", timeout=30).read())
        if pid in h:
            status = h[pid].get("status", {}).get("status_str", "?")
            for m in (h[pid].get("status", {}).get("messages") or []):
                if m[0] == "execution_error":
                    status += ": " + str(m[1].get("exception_message", ""))[:300]
            out = h[pid].get("outputs", {})
            for nid in sorted(out, key=int):
                for kind, items in (out[nid] or {}).items():
                    for it in (items or []):
                        if isinstance(it, dict) and "filename" in it:
                            print(f"  file {kind}: {it.get('subfolder','')}/{it['filename']}")
            break
        time.sleep(2)
    else:
        status = "TIMEOUT"

    stop.set()
    time.sleep(0.4)
    el = time.time() - t0
    print(f"\nelapsed {el:.1f}s  status={status}")
    print(f"peak mem used {peak['used_kib']/2**20:.2f} GiB   lowest MemAvailable {peak['free_kib']/2**20:.2f} GiB")
    print("If MemAvailable never approached zero, the recorded .wslconfig blocker does not")
    print("apply to this configuration. Free the icon weights first (POST /free) or the")
    print("reading measures contention with them, not the video graph.")


if __name__ == "__main__":
    main()
