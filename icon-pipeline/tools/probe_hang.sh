#!/usr/bin/env bash
# Capture the state of the running ComfyUI before we terminate the distro.
P=$(pgrep -f "main.py --enable-manager" | head -1)
if [ -z "$P" ]; then echo "no comfy process found"; exit 0; fi
echo "pid=$P"
echo "cwd=$(readlink /proc/$P/cwd)"
echo "cmdline=$(tr '\0' ' ' < /proc/$P/cmdline)"
echo "etime_s=$(ps -o etimes= -p $P | tr -d ' ')"
echo "pcpu=$(ps -o %cpu= -p $P | tr -d ' ')"
echo "rss_MiB=$(ps -o rss= -p $P | awk '{print int($1/1024)}')"
echo "state=$(awk '/^State/{print $2, $3}' /proc/$P/status)"
echo "wchan=$(cat /proc/$P/wchan)"
echo "--- busiest threads ---"
ps -T -p $P -o tid,etimes,pcpu,stat,comm --sort=-pcpu | head -6
echo "--- thread stacks of top-2 ---"
for t in $(ps -T -p $P -o tid,pcpu --sort=-pcpu --no-headers | head -2 | awk '{print $1}'); do
  echo "tid=$t wchan=$(cat /proc/$P/task/$t/wchan 2>/dev/null) state=$(awk '/^State/{print $2}' /proc/$P/task/$t/status 2>/dev/null)"
done
echo "--- system ---"
echo "loadavg=$(cat /proc/loadavg)"
free -m | head -2
echo "--- swap ---"; swapon --show 2>/dev/null | head -3 || echo "(none)"
echo "--- outputs ---"
ls -la /data/ComfyUI/output/p0test 2>/dev/null || echo "(no p0test dir)"
echo "--- gpu ---"
nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader 2>/dev/null || echo "(no nvidia-smi)"
