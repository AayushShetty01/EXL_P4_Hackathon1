"""Append only, hash chained audit trail.

Each event hash is the SHA 256 of the previous hash plus the canonical JSON of the event,
so changing, inserting or removing a stored event breaks the chain.
"""

import hashlib
import json
import threading
from dataclasses import dataclass
from typing import Any, get_args

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from app.api_schemas import ActorType, AuditAction
from app.database import AuditEventRow, utc_timestamp

GENESIS_HASH = "0" * 64
ACTOR_TYPES = set(get_args(ActorType))
AUDIT_ACTIONS = set(get_args(AuditAction))
_append_lock = threading.Lock()


def canonical_json(value: Any) -> str:
    """Serialise with sorted keys and no spaces, so the same event always gives the same text."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def event_content(row: AuditEventRow) -> dict[str, Any]:
    """The fields of an event that its hash covers (everything except the two hashes)."""
    return {
        "seq": row.seq,
        "ts": row.ts,
        "model_id": row.model_id,
        "run_id": row.run_id,
        "stage": row.stage,
        "actor_type": row.actor_type,
        "actor": row.actor,
        "action": row.action,
        "detail": row.detail,
    }


def compute_hash(prev_hash: str, content: dict[str, Any]) -> str:
    """SHA 256 of the previous hash followed by the canonical JSON of the event."""
    return hashlib.sha256((prev_hash + canonical_json(content)).encode("utf-8")).hexdigest()


def append_event(
    session: Session,
    *,
    actor_type: str,
    actor: str,
    action: str,
    model_id: str | None = None,
    run_id: str | None = None,
    stage: str | None = None,
    detail: dict[str, Any] | None = None,
) -> AuditEventRow:
    """Add one event to the end of the chain and commit the session."""
    if actor_type not in ACTOR_TYPES:
        raise ValueError(f"Unknown audit actor_type {actor_type!r}")
    if action not in AUDIT_ACTIONS:
        raise ValueError(f"Unknown audit action {action!r}")
    with _append_lock:
        last = session.exec(select(AuditEventRow).order_by(col(AuditEventRow.seq).desc())).first()
        prev_hash = last.hash if last else GENESIS_HASH
        row = AuditEventRow(
            seq=last.seq + 1 if last else 1,
            ts=utc_timestamp(),
            model_id=model_id,
            run_id=run_id,
            stage=stage,
            actor_type=actor_type,
            actor=actor,
            action=action,
            detail=json.loads(canonical_json(detail or {})),
            prev_hash=prev_hash,
            hash="",
        )
        row.hash = compute_hash(prev_hash, event_content(row))
        session.add(row)
        session.commit()
        session.refresh(row)
    return row


def verify_chain(session: Session) -> bool:
    """Recompute every hash from the first event; False when any event was changed or removed."""
    prev_hash = GENESIS_HASH
    expected_seq = 1
    for row in session.exec(select(AuditEventRow).order_by(col(AuditEventRow.seq))):
        if row.seq != expected_seq or row.prev_hash != prev_hash:
            return False
        if row.hash != compute_hash(prev_hash, event_content(row)):
            return False
        prev_hash = row.hash
        expected_seq += 1
    return True


def list_events(session: Session, model_id: str | None = None, limit: int = 200) -> list[AuditEventRow]:
    """The newest events (optionally for one model), returned oldest first."""
    statement = select(AuditEventRow)
    if model_id:
        statement = statement.where(AuditEventRow.model_id == model_id)
    rows = session.exec(statement.order_by(col(AuditEventRow.seq).desc()).limit(limit)).all()
    return list(reversed(rows))


@dataclass(frozen=True)
class AuditRecorder:
    """Writes audit events for one model, run and stage, each in its own short transaction."""

    engine: Engine
    model_id: str | None = None
    run_id: str | None = None
    stage: str | None = None

    def record(
        self, action: str, *, actor_type: str = "system", actor: str = "factory_core", detail: dict | None = None
    ) -> None:
        """Append one event bound to this model, run and stage."""
        with Session(self.engine) as session:
            append_event(
                session,
                actor_type=actor_type,
                actor=actor,
                action=action,
                model_id=self.model_id,
                run_id=self.run_id,
                stage=self.stage,
                detail=detail,
            )

    def llm_call(self, actor: str, trace: dict[str, Any]) -> None:
        """Record one LLM call of an agent with its trace fields."""
        self.record("llm_call", actor_type="agent", actor=actor, detail=trace)

    def service_call(self, detail: dict[str, Any]) -> None:
        """Record one call to redev_engine or validation_lab."""
        self.record("service_call", actor=detail.get("service", "factory_core"), detail=detail)

    def tool_call(self, tool: str, detail: dict[str, Any]) -> None:
        """Record one run of a deterministic check such as the evidence verifier."""
        self.record("tool_call", actor=tool, detail=detail)
