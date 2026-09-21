"""A/B the same clip with and without sliding context windows.

Baseline already measured: 241 frames, one latent, no context window = 846.2 s.
If WanContextWindowsManual turns the superlinear time curve back towards linear,
that changes the honest answer to "how long a clip fits a 20 minute budget".
"""
import json
import sys
import threading
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_graph

C = "http://127.0.0.1:8188"
low = {"vram": 10 ** 12, "ram": 10 ** 12}
stop = threading.Event()


def sample():
    while not stop.is_set():
        try:
            d = json.loads(urllib.request.urlopen(f"{C}/system_stats", timeout=10).read())
            low["vram"] = min(low["vram"], d["devices"][0]["vram_free"])
            low["ram"] = min(low["ram"], d["system"]["ram_free"])
        except Exception:
            pass
        time.sleep(0.5)


def main():
    length = int(sys.argv[1]) if len(sys.argv) > 1 else 241
    g = json.loads((Path(__file__).resolve().parents[1] / "workflows" / "wan_t2v_long.json")
                   .read_text(encoding="utf-8"))
    g["7"]["inputs"]["length"] = length
    g["11"]["inputs"]["filename_prefix"] = f"video/ctx_{length}f"
    print(f"context-window run: {length}f, context_length={g['12']['inputs']['context_length']}, "
          f"overlap={g['12']['inputs']['context_overlap']}, fuse={g['12']['inputs']['fuse_method']}",
          flush=True)

    stop.clear()
    th = threading.Thread(target=sample, daemon=True)
    th.start()
    t0 = time.time()
    r = run_graph.post(g, "ctx-ab")
    if "error" in r:
        stop.set()
        print("REJECTED", json.dumps(r.get("error") or r.get("node_errors"))[:900], flush=True)
        return
    status, outputs, secs = run_graph.wait(r["prompt_id"], timeout=3000)
    stop.set()
    gib = lambda x: x / 2 ** 30
    print(f"status={status}  elapsed={secs:.1f}s  wall={time.time()-t0:.1f}s")
    print(f"min vram_free={gib(low['vram']):.2f} GiB   min ram_free={gib(low['ram']):.2f} GiB")
    for f in run_graph.saved_files(outputs):
        print("  file:", f"{f['subfolder']}/{f['filename']}")
    print(f"\nvs baseline (no context window, 241f): 846.2s")


if __name__ == "__main__":
    main()
