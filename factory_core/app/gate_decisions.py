"""Human decisions at stage gates: approve, reject, and the independence rule.

A reject stops the run. The validate gate cannot be approved by the reviewer who approved the
redevelop gate. Every decision is recorded with its review time and written to the audit trail.
"""

from datetime import datetime

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from app.api_schemas import GateDecisionRequest, GateRecord
from app.audit_trail import AuditRecorder
from app.database import ModelRow, RunRow, StageRunRow, utc_timestamp

AUTOMATIC_REVIEWERS = {"validate": ("demo_validator", "validator")}
DEFAULT_AUTOMATIC_REVIEWER = ("demo_developer", "developer")


class GateError(Exception):
    """A decision that cannot be recorded; carries the HTTP status and error code for the API."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        """Keep the HTTP status and error code for the API response."""
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def parse_timestamp(text: str) -> datetime:
    """Read an ISO UTC timestamp such as 2026-11-15T10:02:11Z."""
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def seconds_between(start: str | None, end: str) -> int:
    """Whole seconds between two ISO UTC timestamps; 0 when the start is unknown."""
    if not start:
        return 0
    return max(0, round((parse_timestamp(end) - parse_timestamp(start)).total_seconds()))


def redevelopment_approver(session: Session, run: RunRow) -> str | None:
    """Who approved redevelopment: in this run, or else in the latest earlier run of the model."""
    rows = session.exec(
        select(StageRunRow, RunRow)
        .join(RunRow, col(RunRow.run_id) == col(StageRunRow.run_id))
        .where(RunRow.model_id == run.model_id, StageRunRow.stage == "redevelop", StageRunRow.status == "APPROVED")
        .order_by(col(RunRow.started_at).desc())
    ).all()
    this_run_first = sorted(rows, key=lambda pair: pair[1].run_id != run.run_id)
    for stage_row, _ in this_run_first:
        if stage_row.gate and stage_row.gate.get("decision") == "approve":
            return stage_row.gate["reviewer"]
    return None


def record_decision(
    engine: Engine, run_id: str, stage: str, decision: GateDecisionRequest, *, automatic: bool = False
) -> None:
    """Check and store one gate decision, update the stage and run, and audit it."""
    with Session(engine) as session:
        run = session.get(RunRow, run_id)
        if run is None:
            raise GateError(404, "RUN_NOT_FOUND", f"Run {run_id} does not exist")
        model_id = run.model_id
        owner = session.get(ModelRow, model_id)
        if owner is not None and owner.source == "sample":
            raise GateError(409, "SAMPLE_MODEL", "The sample model from the contract examples is read only.")
        stage_row = session.exec(
            select(StageRunRow).where(StageRunRow.run_id == run_id, StageRunRow.stage == stage)
        ).first()
        if stage_row is None or stage_row.status != "AWAITING_REVIEW":
            status = stage_row.status if stage_row else "missing"
            raise GateError(409, "GATE_NOT_OPEN", f"The {stage} stage is not waiting for review (status {status}).")
        if stage == "validate" and decision.decision == "approve":
            developer = redevelopment_approver(session, run)
            if developer and developer.strip().lower() == decision.reviewer.strip().lower():
                raise GateError(
                    409,
                    "INDEPENDENCE_VIOLATION",
                    f"{decision.reviewer} approved the redevelop gate, "
                    "so a different reviewer must approve validation.",
                )
        now = utc_timestamp()
        stage_row.gate = GateRecord(
            decision=decision.decision,
            reviewer=decision.reviewer,
            role=decision.role,
            comment=decision.comment,
            decided_at=now,
            review_seconds=seconds_between(stage_row.awaiting_review_since, now),
        ).model_dump(mode="json")
        approved = decision.decision == "approve"
        stage_row.status = "APPROVED" if approved else "REJECTED"
        run.status = "RUNNING" if approved else "REJECTED"
        run.finished_at = None if approved else now
        if approved and stage == "validate" and owner is not None:
            owner.revalidation_required = False
            session.add(owner)
        session.add(stage_row)
        session.add(run)
        session.commit()
    AuditRecorder(engine, model_id=model_id, run_id=run_id, stage=stage).record(
        "gate_decision",
        actor_type="system" if automatic else "human",
        actor=decision.reviewer,
        detail={
            "decision": decision.decision,
            "role": decision.role,
            "comment": decision.comment,
            "automatic": automatic,
        },
    )


def record_automatic_approval(engine: Engine, run_id: str, stage: str) -> None:
    """Approve a gate for a seeding run (auto_approve) with the demo reviewers, marked as automatic."""
    reviewer, role = AUTOMATIC_REVIEWERS.get(stage, DEFAULT_AUTOMATIC_REVIEWER)
    decision = GateDecisionRequest(
        decision="approve", reviewer=reviewer, role=role, comment="Automatic approval for a seeded demo run."
    )
    record_decision(engine, run_id, stage, decision, automatic=True)
