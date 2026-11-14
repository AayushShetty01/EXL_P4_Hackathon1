"""Audit endpoint: events in contract shape and a chain_valid flag that detects tampering."""

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.api_schemas import Audit
from app.audit_trail import append_event
from app.database import AuditEventRow


def write_events(client: TestClient) -> None:
    """Append three events through the app's own database."""
    with Session(client.app.state.engine) as session:
        append_event(session, actor_type="system", actor="factory_core", action="stage_started", model_id="M001")
        append_event(
            session,
            actor_type="human",
            actor="reviewer_a",
            action="gate_decision",
            model_id="M001",
            detail={"decision": "approve"},
        )
        append_event(session, actor_type="agent", actor="discovery_agent", action="llm_call", model_id="M002")


def test_empty_trail(client: TestClient) -> None:
    """A fresh trail has no events and a valid chain."""
    assert client.get("/api/audit").json() == {"chain_valid": True, "events": []}


def test_events_filter_and_limit(client: TestClient) -> None:
    """Events come back in contract shape, filtered by model and limited to the newest."""
    write_events(client)
    body = client.get("/api/audit", params={"model_id": "M001"}).json()
    Audit.model_validate(body)
    assert [event["action"] for event in body["events"]] == ["stage_started", "gate_decision"]
    assert [event["seq"] for event in client.get("/api/audit", params={"limit": 1}).json()["events"]] == [3]


def test_tampering_shows_as_an_invalid_chain(client: TestClient) -> None:
    """Changing one stored event makes chain_valid false in the API."""
    write_events(client)
    with Session(client.app.state.engine) as session:
        event = session.get(AuditEventRow, 2)
        event.detail = {"decision": "reject"}
        session.add(event)
        session.commit()
    assert client.get("/api/audit").json()["chain_valid"] is False


def test_limit_must_be_positive(client: TestClient) -> None:
    """A limit of zero is an invalid request."""
    assert client.get("/api/audit", params={"limit": 0}).status_code == 422
