import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_tmp = Path(tempfile.mkdtemp(prefix="wf-test-"))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{(_tmp / 'test.sqlite3').as_posix()}")
os.environ.setdefault("WORK_DIR", str(_tmp / "work"))
