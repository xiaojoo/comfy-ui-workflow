#!/usr/bin/env bash
# Full local spine run: vectorise -> gate -> normalise -> re-gate -> prove the ruler.
set -u
cd "$(dirname "$0")"
PY=${PY:-/data/ComfyUI/venv/bin/python}
GT=${GT:-run/gt}
OUT=${OUT:-run/svg}

$PY tools/vectorize_local.py --in-dir "$GT" --out-dir "$OUT"
echo
echo "##### RULER SELFTEST (axis orthogonality)"
$PY tools/qa_gate.py --selftest --source "$GT/gear_gt.png" --svg "$OUT/default/gear.svg"
echo
for p in tight default coarse polygon; do
  echo "##### NORMALISE preset=$p"
  $PY tools/svg_norm.py --dir "$OUT/$p"
  echo
done
