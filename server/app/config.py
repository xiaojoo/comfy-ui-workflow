"""Single source of truth for paths and endpoints.

Everything is env-overridable because the two halves of this system live on
different sides of the WSL boundary: ComfyUI runs inside the distro (which has no
network), while this server runs on Windows and reaches it over 127.0.0.1.
"""

import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PIPELINE = REPO / "icon-pipeline"
TOOLS = PIPELINE / "tools"
FIXTURES = PIPELINE / "fixtures"
WORKFLOWS = PIPELINE / "workflows"
BRAND_KIT = Path(os.environ.get("BRAND_KIT", PIPELINE / "brand-kit.example.json"))

COMFY = os.environ.get("COMFY_URL", "http://127.0.0.1:8188")
# Windows-side scratch for submitted graphs and fetched artefacts.
WORK = Path(os.environ.get("WORK_DIR", REPO / "server" / "work"))
DB_URL = os.environ.get("DATABASE_URL", f"sqlite:///{(REPO / 'server' / 'app.sqlite3').as_posix()}")

# ComfyUI writes under the distro's filesystem; Windows sees it through this root.
# Overridable because the distro name is deployment-specific.
COMFY_OUTPUT_ROOT = Path(os.environ.get("COMFY_OUTPUT_ROOT", r"\\wsl.localhost\ComfyUI\data\ComfyUI\output"))
