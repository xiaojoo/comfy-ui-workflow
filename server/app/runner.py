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

from . import comfy, gates, templates
from .db import Session
from .gates import Kit
from .models import Asset, Batch, Task


def _entry(msg):
    """One line of the execution log. Timestamped UTC; the viewer renders local."""
    return {"ts": datetime.now(timezone.utc).isoformat(), "msg": msg}


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

    def submit_task(self, task_id):
        with self._lock:
            self._ahead += 1
            pos = self._ahead
        fut = self._ex.submit(self._process_task, task_id)

        def done(_):
            with self._lock:
                self._ahead -= 1

        fut.add_done_callback(done)
        return pos

    def _process_task(self, task_id):
        """One generation run, with the stage log the right-hand panel shows.

        Progress is stage-based, not a diffusion step counter: we can see which
        stage we are in, and we cannot see inside ComfyUI's sampler without a
        second connection, so the bar says what it actually knows.
        """
        with Session() as s:
            t = s.get(Task, task_id)
            if t is None:
                return
            tpl = templates.BY_ID[t.template]
            t.state, t.progress = "running", 5
            t.log = [_entry("任务开始")]
            s.commit()
            params, title = dict(t.params), t.title

        def stage(pct, msg, log):
            log = log + [_entry(msg)]
            with Session() as s:
                t = s.get(Task, task_id)
                t.progress, t.log = pct, log
                s.commit()
            return log

        log = t.log
        try:
            log = stage(15, "装配工作流图", log)
            graph = templates.graph_for(tpl, params)
            log = stage(30, f"提交 ComfyUI（{tpl['model']}）", log)
            pid = comfy.submit(graph, f"studio-{task_id}")
            with Session() as s:
                s.get(Task, task_id).comfy_id = pid
                s.commit()
            log = stage(55, f"排队与采样中 · prompt {pid[:8]}", log)
            status, files, secs = comfy.collect(pid)
            if status != "success":
                raise RuntimeError(f"{status}")
            log = stage(90, f"生成完成 · {secs:.1f}s · {len(files)} 个文件", log)
            with Session() as s:
                t = s.get(Task, task_id)
                t.state, t.progress, t.log = "done", 100, log + [_entry("任务成功")]
                t.seconds, t.error = secs, None
                t.outputs = [{"subfolder": f["subfolder"], "filename": f["filename"],
                              "url": comfy.view_url(f["subfolder"], f["filename"])} for f in files]
                t.finished_at = datetime.now(timezone.utc)
                s.commit()
        except Exception as e:
            with Session() as s:
                t = s.get(Task, task_id)
                t.state, t.error, t.finished_at = "error", f"{type(e).__name__}: {e}", datetime.now(timezone.utc)
                t.log = log + [_entry(t.error)]
                s.commit()

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
