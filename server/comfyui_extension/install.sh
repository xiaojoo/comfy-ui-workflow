#!/usr/bin/env bash
# Install the studio_loader front-end extension into ComfyUI. Run it from Windows with:
#
#   wsl -d ComfyUI -- bash /mnt/h/workflow/server/comfyui_extension/install.sh
#
# ComfyUI registers /extensions/<name> routes only at startup (server.py:1247), so the engine
# has to be restarted afterwards before the desk app's 「在 ComfyUI 打开」 gets an answer.
# Without it the feature still works one click slower: the pushed file is listed under the
# engine's own Workflow menu.
set -eu
SRC=$(cd "$(dirname "$0")/studio_loader" && pwd)
DST=/data/ComfyUI/custom_nodes/studio_loader
mkdir -p "$DST/web_extensions"
cp "$SRC/__init__.py" "$DST/__init__.py"
cp "$SRC/web_extensions/studio_load.js" "$DST/web_extensions/studio_load.js"
find "$DST" -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
echo "installed -> $DST"
echo "check after restart: curl -s http://127.0.0.1:8188/extensions | grep studio_loader"
