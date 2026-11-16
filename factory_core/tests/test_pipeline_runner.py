"""The pipeline runner: background runs, run ids, resuming after a restart, recovering stuck stages, replay."""

import dataclasses
from datetime import datetime

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.database import StageRunRow
from app.main import create_app
from app.pipeline_runner import INTERRUPTED
from scripts.seed_demo import seed
from tests.conftest import decide, live_settings, pipeline_provider, stage_statuses


def make_app(settings, background: bool = False):
    """An app on the test estate with the scripted LLM and stubbed services."""
    return create_app(live_settings(settings), llm_provider=pipeline_provider(), background=background)


def test_background_run_returns_at_once_and_pauses_at_the_gate(hero_estate) -> None:
    """POST answers immediately; the run then pauses at the first gate in its own thread."""
    with TestClient(make_app(hero_estate, background=True)) as client:
        run_id = client.post("/api/models/M001/runs", json={}).json()["run_id"]
        client.app.state.runner.wait(run_id)
        assert stage_statuses(client, run_id)["discover"] == "AWAITING_REVIEW"
        decide(client, run_id, "discover", "owner_a", role="owner")
        client.app.state.runner.wait(run_id)
        assert stage_statuses(client, run_id)["document"] == "AWAITING_REVIEW"


def test_run_ids_count_up_per_model(pipeline_client: TestClient) -> None:
    """The second run of a model gets the next number."""
    first = pipeline_client.post("/api/models/M001/runs", json={"stages": ["discover"]}).json()["run_id"]
    decide(pipeline_client, first, "discover", "owner_a", decision="reject", role="owner")
    second = pipeline_client.post("/api/models/M001/runs", json={"stages": ["discover"]}).json()["run_id"]
    assert (first, second) == ("run_M001_001", "run_M001_002")


def test_paused_run_resumes_after_a_restart(hero_estate) -> None:
    """A run paused at a gate continues from its checkpoint when the service has been restarted."""
    with TestClient(make_app(hero_estate)) as client:
        run_id = client.post("/api/models/M001/runs", json={}).json()["run_id"]
    with TestClient(make_app(hero_estate)) as restarted:
        assert stage_statuses(restarted, run_id)["discover"] == "AWAITING_REVIEW"
        decide(restarted, run_id, "discover", "owner_a", role="owner")
        assert stage_statuses(restarted, run_id)["document"] == "AWAITING_REVIEW"


def test_stage_left_running_by_a_crash_is_failed_at_startup(hero_estate) -> None:
    """A stage that was RUNNING when the service stopped is FAILED on the next start, not left hanging."""
    with TestClient(make_app(hero_estate)) as client:
        run_id = client.post("/api/models/M001/runs", json={}).json()["run_id"]
        decide(client, run_id, "discover", "owner_a", role="owner")
        with Session(client.app.state.engine) as session:
            row = session.exec(
                select(StageRunRow).where(StageRunRow.run_id == run_id, StageRunRow.stage == "document")
            ).one()
            row.status = "RUNNING"
            session.add(row)
            session.commit()
    with TestClient(make_app(hero_estate)) as restarted:
        run = restarted.get(f"/api/runs/{run_id}").json()
    assert (run["status"], run["stages"][1]["status"], run["stages"][1]["error"]) == ("FAILED", "FAILED", INTERRUPTED)


class NextYear(datetime):
    """The clock of the replay run: one year after the recording, so every timestamp differs."""

    @classmethod
    def now(cls, tz=None):
        """A fixed time one year later."""
        return datetime(2027, 11, 15, 9, 30, tzinfo=tz)


def test_a_recorded_run_replays_on_a_fresh_database_later(hero_estate, tmp_path, monkeypatch) -> None:
    """Record one full run, then repeat it from the cache alone: new database, later clock, no provider, no key."""
    assert seed(live_settings(hero_estate), context_options={"llm_provider": pipeline_provider()}) == 0
    monkeypatch.setattr("app.database.datetime", NextYear)
    replay = dataclasses.replace(
        hero_estate,
        llm_mode="replay",
        llm_api_key="",
        llm_model="",
        database_path=tmp_path / "replay.db",
        checkpoints_path=tmp_path / "replay_checkpoints.db",
    )
    assert seed(replay) == 0
