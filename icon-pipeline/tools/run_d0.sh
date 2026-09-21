#!/usr/bin/env bash
# Does D0 (cut-out + flat background) fix the 323-shell asset? Same source photo,
# same seed, same octree -- only the input preprocessing differs.
set -u
cd "$(dirname "$0")/.." || exit 1
PY=/data/ComfyUI/venv/bin/python

cp run/icons/gear_00001_.png /data/ComfyUI/input/ 2>/dev/null

for SPEC in "cat:test.jpg:d0cat" "gear:gear_00001_.png:d0gear"; do
  NAME=${SPEC%%:*}; rest=${SPEC#*:}; IMG=${rest%%:*}; TAG=${rest##*:}
  $PY - "$IMG" "$TAG" <<'EOF'
import json, sys
g = json.load(open("workflows/3d_d0_chain.json"))
g["2"]["inputs"]["image"] = sys.argv[1]
for n, p in [("15", f"{sys.argv[2]}/INPUT"), ("27", f"{sys.argv[2]}/raw"),
             ("29", f"{sys.argv[2]}/render"), ("31", f"{sys.argv[2]}/mask")]:
    g[n]["inputs"]["filename_prefix"] = p
json.dump(g, open(f"workflows/3d_{sys.argv[2]}.json", "w"), indent=1)
EOF
  $PY -u tools/run_graph.py "workflows/3d_$TAG.json" > "run/$TAG.txt" 2>&1
  echo "### $NAME  (input: $IMG)"
  grep -E "elapsed|status|error" "run/$TAG.txt" | head -3
  $PY tools/mesh_metrics.py "/data/ComfyUI/output/$TAG/raw_00001_.glb" > "run/m_$TAG.json" 2>&1
  $PY - "run/m_$TAG.json" <<'EOF'
import json, sys
d = json.load(open(sys.argv[1]))
print("   shells %s | open %s | nonmanifold %s | tris %s | bbox %s"
      % (d.get("shells"), d.get("open_edges"), d.get("nonmanifold_edges"), d.get("tris"), d.get("bbox")))
for s in d.get("top_shells", [])[:4]:
    print("     shell tris %-8s area %-10s vol %-10s thinness %s"
          % (s["tris"], s["area"], s["volume"], s["thinness"]))
EOF
done
