"""Stage lifecycle: skips, success, failure, and never running a finished stage twice."""

import pytest
from sqlalchemy import Engine
from sqlmodel import Session

from app.config import Settings
from app.database import ModelRow, RunRow, StageRunRow, load_run
from app.estate_scanner import register_estate
from app.llm_client import LLMReplayMissError
from app.pipeline_context import PipelineContext, StageError, execute_stage, skip_reason, stage_error_message
from app.schemas import STAGE_NAMES


@pytest.fixture
def run_id(hero_estate: Settings, engine: Engine) -> str:
    """M001 registered with one run whose stages are all PENDING."""
    with Session(engine) as session:
        register_estate(session, hero_estate)
        session.add(RunRow(run_id="run_M001_001", model_id="M001", status="RUNNING", started_at="2026-11-15T10:00:00Z"))
        for position, stage in enumerate(STAGE_NAMES):
            session.add(StageRunRow(run_id="run_M001_001", stage=stage, position=position))
        session.commit()
    return "run_M001_001"


def test_skip_reasons_follow_the_manifest() -> None:
    """No redevelopment when the manifest says so; no validation or monitoring without data."""
    python_model = ModelRow(
        model_id="M003", source="estate", folder="f", language="Python", created_at="", updated_at=""
    )
    python_model.registration = {"manifest": {"redevelop": False, "data": {"dev_path": "d"}}}
    assert "already in Python" in skip_reason("redevelop", python_model)
    assert skip_reason("validate", python_model) is None
    pricing_model = ModelRow(model_id="M004", source="estate", folder="f", language="SAS", created_at="", updated_at="")
    pricing_model.registration = {"manifest": {"redevelop": False, "data": None}}
    assert skip_reason("redevelop", pricing_model) == "The manifest marks this model as not to be redeveloped."
    assert skip_reason("monitor", pricing_model) == "The model has no data, so it cannot be monitored."


def test_successful_stage_awaits_review_with_summary_and_duration(hero_estate, engine, run_id) -> None:
    """A stage that finishes waits for review with its summary; the run waits too."""
    context = PipelineContext(hero_estate, engine)
    assert execute_stage(context, run_id, "discover", lambda work: "Done by code.") == "AWAITING_REVIEW"
    with Session(engine) as session:
        run = load_run(session, run_id)
    stage = run.stages[0]
    assert (run.status, run.current_stage, stage.summary) == ("AWAITING_REVIEW", "discover", "Done by code.")
    assert stage.duration_seconds is not None
    assert stage.started_at
    assert stage.finished_at


def test_failing_stage_fails_the_run_with_its_message(hero_estate, engine, run_id) -> None:
    """Any error ends the stage and the run as FAILED with a readable message."""

    def broken(work):
        """Fail like a replay run without recordings."""
        raise LLMReplayMissError("LLM step discover: no recorded reply")

    assert execute_stage(PipelineContext(hero_estate, engine), run_id, "discover", broken) == "FAILED"
    with Session(engine) as session:
        run = load_run(session, run_id)
    assert (run.status, run.stages[0].error) == ("FAILED", "LLM step discover: no recorded reply")


def test_finished_stage_is_never_run_again(hero_estate, engine, run_id) -> None:
    """Executing a stage that is no longer PENDING returns its status without doing the work."""
    context = PipelineContext(hero_estate, engine)
    execute_stage(context, run_id, "discover", lambda work: "first")
    assert execute_stage(context, run_id, "discover", lambda work: pytest.fail("ran twice")) == "AWAITING_REVIEW"


def test_unexpected_errors_name_their_type() -> None:
    """Known errors keep their message; other errors are prefixed with their type."""
    assert stage_error_message(StageError("No scores.")) == "No scores."
    assert stage_error_message(KeyError("pd")) == "KeyError: 'pd'"
