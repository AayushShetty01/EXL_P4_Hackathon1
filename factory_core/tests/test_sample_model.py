"""The built-in sample model registered from the contract examples."""

from sqlmodel import Session, select

from app.config import Settings
from app.database import ModelRow, StageOutputRow, latest_stage_output, load_run
from app.sample_model import SAMPLE_NAME_SUFFIX, register_sample_model, remove_sample_model
from tests.conftest import load_example


def test_sample_is_labelled_as_a_sample(settings: Settings, session: Session) -> None:
    """The sample keeps the example values but its name says it is a sample."""
    model_id = register_sample_model(session, settings)
    record = latest_stage_output(session, model_id, "inventory_record")
    assert record["model_name"] == "Credit Card PD Scorecard" + SAMPLE_NAME_SUFFIX
    assert session.get(ModelRow, model_id).source == "sample"


def test_sample_holds_the_example_run_and_outputs(settings: Settings, session: Session) -> None:
    """The example run and every example stage output are stored unchanged."""
    model_id = register_sample_model(session, settings)
    assert load_run(session, "run_M001_001").model_dump(mode="json") == load_example("run.json")
    assert latest_stage_output(session, model_id, "documentation") == load_example("documentation.M001.json")
    assert latest_stage_output(session, model_id, "monitoring") == load_example("monitoring_result.M001.json")


def test_remove_sample_model_deletes_everything_stored_for_it(settings: Settings, session: Session) -> None:
    """After removal no model, run or output of the sample is left."""
    register_sample_model(session, settings)
    remove_sample_model(session)
    assert session.exec(select(ModelRow)).first() is None
    assert session.exec(select(StageOutputRow)).first() is None
    assert load_run(session, "run_M001_001") is None
