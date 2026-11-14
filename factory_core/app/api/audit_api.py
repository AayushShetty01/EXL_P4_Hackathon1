"""Audit endpoint: the events of the hash chained audit trail and whether the chain is intact."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.api_schemas import Audit, AuditEvent
from app.audit_trail import list_events, verify_chain
from app.database import get_session

router = APIRouter(prefix="/api", tags=["audit"])
SessionDependency = Annotated[Session, Depends(get_session)]


@router.get("/audit", response_model=Audit)
def read_audit(
    session: SessionDependency,
    model_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 200,
) -> Audit:
    """The newest events, oldest first. chain_valid always checks the whole chain."""
    events = [AuditEvent.model_validate(row.model_dump()) for row in list_events(session, model_id, limit)]
    return Audit(chain_valid=verify_chain(session), events=events)
