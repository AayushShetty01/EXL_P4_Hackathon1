"""What every pipeline stage shares, and the stage lifecycle.

A stage moves PENDING -> RUNNING -> AWAITING_REVIEW, or ends FAILED or SKIPPED. Durations, summaries,
errors and audit events are recorded here, so each stage only does its own work.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

import httpx
from sqlalchemy import Engine
from sqlmodel import Session, select

from app.audit_trail import AuditRecorder
from app.config import Settings
from app.database import ModelRow, RunRow, StageRunRow, utc_timestamp
from app.estate_scanner import EstateScanError, FileAccessError
from app.llm_client import LLMClient, LLMError, Provider
from app.service_clients import ServiceCallError, ServiceClients

logger = logging.getLogger("factory_core")


class StageError(Exception):
    """A stage cannot finish; the message is shown as the stage error."""


@dataclass(frozen=True)
class PipelineContext:
    """Settings, database and clients for the stages; tests pass a scripted LLM and a service transport."""

    settings: Settings
    engine: Engine
    llm_provider: Provider | None = None
    service_transport: httpx.BaseTransport | None = None
    today: Callable[[], date] = field(default=date.today)

    def llm(self, recorder: AuditRecorder, actor: str) -> LLMClient:
        """An LLM client whose every call is written to the audit trail under the agent's name."""
        return LLMClient(
            self.settings,
            provider=self.llm_provider,
            on_call=lambda response: recorder.llm_call(actor, response.trace()),
        )

    def services(self, recorder: AuditRecorder) -> ServiceClients:
        """Clients for redev_engine and validation_lab whose calls are written to the audit trail."""
        return ServiceClients(self.settings, transport=self.service_transport, on_call=recorder.service_call)


@dataclass
class StageWork:
    """One stage of one run, handed to the function that does the stage's work."""

    context: PipelineContext
    session: Session
    model: ModelRow
    run: RunRow
    recorder: AuditRecorder


StageFunction = Callable[[StageWork], str]


def error_text(error: object, default: str = "no detail given") -> str:
    """Readable text of a service error field, which may be text or an {"code", "message"} object."""
    if isinstance(error, dict):
        return str(error.get("message") or error.get("code") or error)
    return str(error) if error else default


def stage_error_message(error: Exception) -> str:
    """Known failures keep their own clear message; anything unexpected is prefixed with its type."""
    if isinstance(error, (StageError, LLMError, ServiceCallError, FileAccessError, EstateScanError)):
        return str(error)
    return f"{type(error).__name__}: {error}"


def skip_reason(stage: str, model: ModelRow) -> str | None:
    """Why a stage does not apply to a model, or None when it applies."""
    manifest = model.registration.get("manifest") or {}
    if stage == "redevelop" and not manifest.get("redevelop", False):
        if model.language == "Python":
            return "The model is already in Python, so there is nothing to redevelop."
        return "The manifest marks this model as not to be redeveloped."
    if stage in ("validate", "monitor") and not manifest.get("data"):
        return f"The model has no data, so it cannot be {'validated' if stage == 'validate' else 'monitored'}."
    return None


def stage_row(session: Session, run_id: str, stage: str) -> StageRunRow:
    """The row of one stage of a run."""
    row = session.exec(select(StageRunRow).where(StageRunRow.run_id == run_id, StageRunRow.stage == stage)).first()
    if row is None:
        raise StageError(f"Run {run_id} has no {stage} stage")
    return row


def stage_status(engine: Engine, run_id: str, stage: str) -> str:
    """The current status of one stage, read fresh from the database."""
    with Session(engine) as session:
        return stage_row(session, run_id, stage).status


def execute_stage(context: PipelineContext, run_id: str, stage: str, work: StageFunction) -> str:
    """Run one stage through its lifecycle and return its final status. A finished stage is never rerun."""
    recorder = AuditRecorder(context.engine, run_id=run_id, stage=stage)
    with Session(context.engine) as session:
        row = stage_row(session, run_id, stage)
        if row.status != "PENDING":
            return row.status
        run = session.get(RunRow, run_id)
        model = session.get(ModelRow, run.model_id)
        recorder = AuditRecorder(context.engine, model_id=model.model_id, run_id=run_id, stage=stage)
        reason = skip_reason(stage, model)
        if reason:
            row.status, row.skip_reason = "SKIPPED", reason
            session.add(row)
            session.commit()
            recorder.record("stage_skipped", detail={"reason": reason})
            return "SKIPPED"
        started = time.perf_counter()
        row.status, row.started_at = "RUNNING", utc_timestamp()
        run.status, run.current_stage = "RUNNING", stage
        session.add_all([row, run])
        session.commit()
        recorder.record("stage_started")
        try:
            summary = work(StageWork(context, session, model, run, recorder))
        except Exception as error:  # every failure must end the stage visibly, never kill the run thread silently
            session.rollback()
            message = stage_error_message(error)
            logger.warning("The %s stage of a run failed; the error is stored with the run", stage)
            return fail_stage(context, run_id, stage, message, time.perf_counter() - started, recorder)
        row = stage_row(session, run_id, stage)
        run = session.get(RunRow, run_id)
        now = utc_timestamp()
        row.status, row.finished_at, row.summary = "AWAITING_REVIEW", now, summary
        row.duration_seconds = round(time.perf_counter() - started, 1)
        row.awaiting_review_since = now
        run.status = "AWAITING_REVIEW"
        session.add_all([row, run])
        session.commit()
    recorder.record("stage_completed", detail={"summary": summary})
    return "AWAITING_REVIEW"


def fail_stage(
    context: PipelineContext, run_id: str, stage: str, message: str, seconds: float, recorder: AuditRecorder
) -> str:
    """Mark a stage and its run FAILED with the error message."""
    with Session(context.engine) as session:
        row = stage_row(session, run_id, stage)
        run = session.get(RunRow, run_id)
        now = utc_timestamp()
        row.status, row.error, row.finished_at, row.duration_seconds = "FAILED", message, now, round(seconds, 1)
        run.status, run.finished_at = "FAILED", now
        session.add_all([row, run])
        session.commit()
    recorder.record("stage_failed", detail={"error": message})
    return "FAILED"
