"""Run the L4->L5 spine over real model output and stage results for the gate.

The gate wants <tag>.svg next to <tag>_gt.png; ComfyUI wants absolute output
prefixes and hands back auto-numbered names, so the renaming lives here.
"""

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_graph

TEMPLATE = Path(__file__).resolve().parent.parent / "workflows" / "spine_real_image.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", nargs="+", required=True, help="filenames inside ComfyUI input/")
    ap.add_argument("--out-comfy", required=True, help="ComfyUI output dir, WSL path")
    ap.add_argument("--out-local", required=True, help="local dir to stage gate inputs into")
    ap.add_argument("--dtype", default="float16")
    ap.add_argument("--template", default=str(TEMPLATE))
    ap.add_argument("--suffix", default="", help="tag suffix so variants do not clobber each other")
    args = ap.parse_args()

    tmpl = json.loads(Path(args.template).read_text(encoding="utf-8"))
    out_local = Path(args.out_local)
    out_local.mkdir(parents=True, exist_ok=True)
    rows = []

    for img in args.images:
        tag = Path(img).stem + args.suffix
        graph = json.loads(json.dumps(tmpl))
        graph["1"]["inputs"]["image"] = img
        graph["2"]["inputs"]["dtype"] = args.dtype
        for n in graph.values():
            if n["inputs"].get("filename_prefix") == "PREFIX/raw":
                n["inputs"]["filename_prefix"] = f"{tag}/raw"
            elif isinstance(n["inputs"].get("filename_prefix"), str):
                n["inputs"]["filename_prefix"] = f"{tag}/{n['inputs']['filename_prefix'].split('/')[-1]}"

        t0 = time.time()
        r = run_graph.post(graph, "spine-runner")
        if "error" in r:
            print(f"{tag}: REJECTED {json.dumps(r)[:400]}")
            continue
        pid = r["prompt_id"]
        while True:
            h = json.loads(run_graph.urllib.request.urlopen(f"{run_graph.SERVER}/history/{pid}", timeout=30).read())
            if pid in h:
                break
            if time.time() - t0 > 420:
                print(f"{tag}: TIMEOUT")
                break
            time.sleep(1)
        dur = time.time() - t0
        st = h.get(pid, {}).get("status", {})
        outdir = Path(args.out_comfy) / tag
        svg = sorted(outdir.glob("raw*.svg")) or sorted(outdir.glob("*.svg"))
        src = [p for p in sorted(outdir.glob("src*.png"))]
        dest_svg = out_local / f"{tag}.svg"
        ok = bool(svg) and bool(src)
        if ok:
            shutil.copyfile(svg[-1], dest_svg)
            shutil.copyfile(src[-1], out_local / f"{tag}_gt.png")
        err = ""
        for m in (st.get("messages") or []):
            if m[0] == "execution_error":
                err = m[1].get("exception_message", "")[:110]
        print(f"{tag:34} {st.get('status_str','?'):8} {dur:5.1f}s  svg={'Y' if svg else 'N'} src={len(src)}  {err}")
        rows.append((tag, st.get("status_str"), round(dur, 1), bool(svg)))

    print(f"\nstaged {len(rows)} assets -> {out_local}")


if __name__ == "__main__":
    main()
