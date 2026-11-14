"""The hash chained audit trail: valid chains pass, any tampering is detected."""

import pytest
from sqlmodel import Session

from app.audit_trail import (
    GENESIS_HASH,
    AuditRecorder,
    append_event,
    compute_hash,
    event_content,
    list_events,
    verify_chain,
)
from app.database import AuditEventRow


def append_three(session: Session) -> None:
    """Write three events for two models."""
    append_event(
        session, actor_type="system", actor="factory_core", action="stage_started", model_id="M001", stage="discover"
    )
    append_event(
        session,
        actor_type="human",
        actor="reviewer_a",
        action="gate_decision",
        model_id="M001",
        run_id="run_M001_001",
        stage="discover",
        detail={"decision": "approve", "role": "owner", "comment": "Looks right"},
    )
    append_event(session, actor_type="agent", actor="documentation_agent", action="llm_call", model_id="M002")


def test_empty_chain_is_valid(session: Session) -> None:
    """A trail with no events has nothing to break."""
    assert verify_chain(session) is True


def test_events_link_to_each_other(session: Session) -> None:
    """Each event points at the hash of the event before it, starting from the genesis hash."""
    append_three(session)
    events = list_events(session)
    assert [event.seq for event in events] == [1, 2, 3]
    assert events[0].prev_hash == GENESIS_HASH
    assert events[1].prev_hash == events[0].hash
    assert events[2].hash == compute_hash(events[1].hash, event_content(events[2]))
    assert verify_chain(session) is True


def test_changing_a_stored_event_breaks_the_chain(session: Session) -> None:
    """Editing the detail of one event makes chain_valid false."""
    append_three(session)
    event = session.get(AuditEventRow, 2)
    event.detail = {"decision": "approve", "role": "owner", "comment": "Changed afterwards"}
    session.add(event)
    session.commit()
    assert verify_chain(session) is False


def test_recomputing_one_hash_still_breaks_the_chain(session: Session) -> None:
    """Fixing the hash of an edited event does not help: the next event no longer links to it."""
    append_three(session)
    event = session.get(AuditEventRow, 2)
    event.actor = "someone_else"
    event.hash = compute_hash(event.prev_hash, event_content(event))
    session.add(event)
    session.commit()
    assert verify_chain(session) is False


def test_removing_an_event_breaks_the_chain(session: Session) -> None:
    """Deleting an event in the middle is detected."""
    append_three(session)
    session.delete(session.get(AuditEventRow, 2))
    session.commit()
    assert verify_chain(session) is False


def test_unknown_action_is_refused(session: Session) -> None:
    """Only the actions listed in the contract can be written."""
    with pytest.raises(ValueError, match="action"):
        append_event(session, actor_type="system", actor="factory_core", action="model_deleted")


def test_list_events_filters_and_limits(session: Session) -> None:
    """Filtering by model and limiting keep the newest events, oldest first."""
    append_three(session)
    assert [event.seq for event in list_events(session, model_id="M001")] == [1, 2]
    assert [event.seq for event in list_events(session, limit=2)] == [2, 3]


def test_recorder_binds_model_run_and_stage(engine) -> None:
    """Events written through a recorder carry its model, run and stage, and keep the chain valid."""
    recorder = AuditRecorder(engine, model_id="M001", run_id="run_M001_001", stage="document")
    recorder.llm_call("documentation_agent", {"step": "section:overview", "cached": True})
    recorder.service_call({"service": "validation_lab", "endpoint": "POST /validate", "outcome": "ok"})
    recorder.tool_call("evidence_verifier", {"claims": 3, "verified": 3})
    with Session(engine) as session:
        events = list_events(session)
        assert verify_chain(session) is True
    assert [(event.action, event.actor_type, event.actor) for event in events] == [
        ("llm_call", "agent", "documentation_agent"),
        ("service_call", "system", "validation_lab"),
        ("tool_call", "system", "evidence_verifier"),
    ]
    assert {(event.model_id, event.run_id, event.stage) for event in events} == {("M001", "run_M001_001", "document")}
