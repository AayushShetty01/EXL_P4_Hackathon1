"""Run endpoints: start a run, read a run, record a gate decision.

Runs execute in the background; the dashboard polls GET /api/runs/{run_id}. Approving the validate
gate with the reviewer who approved the redevelop gate answers 409 INDEPENDENCE_VIOLATION.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session

from app.api.api_errors import api_error
from app.api_schemas import GateDecisionRequest, Run, RunCreated, RunCreateRequest
from app.database import get_session, load_run
from app.gate_decisions import GateError
from app.pipeline_runner import PipelineRunner
from app.schemas import StageName

router = APIRouter(prefix="/api", tags=["runs"])
SessionDependency = Annotated[Session, Depends(get_session)]


def request_runner(request: Request) -> PipelineRunner:
    """FastAPI dependency that returns the app's pipeline runner."""
    return request.app.state.runner


RunnerDependency = Annotated[PipelineRunner, Depends(request_runner)]


def get_run(session: Session, run_id: str) -> Run:
    """Return a run or raise 404 RUN_NOT_FOUND."""
    run = load_run(session, run_id)
    if run is None:
        raise api_error(404, "RUN_NOT_FOUND", f"Run {run_id} does not exist")
    return run


@router.post("/models/{model_id}/runs")
def start_run(model_id: str, request: RunCreateRequest, runner: RunnerDependency) -> RunCreated:
    """Start a pipeline run for one model; it pauses at the gate after each stage."""
    try:
        return RunCreated(run_id=runner.start_run(model_id, request))
    except GateError as error:
        raise api_error(error.status_code, error.code, error.message) from error


@router.get("/runs/{run_id}")
def read_run(run_id: str, session: SessionDependency) -> Run:
    """The state of one run with every stage and gate."""
    return get_run(session, run_id)


@router.post("/runs/{run_id}/gates/{stage}/decision")
def decide_gate(
    run_id: str, stage: StageName, decision: GateDecisionRequest, session: SessionDependency, runner: RunnerDependency
) -> Run:
    """Record a human approve or reject decision at a stage gate and return the updated run."""
    try:
        runner.decide(run_id, stage, decision)
    except GateError as error:
        raise api_error(error.status_code, error.code, error.message) from error
    return get_run(session, run_id)
