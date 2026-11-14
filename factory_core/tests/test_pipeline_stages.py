"""The discover, document and redevelop stages: stored results, artifacts and honest failures."""

import dataclasses
import json

import httpx
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import decide, live_settings, load_example, pipeline_provider, stage_statuses


def artifact(client: TestClient, path: str) -> str:
    """Read a written artifact through the file API."""
    return client.get("/api/files", params={"path": path}).json()["content"]


def test_discover_stage_writes_the_inventory_record(pipeline_client: TestClient) -> None:
    """Stamp 1 is stored and written to artifacts/M001/discover/inventory_record.json."""
    run_id = pipeline_client.post("/api/models/M001/runs", json={}).json()["run_id"]
    record = json.loads(artifact(pipeline_client, "artifacts/M001/discover/inventory_record.json"))
    assert record["tiering"]["tier"] == "Tier 1"
    summary = pipeline_client.get(f"/api/runs/{run_id}").json()["stages"][0]["summary"]
    assert summary == "Inventory record created. Tier 1. 3 of 3 field evidence quotes verified. 5 open questions."


def test_document_stage_writes_json_markdown_and_drift(pipeline_client: TestClient) -> None:
    """Stamp 2 writes the three document artifacts and summarises claims and drift by code."""
    run_id = pipeline_client.post("/api/models/M001/runs", json={}).json()["run_id"]
    run = decide(pipeline_client, run_id, "discover", "model_owner", role="owner").json()
    assert run["stages"][1]["summary"] == (
        "10 sections, 10 claims, 10 verified. 1 differences against the old document, 1 verified."
    )
    assert "## Differences against the old document" in artifact(
        pipeline_client, "artifacts/M001/document/model_document.md"
    )
    drift = json.loads(artifact(pipeline_client, "artifacts/M001/document/doc_drift.json"))
    assert drift[0]["topic"] == "Decision cutoff"
    assert json.loads(artifact(pipeline_client, "artifacts/M001/document/model_document.json"))["model_id"] == "M001"


def test_document_stage_needs_an_inventory_record(pipeline_client: TestClient) -> None:
    """Documenting a model that was never discovered fails with a clear message."""
    run_id = pipeline_client.post("/api/models/M001/runs", json={"stages": ["document"]}).json()["run_id"]
    stage = pipeline_client.get(f"/api/runs/{run_id}").json()["stages"][1]
    assert (stage["status"], stage["error"]) == (
        "FAILED",
        "There is no inventory record for this model yet. Run the discover stage first.",
    )


def test_failed_parity_fails_the_stage_but_keeps_the_result_visible(hero_estate) -> None:
    """PARITY_FAILED from redev_engine fails the stage; the result is still served to the dashboard."""
    failed = load_example("redevelop_result.M001.json") | {
        "status": "PARITY_FAILED",
        "error": "L2 mismatch on 41 records",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        """Answer /redevelop with a failed parity result."""
        return httpx.Response(200, json=failed)

    settings = dataclasses.replace(live_settings(hero_estate), use_stubs=False)
    app = create_app(
        settings, llm_provider=pipeline_provider(), service_transport=httpx.MockTransport(handler), background=False
    )
    with TestClient(app) as client:
        run_id = client.post("/api/models/M001/runs", json={"stages": ["discover", "redevelop"]}).json()["run_id"]
        decide(client, run_id, "discover", "model_owner", role="owner")
        stage = client.get(f"/api/runs/{run_id}").json()["stages"][2]
        assert stage["status"] == "FAILED"
        assert stage["error"].startswith("Redevelopment status PARITY_FAILED")
        assert stage["error"].endswith("L2 mismatch on 41 records")
        assert client.get("/api/models/M001/redevelopment").json()["status"] == "PARITY_FAILED"
        assert stage_statuses(client, run_id)["validate"] == "SKIPPED"


def test_unreachable_service_fails_the_stage_clearly(hero_estate) -> None:
    """With USE_STUBS=false and redev_engine down, the stage error says what to do."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Refuse every connection."""
        raise httpx.ConnectError("Connection refused", request=request)

    settings = dataclasses.replace(live_settings(hero_estate), use_stubs=False)
    app = create_app(
        settings, llm_provider=pipeline_provider(), service_transport=httpx.MockTransport(handler), background=False
    )
    with TestClient(app) as client:
        run_id = client.post("/api/models/M001/runs", json={"stages": ["discover", "redevelop"]}).json()["run_id"]
        decide(client, run_id, "discover", "model_owner", role="owner")
        error = client.get(f"/api/runs/{run_id}").json()["stages"][2]["error"]
    assert error.startswith("redev_engine: not reachable") and "USE_STUBS=true" in error


def redev_engine_llm_calls(client: TestClient) -> int:
    """Number of llm_call events recorded for redev_engine."""
    events = client.get("/api/audit", params={"model_id": "M001", "limit": 1000}).json()["events"]
    return sum(event["action"] == "llm_call" and event["actor"] == "redev_engine" for event in events)


def test_redev_engine_calls_are_audited_only_when_they_happened(hero_estate, pipeline_client: TestClient) -> None:
    """Stub answers add no LLM call events; a real redev_engine reply adds one per trace entry."""
    run_id = pipeline_client.post("/api/models/M001/runs", json={"stages": ["discover", "redevelop"]}).json()["run_id"]
    decide(pipeline_client, run_id, "discover", "model_owner", role="owner")
    assert redev_engine_llm_calls(pipeline_client) == 0
    decide(pipeline_client, run_id, "redevelop", "developer_a")

    def handler(request: httpx.Request) -> httpx.Response:
        """Answer /redevelop like the real service."""
        return httpx.Response(200, json=load_example("redevelop_result.M001.json"))

    settings = dataclasses.replace(live_settings(hero_estate), use_stubs=False)
    app = create_app(
        settings, llm_provider=pipeline_provider(), service_transport=httpx.MockTransport(handler), background=False
    )
    with TestClient(app) as client:
        second = client.post("/api/models/M001/runs", json={"stages": ["redevelop"]}).json()["run_id"]
        assert client.get(f"/api/runs/{second}").json()["stages"][2]["status"] == "AWAITING_REVIEW"
        assert redev_engine_llm_calls(client) == len(load_example("redevelop_result.M001.json")["llm_trace"])
