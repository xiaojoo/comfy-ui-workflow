#!/usr/bin/env bash
# One 3D run with a memory curve attached, so an OOM is distinguishable from a
# slow step and the headroom left over is known.
cd "$(dirname "$0")/.." || exit 1
PY=${PY:-/data/ComfyUI/venv/bin/python}
LOG=run/mem3d.csv

bash tools/mem_sampler.sh "$LOG" &
SAMP=$!
sleep 2
$PY -u tools/run_graph.py "${1:-workflows/3d_image_to_glb.json}"
RC=$?
touch run/.sampler_stop
wait "$SAMP" 2>/dev/null
echo "rc=$RC"
$PY - "$LOG" <<'EOF'
import sys
rows=[l.split(",") for l in open(sys.argv[1]).read().splitlines()[1:] if len(l.split(","))>=8]
if not rows:
    print("no samples"); sys.exit()
f=lambda i: [float(r[i]) for r in rows if float(r[i])>0]
print("peak mem_used_mib", max(map(int,f(2))), "| min avail_mib", min(map(int,f(3))))
print("peak gpu_used_mib", max(map(int,f(7))))
EOF
ls -la /data/ComfyUI/output/agent3d/ 2>/dev/null
