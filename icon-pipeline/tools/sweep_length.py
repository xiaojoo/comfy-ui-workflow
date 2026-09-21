"""How long a clip can this box actually make? Sweep upward and let the failure decide.

Linear extrapolation from the 33/49/81 ladder would say ~700 frames fits the 20-minute
budget. Two things break that arithmetic: Wan 1.3B is *trained* at 81 frames, and the
VAE decode of a long clip is a large pixel tensor. So measure the boundary instead --
peak VRAM and RAM included, because an OOM is a different answer from a slow run.
"""
import json
import threading
import time
import urllib.request

import cv2
import numpy as np

B = "http://127.0.0.1:8191"
C = "http://127.0.0.1:8188"
FRAME_COUNTS = [121, 241, 481]          # 4k+1; 7.5s / 15s / 30s of film at 16fps
TIME_BUDGET = 1200                      # his stated ceiling: 20 minutes to generate

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


def post(path, body):
    r = urllib.request.Request(B + path, data=json.dumps(body).encode(),
                               headers={"content-type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=60).read())


def get(path):
    return json.loads(urllib.request.urlopen(B + path, timeout=30).read())


def coherence(url):
    """Decoded frame count, plus a crude same-object check: mean colour drift between
    the first and last frame, and the largest single-frame jump (a cut or a collapse
    shows up there). Not a consistency metric -- just enough to reject nonsense."""
    raw = urllib.request.urlopen(C + url[len("/comfy"):], timeout=120).read()
    open("H:/workflow/icon-pipeline/run/_sweep.mp4", "wb").write(raw)
    cap = cv2.VideoCapture("H:/workflow/icon-pipeline/run/_sweep.mp4")
    fps = cap.get(cv2.CAP_PROP_FPS)
    frames = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(cv2.resize(f, (160, 96)).astype(np.int16))
    cap.release()
    if len(frames) < 2:
        return {"decoded": len(frames)}
    diffs = [np.abs(frames[i] - frames[i - 1]).mean() for i in range(1, len(frames))]
    return {"decoded": len(frames), "fps": round(fps, 1),
            "film_s": round(len(frames) / fps, 2) if fps else None,
            "first_last_drift": round(np.abs(frames[0] - frames[-1]).mean(), 2),
            "max_frame_jump": round(max(diffs), 2), "mean_frame_jump": round(float(np.mean(diffs)), 2)}


for n in FRAME_COUNTS:
    low["vram"] = 10 ** 12
    low["ram"] = 10 ** 12
    stop.clear()
    th = threading.Thread(target=sample, daemon=True)
    th.start()
    t0 = time.time()
    try:
        r = post("/tasks", {"template": "wan_t2v", "prompt": "a flat gear icon rotating slowly on a white background, steady camera",
                            "params": {"length": n}})
    except Exception as e:
        print(f"{n:4d}f  SUBMIT FAILED {e}", flush=True)
        continue
    tid = r["task_id"]
    while True:
        t = get(f"/tasks/{tid}")
        if t["state"] in ("done", "error"):
            break
        if time.time() - t0 > TIME_BUDGET + 300:
            print(f"{n:4d}f  GAVE UP waiting past budget", flush=True)
            break
        time.sleep(3)
    stop.set()
    time.sleep(0.6)
    wall = time.time() - t0
    gib = lambda x: x / 2 ** 30
    print(f"{n:4d}f  {t['state']:5s}  wall={wall:7.1f}s  reported={t['seconds']}  "
          f"peak_vram_used~{gib(17170956288 - low['vram']):.2f}GiB  min_vram_free={gib(low['vram']):.2f}GiB  "
          f"min_ram_free={gib(low['ram']):.2f}GiB  err={(t['error'] or '')[:150]}", flush=True)
    if t["state"] == "done" and t["outputs"]:
        try:
            print("      film:", json.dumps(coherence(t["outputs"][0]["url"])), flush=True)
        except Exception as e:
            print("      film check failed:", e, flush=True)
    if t["state"] == "error":
        print("  stopping sweep at first failure", flush=True)
        break
print("done")
