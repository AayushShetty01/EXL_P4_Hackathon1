"""Stage result endpoints: documentation, redevelopment, validation, monitoring and compliance.

Each stage result answers 404 NOT_AVAILABLE until its stage has produced output for the model.
The compliance matrix is computed on every request from what is stored.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.agents.compliance_matrix import build_compliance
from app.api.api_errors import api_error
from app.api.models_api import get_model_row
from app.database import OutputKind, get_session, latest_stage_output
from app.monitoring_schemas import MonitoringResult
from app.redev_engine_schemas import RedevelopResult
from app.stage_result_schemas import Compliance, Documentation, ValidationView

router = APIRouter(prefix="/api/models/{model_id}", tags=["results"])
SessionDependency = Annotated[Session, Depends(get_session)]


def stage_result(session: Session, model_id: str, kind: OutputKind, description: str) -> dict[str, Any]:
    """Return the newest stored result of a kind, or raise 404 NOT_AVAILABLE."""
    get_model_row(session, model_id)
    payload = latest_stage_output(session, model_id, kind)
    if payload is None:
        raise api_error(404, "NOT_AVAILABLE", f"No {description} for model {model_id} yet")
    return payload


@router.get("/documentation")
def get_documentation(model_id: str, session: SessionDependency) -> Documentation:
    """Generated documentation with cited claims and the drift list (stamp 2)."""
    return Documentation.model_validate(stage_result(session, model_id, "documentation", "documentation"))


@router.get("/redevelopment")
def get_redevelopment(model_id: str, session: SessionDependency) -> RedevelopResult:
    """The redev_engine result exactly as returned (stamp 3)."""
    return RedevelopResult.model_validate(stage_result(session, model_id, "redevelopment", "redevelopment result"))


@router.get("/validation")
def get_validation(model_id: str, session: SessionDependency) -> ValidationView:
    """Validation numbers, narrative, number grounding and report paths (stamp 4)."""
    return ValidationView.model_validate(stage_result(session, model_id, "validation_view", "validation result"))


@router.get("/monitoring")
def get_monitoring(model_id: str, session: SessionDependency) -> MonitoringResult:
    """The validation_lab monitoring result exactly as returned (stamp 5)."""
    return MonitoringResult.model_validate(stage_result(session, model_id, "monitoring", "monitoring result"))


@router.get("/compliance")
def get_compliance(model_id: str, session: SessionDependency) -> Compliance:
    """The SS1/23 compliance matrix of a model, computed now from its stored outputs and the audit trail."""
    return build_compliance(session, get_model_row(session, model_id))
