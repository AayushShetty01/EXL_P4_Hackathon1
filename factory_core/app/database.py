"""SQLite tables of factory_core (models, runs, stage runs, stage outputs, audit events) and their helpers.

The database file is artifacts/factory_core.db. JSON columns hold contract shaped payloads.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import Request
from sqlalchemy import JSON, Column, Engine, event
from sqlmodel import Field, Session, SQLModel, col, create_engine, delete, select

from app.api_schemas import GateRecord, Run, StageRun
from app.schemas import STAGE_NAMES

OutputKind = Literal[
    "inventory_record", "documentation", "redevelopment", "validation_view", "monitoring", "compliance"
]


class ModelRow(SQLModel, table=True):
    """A registered model, from the estate or the built-in sample."""

    __tablename__ = "models"

    model_id: str = Field(primary_key=True)
    source: str
    folder: str
    language: str
    registration: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    revalidation_required: bool = False
    active_run_id: str | None = None
    created_at: str
    updated_at: str


class RunRow(SQLModel, table=True):
    """One pipeline run of one model."""

    __tablename__ = "runs"

    run_id: str = Field(primary_key=True)
    model_id: str = Field(index=True)
    status: str
    current_stage: str | None = None
    auto_approve: bool = False
    started_at: str
    finished_at: str | None = None


class StageRunRow(SQLModel, table=True):
    """One stage inside a run, with its gate decision."""

    __tablename__ = "stage_runs"

    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(index=True)
    stage: str
    position: int
    status: str = "PENDING"
    started_at: str | None = None
    finished_at: str | None = None
    duration_seconds: float | None = None
    summary: str | None = None
    skip_reason: str | None = None
    error: str | None = None
    awaiting_review_since: str | None = None
    gate: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))


class StageOutputRow(SQLModel, table=True):
    """A contract shaped result produced by a stage, such as the documentation of a model."""

    __tablename__ = "stage_outputs"

    id: int | None = Field(default=None, primary_key=True)
    model_id: str = Field(index=True)
    run_id: str | None = None
    stage: str | None = None
    kind: str = Field(index=True)
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: str


class AuditEventRow(SQLModel, table=True):
    """One event of the append only, hash chained audit trail."""

    __tablename__ = "audit_events"

    seq: int = Field(primary_key=True)
    ts: str
    model_id: str | None = Field(default=None, index=True)
    run_id: str | None = None
    stage: str | None = None
    actor_type: str
    actor: str
    action: str
    detail: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    prev_hash: str
    hash: str


def utc_timestamp() -> str:
    """Current time as an ISO 8601 UTC string, for example 2026-11-15T10:02:11Z."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def create_database_engine(database_path: Path) -> Engine:
    """Open (and create when missing) the SQLite database with every table."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{database_path}", connect_args={"check_same_thread": False, "timeout": 30})

    @event.listens_for(engine, "connect")
    def use_write_ahead_log(connection: Any, record: Any) -> None:
        """Let readers work while a pipeline thread writes, and wait instead of failing on a busy file."""
        cursor = connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

    SQLModel.metadata.create_all(engine)
    return engine


def get_session(request: Request) -> Iterator[Session]:
    """FastAPI dependency that yields one database session per request."""
    with Session(request.app.state.engine) as session:
        yield session


def save_stage_output(
    session: Session, model_id: str, run_id: str | None, stage: str | None, kind: OutputKind, payload: dict[str, Any]
) -> None:
    """Store a stage result. The newest row of a kind is the one the API serves."""
    session.add(
        StageOutputRow(
            model_id=model_id, run_id=run_id, stage=stage, kind=kind, payload=payload, created_at=utc_timestamp()
        )
    )


def latest_stage_output(session: Session, model_id: str, kind: OutputKind) -> dict[str, Any] | None:
    """Return the newest stored result of a kind for a model, or None."""
    statement = (
        select(StageOutputRow)
        .where(StageOutputRow.model_id == model_id, StageOutputRow.kind == kind)
        .order_by(col(StageOutputRow.id).desc())
    )
    row = session.exec(statement).first()
    return row.payload if row else None


def latest_run_id(session: Session, model_id: str) -> str | None:
    """Return the id of the most recently started run of a model, or None."""
    statement = select(RunRow).where(RunRow.model_id == model_id).order_by(col(RunRow.started_at).desc())
    row = session.exec(statement).first()
    return row.run_id if row else None


def pipeline_status(session: Session, model: ModelRow) -> dict[str, str]:
    """Stage statuses of the active (or latest) run of a model; PENDING when there is no run."""
    status = {stage: "PENDING" for stage in STAGE_NAMES}
    run_id = model.active_run_id or latest_run_id(session, model.model_id)
    if run_id:
        for row in session.exec(select(StageRunRow).where(StageRunRow.run_id == run_id)):
            status[row.stage] = row.status
    return status


def load_run(session: Session, run_id: str) -> Run | None:
    """Build the contract shaped Run from its rows, or return None when the run does not exist."""
    run = session.get(RunRow, run_id)
    if run is None:
        return None
    rows = session.exec(
        select(StageRunRow).where(StageRunRow.run_id == run_id).order_by(col(StageRunRow.position))
    ).all()
    stages = [
        StageRun(
            stage=row.stage,
            status=row.status,
            started_at=row.started_at,
            finished_at=row.finished_at,
            duration_seconds=row.duration_seconds,
            summary=row.summary,
            skip_reason=row.skip_reason,
            error=row.error,
            gate=GateRecord.model_validate(row.gate) if row.gate else None,
        )
        for row in rows
    ]
    return Run(
        run_id=run.run_id,
        model_id=run.model_id,
        status=run.status,
        current_stage=run.current_stage,
        auto_approve=run.auto_approve,
        stages=stages,
        started_at=run.started_at,
        finished_at=run.finished_at,
        total_agent_seconds=round(sum(stage.duration_seconds or 0.0 for stage in stages), 1),
        total_review_seconds=sum(stage.gate.review_seconds for stage in stages if stage.gate),
    )


def delete_model_data(session: Session, model_id: str) -> None:
    """Remove a model with its runs, stage runs and outputs. Audit events are never removed."""
    run_ids = list(session.exec(select(RunRow.run_id).where(RunRow.model_id == model_id)))
    if run_ids:
        session.exec(delete(StageRunRow).where(col(StageRunRow.run_id).in_(run_ids)))
    session.exec(delete(RunRow).where(RunRow.model_id == model_id))
    session.exec(delete(StageOutputRow).where(StageOutputRow.model_id == model_id))
    session.exec(delete(ModelRow).where(ModelRow.model_id == model_id))
