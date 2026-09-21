#!/usr/bin/env bash
# Relaunch ComfyUI exactly as it was started (argv from /system_stats: main.py --enable-manager).
cd /data/ComfyUI || exit 1
mkdir -p user/logs
LOG=/data/ComfyUI/user/logs/agent_relaunch_$(date +%Y%m%d_%H%M%S).log
setsid nohup /data/ComfyUI/venv/bin/python main.py --enable-manager > "$LOG" 2>&1 < /dev/null &
echo "pid=$!"
echo "log=$LOG"
echo "$LOG" > /data/ComfyUI/user/logs/.latest
