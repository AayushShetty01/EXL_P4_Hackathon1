"""Gate decisions: approve, reject, review time, the independence rule and automatic approvals."""

import pytest
from sqlalchemy import Engine
from sqlmodel import Session, select

from app.api_schemas import GateDecisionRequest
from app.audit_trail import list_events
from app.database import ModelRow, RunRow, StageRunRow
from app.gate_decisions import GateError, record_automatic_approval, record_decision, seconds_between
from app.schemas import STAGE_NAMES


def add_run(engine: Engine, run_id: str, awaiting: str, approved: dict[str, str] | None = None) -> None:
    """Store model M001 and a run whose given stage awaits review; earlier stages may be approved."""
    with Session(engine) as session:
        if session.get(ModelRow, "M001") is None:
            session.add(
                ModelRow(
                    model_id="M001",
                    source="estate",
                    folder="model_estate/M001",
                    language="SAS",
                    revalidation_required=True,
                    created_at="2026-11-15T10:00:00Z",
                    updated_at="2026-11-15T10:00:00Z",
                )
            )
        session.add(
            RunRow(
                run_id=run_id, model_id="M001", status="AWAITING_REVIEW", started_at=f"2026-11-15T1{run_id[-1]}:00:00Z"
            )
        )
        for position, stage in enumerate(STAGE_NAMES):
            row = StageRunRow(run_id=run_id, stage=stage, position=position)
            if stage == awaiting:
                row.status, row.awaiting_review_since = "AWAITING_REVIEW", "2026-01-01T00:00:00Z"
            elif approved and stage in approved:
                row.status = "APPROVED"
                row.gate = {
                    "decision": "approve",
                    "reviewer": approved[stage],
                    "role": "developer",
                    "comment": None,
                    "decided_at": "2026-11-15T10:00:00Z",
                    "review_seconds": 5,
                }
            session.add(row)
        session.commit()


def decision(reviewer: str, choice: str = "approve") -> GateDecisionRequest:
    """A decision by one reviewer."""
    return GateDecisionRequest(decision=choice, reviewer=reviewer, role="validator", comment="checked")


def stage_of(engine: Engine, run_id: str, stage: str) -> StageRunRow:
    """Read one stage row."""
    with Session(engine) as session:
        return session.exec(select(StageRunRow).where(StageRunRow.run_id == run_id, StageRunRow.stage == stage)).one()


def test_approval_records_the_gate_and_review_time(engine: Engine) -> None:
    """The decision, reviewer and seconds since the stage awaited review are stored and audited."""
    add_run(engine, "run_M001_001", "discover")
    record_decision(engine, "run_M001_001", "discover", decision("owner_a"))
    row = stage_of(engine, "run_M001_001", "discover")
    assert row.status == "APPROVED"
    assert row.gate["reviewer"] == "owner_a" and row.gate["review_seconds"] > 0
    with Session(engine) as session:
        [event] = list_events(session)
    assert (event.action, event.actor_type, event.actor) == ("gate_decision", "human", "owner_a")


def test_reject_closes_the_run(engine: Engine) -> None:
    """A rejection sets the stage and the run to REJECTED with a finish time."""
    add_run(engine, "run_M001_001", "document")
    record_decision(engine, "run_M001_001", "document", decision("owner_a", "reject"))
    with Session(engine) as session:
        run = session.get(RunRow, "run_M001_001")
    assert (run.status, stage_of(engine, "run_M001_001", "document").status) == ("REJECTED", "REJECTED")
    assert run.finished_at


def test_redevelopment_approver_cannot_approve_validation(engine: Engine) -> None:
    """The same reviewer (any case) is refused with INDEPENDENCE_VIOLATION; another reviewer passes."""
    add_run(engine, "run_M001_001", "validate", approved={"redevelop": "developer_a"})
    with pytest.raises(GateError) as raised:
        record_decision(engine, "run_M001_001", "validate", decision(" Developer_A "))
    assert (raised.value.status_code, raised.value.code) == (409, "INDEPENDENCE_VIOLATION")
    record_decision(engine, "run_M001_001", "validate", decision("validator_b"))
    with Session(engine) as session:
        assert session.get(ModelRow, "M001").revalidation_required is False


def test_independence_also_holds_for_a_revalidation_run(engine: Engine) -> None:
    """In a validate-only run, the approver of the earlier redevelopment is still refused."""
    add_run(engine, "run_M001_001", "monitor", approved={"redevelop": "developer_a"})
    add_run(engine, "run_M001_002", "validate")
    with pytest.raises(GateError):
        record_decision(engine, "run_M001_002", "validate", decision("developer_a"))


def test_rejecting_validation_is_always_allowed(engine: Engine) -> None:
    """The independence rule applies to approvals only."""
    add_run(engine, "run_M001_001", "validate", approved={"redevelop": "developer_a"})
    record_decision(engine, "run_M001_001", "validate", decision("developer_a", "reject"))
    assert stage_of(engine, "run_M001_001", "validate").status == "REJECTED"


def test_decision_on_a_closed_gate_is_refused(engine: Engine) -> None:
    """Only a stage that awaits review can be decided."""
    add_run(engine, "run_M001_001", "discover")
    with pytest.raises(GateError) as raised:
        record_decision(engine, "run_M001_001", "monitor", decision("owner_a"))
    assert raised.value.code == "GATE_NOT_OPEN"


def test_automatic_approval_uses_demo_reviewers_and_is_marked(engine: Engine) -> None:
    """Seeding runs approve with demo_validator at the validate gate and say so in the audit trail."""
    add_run(engine, "run_M001_001", "validate", approved={"redevelop": "demo_developer"})
    record_automatic_approval(engine, "run_M001_001", "validate")
    assert stage_of(engine, "run_M001_001", "validate").gate["reviewer"] == "demo_validator"
    with Session(engine) as session:
        [event] = list_events(session)
    assert (event.actor_type, event.detail["automatic"]) == ("system", True)


def test_seconds_between() -> None:
    """Whole seconds between two timestamps, zero without a start."""
    assert seconds_between("2026-11-15T10:00:00Z", "2026-11-15T10:01:29Z") == 89
    assert seconds_between(None, "2026-11-15T10:01:29Z") == 0
