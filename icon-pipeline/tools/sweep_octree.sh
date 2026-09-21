#!/usr/bin/env bash
# Density-vs-fidelity at fixed shape: vary only octree_resolution.
#
# Latent resolution is held at 4096 because it is a latent SIZE, not a quality
# dial -- changing it with a fixed seed yields a different reconstruction, which
# silently invalidated the earlier 3-config comparison.
set -u
cd "$(dirname "$0")/.." || exit 1
PY=/data/ComfyUI/venv/bin/python
SEED=1108207273232038

for OCT in 128 192 256; do
  $PY - "$OCT" "$SEED" <<'EOF'
import json, sys
g = json.load(open("workflows/3d_full_chain.json"))
o, s = int(sys.argv[1]), int(sys.argv[2])
g["8"]["inputs"]["octree_resolution"] = o
g["7"]["inputs"]["seed"] = s
g["30"] = {"class_type": "SaveGLB", "inputs": {"mesh": ["9", 0], "filename_prefix": f"agent3d/d{o}/raw"}}
g["40"] = {"class_type": "MaskToImage", "inputs": {"mask": ["28", 1]}}
g["41"] = {"class_type": "SaveImage", "inputs": {"images": ["40", 0], "filename_prefix": f"agent3d/d{o}/mask"}}
g["27"]["inputs"]["filename_prefix"] = f"agent3d/d{o}/post"
g["29"]["inputs"]["filename_prefix"] = f"agent3d/d{o}/render"
json.dump(g, open(f"workflows/3d_oct{o}.json", "w"), indent=1)
EOF
  rm -f run/.sampler_stop
  LOG=run/mem_oct$OCT.csv timeout 600 bash -c "
    PY=$PY bash tools/mem_sampler.sh run/mem_oct$OCT.csv &
    S=\$!; sleep 2
    $PY -u tools/run_graph.py workflows/3d_oct$OCT.json
    touch run/.sampler_stop; wait \$S 2>/dev/null
  " > run/oct$OCT.txt 2>&1
  echo "### octree=$OCT"
  grep -E "elapsed|status" run/oct$OCT.txt | head -2
  awk -F, 'NR>1 && $2>0 {if($3>u)u=$3; if(a==0||$4<a)a=$4; if($8>g)g=$8} END{printf "    peak mem_used %d MiB | min avail %d MiB | peak gpu %d MiB\n", u, a, g}' run/mem_oct$OCT.csv
done

$PY tools/mesh_stats.py /data/ComfyUI/output/agent3d/d128/raw_00001_.glb /data/ComfyUI/output/agent3d/d192/raw_00001_.glb /data/ComfyUI/output/agent3d/d256/raw_00001_.glb 2>&1 | grep -E "glb|verts"
M=""
for O in 256 192 128; do M="$M /data/ComfyUI/output/agent3d/d$O/mask_00001_.png"; done
$PY tools/render_agree.py $M --ref d256 --mode mask
