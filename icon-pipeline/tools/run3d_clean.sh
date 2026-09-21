#!/usr/bin/env bash
# Decisive test: clean synthetic object in, same chain -- are the 323 shells the
# photo's fault or the model's?
set -u
cd "$(dirname "$0")/.." || exit 1
PY=/data/ComfyUI/venv/bin/python

$PY tools/make_object_png.py run/solid
cp run/solid/obj_sphere.png run/solid/obj_snowman.png /data/ComfyUI/input/

$PY - <<'EOF'
import json
g = json.load(open("workflows/3d_oct192.json"))
g["2"]["inputs"]["image"] = "obj_sphere.png"
for n, nme in [("30", "clean192/sphere_raw"), ("27", "clean192/sphere_post"), ("29", "clean192/sphere_render")]:
    if n in g:
        g[n]["inputs"]["filename_prefix"] = nme
json.dump(g, open("workflows/3d_clean_sphere.json", "w"), indent=1)

g["2"]["inputs"]["image"] = "obj_snowman.png"
for n, nme in [("30", "clean192/snowman_raw"), ("27", "clean192/snowman_post"), ("29", "clean192/snowman_render")]:
    if n in g:
        g[n]["inputs"]["filename_prefix"] = nme
json.dump(g, open("workflows/3d_clean_snowman.json", "w"), indent=1)
print("clean probes written")
EOF

for TAG in sphere snowman; do
  rm -f run/.sampler_stop
  bash -c "$PY tools/mem_sampler.sh run/mem_clean_$TAG.csv & sleep 2; $PY -u tools/run_graph.py workflows/3d_clean_$TAG.json; touch run/.sampler_stop; wait" > "run/clean_$TAG.txt" 2>&1
  echo "### clean input: $TAG"
  grep -E "elapsed|status" "run/clean_$TAG.txt" | head -2
  awk -F, 'NR>1 && $2>0 {if($3>u)u=$3; if(a==0||$4<a)a=$4} END{printf "    peak mem_used %d MiB | min avail %d MiB\n", u, a}' "run/mem_clean_$TAG.csv"
  $PY tools/mesh_metrics.py "/data/ComfyUI/output/clean192/${TAG}_raw_00001_.glb" \
     | $PY -c "
import json,sys
d=json.load(sys.stdin)
print('    shells %s | watertight %s | open %s | nonmanifold %s | tris %s | bbox %s'
      % (d['shells'], d['watertight'], d['open_edges'], d['nonmanifold_edges'], d['tris'], d['bbox']))
for s in d['top_shells'][:3]:
    print('      shell tris %-8s area %-10s vol %-10s thinness %s' % (s['tris'], s['area'], s['volume'], s['thinness']))
"
done
