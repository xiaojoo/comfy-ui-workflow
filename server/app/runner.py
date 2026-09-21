"""Serial execution of batches and of the L5.5 -> L5.6 -> L6 stages.

max_workers=1 is not a performance shortcut, it is the constraint the hardware
imposed: ComfyUI serves one graph at a time and the WSL distro is capped at
15.5 GiB with no swap, where a 3D run at octree 256 was measured to leave 89 MiB
free. Concurrent submissions here do not parallelise, they wedge the box -- which
this session reproduced twice.
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from . import gates
from .db import Session
from .gates import Kit
from .models import Asset, Batch


class Runner:
    def __init__(self):
        self._ex = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pipeline")
        self._lock = threading.Lock()
        self._ahead = 0

    def submit(self, batch_id):
        with self._lock:
            self._ahead += 1
            pos = self._ahead
        fut = self._ex.submit(self._process, batch_id)

        def done(_):
            with self._lock:
                self._ahead -= 1

        fut.add_done_callback(done)
        return pos

    def depth(self):
        with self._lock:
            return self._ahead

    def _process(self, batch_id):
        with Session() as s:
            batch = s.get(Batch, batch_id)
            if batch is None:
                return
            batch.state = "running"
            s.commit()
            kit = Kit(raw=batch.kit)
            rows = [(a.id, a.source_png, a.raw_svg) for a in batch.assets]

        try:
            for aid, src, raw in rows:
                norm, flat, gate, meta = run_stages(src, raw, kit)
                with Session() as s:
                    a = s.get(Asset, aid)
                    a.norm_svg, a.flat_svg, a.gate, a.meta = norm, flat, gate, meta
                    a.verdict = gate["verdict"]
                    s.commit()
        except Exception as e:
            with Session() as s:
                b = s.get(Batch, batch_id)
                b.state = "error"
                b.error = f"{type(e).__name__}: {e}"
                b.finished_at = datetime.now(timezone.utc)
                s.commit()
            raise

        with Session() as s:
            b = s.get(Batch, batch_id)
            b.state = "done"
            b.finished_at = datetime.now(timezone.utc)
            s.commit()


def run_stages(source_png, raw_svg, kit):
    """norm -> flat -> gate, plus the pre-stage numbers for the before/after column.

    Both readings are kept because the whole point of the table is the delta:
    'repaired N, regressed M' is what made these stages trustworthy in the first
    place, and it cannot be recovered after the fact.
    """
    norm_svg, nmeta = gates.normalise(raw_svg, kit)
    flat_svg, drift = gates.flatten(norm_svg, kit)
    gate = gates.measure(source_png, flat_svg, kit)
    pre = gates.measure(source_png, raw_svg, kit)
    meta = {
        "normalise": nmeta,
        "flatten": {"drift_entries": len(drift), "dropped_paths": drift.get("dropped", 0)},
        # Full pre-stage reading, kept so the parity test can compare the API's
        # numbers against the CLI's text table for the same input.
        "before_stages": pre,
    }
    return norm_svg, flat_svg, gate, meta


runner = Runner()
