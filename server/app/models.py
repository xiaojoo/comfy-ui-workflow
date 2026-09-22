"""Schema for a single-machine, many-batch deployment.

Deliberately plain SQLite via SQLAlchemy so the same models migrate to Postgres
without rethinking the domain -- but no multi-user/roles yet, which is what
"single machine" bought us.
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def now():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Batch(Base):
    __tablename__ = "batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    kit: Mapped[dict] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String, default="queued", index=True)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)

    assets: Mapped[list["Asset"]] = relationship(back_populates="batch", cascade="all, delete-orphan")


class Task(Base):
    """One generation run: a template, its parameters, and what ComfyUI wrote back.

    Separate from Batch on purpose. A Task is "ask the model for pictures"; a Batch
    is "gate these deliverables". The two join when a generated image is sent
    through the gate, which is the point of the pipeline but not a step every task takes.
    """

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Derived from the row id, so it is only knowable after the first insert.
    ref: Mapped[str | None] = mapped_column(String, unique=True, index=True)
    template: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String, default="")
    model: Mapped[str] = mapped_column(String, default="")
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    state: Mapped[str] = mapped_column(String, default="queued", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    log: Mapped[list] = mapped_column(JSON, default=list)
    comfy_id: Mapped[str | None] = mapped_column(String)
    error: Mapped[str | None] = mapped_column(Text)
    outputs: Mapped[list] = mapped_column(JSON, default=list)
    favorite: Mapped[bool] = mapped_column(default=False)
    seconds: Mapped[float | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    source_png: Mapped[str] = mapped_column(String)
    raw_svg: Mapped[str] = mapped_column(Text)
    norm_svg: Mapped[str] = mapped_column(Text, default="")
    flat_svg: Mapped[str] = mapped_column(Text, default="")
    # provenance: which stage produced what, and the parameters that made it.
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    gate: Mapped[dict] = mapped_column(JSON, default=dict)
    verdict: Mapped[str] = mapped_column(String, default="UNVERIFIED", index=True)
    approval: Mapped[str] = mapped_column(String, default="pending")

    batch: Mapped[Batch] = relationship(back_populates="assets")


class Flow(Base):
    """A saved canvas: measured templates arranged into a chain, with each step's own overrides.

    The unit is a *template*, not a ComfyUI node. Compiling a chain into one graph would
    collide node ids between templates and ask the engine to hold several model sets at
    once, which on this box is not slow but fatal -- see the 15.5 GiB WSL ceiling.
    """

    __tablename__ = "flows"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    # As authored: {nodes: [{id, template, params, position}], edges: [{from, out, to, in, index}]}.
    # Compiled against the live registry at run time, so a template that has since changed
    # surfaces as a refusal rather than a half-run chain.
    graph: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class FlowRun(Base):
    """One execution of a canvas.

    The steps are Tasks, and nothing here duplicates them: a chain step is an ordinary
    generation run whose input happens to be another run's output, so progress, logs and
    artefacts stay on the task row. What this row owns is the ordering and the reason a
    later step never became a task at all.
    """

    __tablename__ = "flow_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    ref: Mapped[str | None] = mapped_column(String, unique=True, index=True)
    flow_id: Mapped[int] = mapped_column(ForeignKey("flows.id"), index=True)
    # [{node, template, task_id, error}] -- task_id is null until that step is submitted,
    # and stays null for every step after the one that stopped the chain.
    steps: Mapped[list] = mapped_column(JSON, default=list)
    state: Mapped[str] = mapped_column(String, default="queued", index=True)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
