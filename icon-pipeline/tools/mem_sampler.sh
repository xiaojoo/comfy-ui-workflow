#!/usr/bin/env bash
# Sample host memory + ComfyUI RSS once a second so a hang can be told apart from
# a slow computation. Writes CSV to the run dir; kill by removing the flag file.
OUT=${1:-/mnt/h/workflow/icon-pipeline/run/mem.csv}
STOP=${2:-/mnt/h/workflow/icon-pipeline/run/.sampler_stop}
rm -f "$STOP"
echo "t_s,mem_total_mib,mem_used_mib,mem_avail_mib,swap_used_mib,comfy_rss_mib,comfy_pcpu,gpu_used_mib" > "$OUT"
T0=$(date +%s)
while [ ! -f "$STOP" ]; do
  P=$(pgrep -f "main.py --enable-manager" | head -1)
  RSS=$( [ -n "$P" ] && awk '{print int($1/1024)}' /proc/$P/statm 2>/dev/null || echo -1 )
  PCPU=$( [ -n "$P" ] && ps -o %cpu= -p $P 2>/dev/null | tr -d ' ' || echo -1 )
  GPU=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | tr -d ' ')
  MEM=$(free -m | awk 'NR==2{print $2","$3","$7}')
  SW=$(free -m | awk 'NR==3{print $3}')
  echo "$(($(date +%s)-T0)),$MEM,$SW,${RSS:--1},${PCPU:-?},${GPU:--1}" >> "$OUT"
  sleep 1
done
echo "sampler stopped" >> "$OUT"
