"""Database tables and helpers: stage outputs, run views, pipeline status and model removal."""

from sqlmodel import Session

from app.audit_trail import append_event, list_events
from app.database import (
    ModelRow,
    RunRow,
    StageRunRow,
    delete_model_data,
    latest_stage_output,
    load_run,
    pipeline_status,
    save_stage_output,
    utc_timestamp,
)


def add_model_with_run(session: Session) -> ModelRow:
    """Store a model with one run whose discover stage was approved after review."""
    now = utc_timestamp()
    model = ModelRow(
        model_id="M900", source="estate", folder="model_estate/M900", language="R", created_at=now, updated_at=now
    )
    session.add(model)
    session.add(
        RunRow(run_id="run_M900_001", model_id="M900", status="RUNNING", current_stage="document", started_at=now)
    )
    gate = {
        "decision": "approve",
        "reviewer": "owner_a",
        "role": "owner",
        "comment": None,
        "decided_at": now,
        "review_seconds": 40,
    }
    session.add(
        StageRunRow(
            run_id="run_M900_001", stage="discover", position=0, status="APPROVED", duration_seconds=12.5, gate=gate
        )
    )
    session.add(
        StageRunRow(run_id="run_M900_001", stage="document", position=1, status="RUNNING", duration_seconds=3.0)
    )
    session.commit()
    return model


def test_utc_timestamp_format() -> None:
    """Timestamps are ISO 8601 UTC with a Z suffix."""
    stamp = utc_timestamp()
    assert len(stamp) == 20 and stamp[10] == "T" and stamp.endswith("Z")


def test_latest_stage_output_returns_the_newest(session: Session) -> None:
    """The newest stored result of a kind wins; other kinds and models are separate."""
    save_stage_output(session, "M900", "run_1", "document", "documentation", {"version": 1})
    save_stage_output(session, "M900", "run_2", "document", "documentation", {"version": 2})
    save_stage_output(session, "M901", "run_3", "document", "documentation", {"version": 3})
    session.commit()
    assert latest_stage_output(session, "M900", "documentation") == {"version": 2}
    assert latest_stage_output(session, "M900", "monitoring") is None


def test_load_run_builds_the_contract_shape(session: Session) -> None:
    """A run view lists stages in order and totals agent and review time."""
    add_model_with_run(session)
    run = load_run(session, "run_M900_001")
    assert [stage.stage for stage in run.stages] == ["discover", "document"]
    assert run.stages[0].gate.reviewer == "owner_a"
    assert run.total_agent_seconds == 15.5
    assert run.total_review_seconds == 40
    assert load_run(session, "run_missing") is None


def test_pipeline_status_follows_the_latest_run(session: Session) -> None:
    """Stages without a row stay PENDING; stages of the run show their status."""
    model = add_model_with_run(session)
    assert pipeline_status(session, model) == {
        "discover": "APPROVED",
        "document": "RUNNING",
        "redevelop": "PENDING",
        "validate": "PENDING",
        "monitor": "PENDING",
    }


def test_delete_model_data_keeps_the_audit_trail(session: Session) -> None:
    """Removing a model removes its runs and outputs but never its audit events."""
    add_model_with_run(session)
    save_stage_output(session, "M900", "run_M900_001", "discover", "inventory_record", {"model_id": "M900"})
    append_event(session, actor_type="system", actor="test", action="stage_started", model_id="M900")
    delete_model_data(session, "M900")
    session.commit()
    assert session.get(ModelRow, "M900") is None
    assert load_run(session, "run_M900_001") is None
    assert latest_stage_output(session, "M900", "inventory_record") is None
    assert len(list_events(session, "M900")) == 1
