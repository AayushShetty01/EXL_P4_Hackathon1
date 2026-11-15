"""The LangGraph wiring: node order, routing, skips without gates, and the end of a run."""

import json

from fastapi.testclient import TestClient

from app.main import create_app
from app.pipeline_graph import DONE, next_node
from tests.conftest import HERO_FOLDER, decide, live_settings, pipeline_provider, stage_statuses


def test_nodes_follow_the_five_stages_with_a_gate_after_each(pipeline_client: TestClient) -> None:
    """discover, gate, document, gate, redevelop, gate, validate, gate, monitor, gate, done."""
    graph = pipeline_client.app.state.runner.graph.get_graph()
    nodes = set(graph.nodes)
    for stage in ("discover", "document", "redevelop", "validate", "monitor"):
        assert {stage, f"gate_{stage}"} <= nodes
    assert DONE in nodes
    assert next_node("discover") == "document"
    assert next_node("monitor") == DONE


def test_skipped_stages_need_no_gate(hero_estate) -> None:
    """A model that is not redeveloped and has no data goes from document straight to done."""
    manifest_path = hero_estate.repository_root / HERO_FOLDER / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) | {"redevelop": False, "data": None, "golden": None}
    manifest_path.write_text(json.dumps(manifest))
    with TestClient(
        create_app(live_settings(hero_estate), llm_provider=pipeline_provider(), background=False)
    ) as client:
        run_id = client.post("/api/models/M001/runs", json={}).json()["run_id"]
        decide(client, run_id, "discover", "owner_a", role="owner")
        decide(client, run_id, "document", "owner_a", role="owner")
        run = client.get(f"/api/runs/{run_id}").json()
    assert run["status"] == "COMPLETED"
    skipped = {stage["stage"]: stage["skip_reason"] for stage in run["stages"] if stage["status"] == "SKIPPED"}
    assert skipped == {
        "redevelop": "The manifest marks this model as not to be redeveloped.",
        "validate": "The model has no data, so it cannot be validated.",
        "monitor": "The model has no data, so it cannot be monitored.",
    }


def test_completed_run_writes_the_compliance_matrix(pipeline_client: TestClient) -> None:
    """The done node marks the run COMPLETED and saves artifacts/M001/compliance/ss123_matrix.json."""
    run_id = pipeline_client.post("/api/models/M001/runs", json={"stages": ["discover"]}).json()["run_id"]
    decide(pipeline_client, run_id, "discover", "owner_a", role="owner")
    run = pipeline_client.get(f"/api/runs/{run_id}").json()
    assert (run["status"], run["current_stage"]) == ("COMPLETED", None)
    content = pipeline_client.get("/api/files", params={"path": "artifacts/M001/compliance/ss123_matrix.json"}).json()
    assert json.loads(content["content"])["model_id"] == "M001"


def test_failed_stage_ends_the_graph(pipeline_client: TestClient) -> None:
    """After a failure no later stage starts."""
    run_id = pipeline_client.post("/api/models/M001/runs", json={"stages": ["document", "redevelop"]}).json()["run_id"]
    assert stage_statuses(pipeline_client, run_id) == {
        "discover": "SKIPPED",
        "document": "FAILED",
        "redevelop": "PENDING",
        "validate": "SKIPPED",
        "monitor": "SKIPPED",
    }
