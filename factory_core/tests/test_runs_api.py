"""Run endpoints: a full run through all five gates, rejections, the independence rule and errors."""

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.api_schemas import Run
from app.audit_trail import list_events, verify_chain
from app.main import create_app
from tests.conftest import decide, load_example, stage_statuses


def start(client: TestClient, **body) -> str:
    """Start a run on M001 and return its id."""
    response = client.post("/api/models/M001/runs", json=body)
    assert response.status_code == 200, response.text
    return response.json()["run_id"]


def test_sample_run_matches_the_contract_example(client: TestClient) -> None:
    """GET /api/runs/{run_id} for the sample returns the run example exactly."""
    assert client.get("/api/runs/run_M001_001").json() == load_example("run.json")


def test_unknown_run_is_404(client: TestClient) -> None:
    """A run id that does not exist gives 404 RUN_NOT_FOUND."""
    response = client.get("/api/runs/run_M999_001")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RUN_NOT_FOUND"


def test_full_run_pauses_at_every_gate_and_enforces_independence(pipeline_client: TestClient) -> None:
    """Each stage waits for a human; the redevelop approver cannot approve validation."""
    client = pipeline_client
    run_id = start(client)
    assert run_id == "run_M001_001"
    run = client.get(f"/api/runs/{run_id}").json()
    assert (run["status"], run["current_stage"]) == ("AWAITING_REVIEW", "discover")
    assert stage_statuses(client, run_id)["document"] == "PENDING"

    assert (
        decide(client, run_id, "discover", "model_owner", role="owner").json()["stages"][1]["status"]
        == "AWAITING_REVIEW"
    )
    assert decide(client, run_id, "document", "model_owner", role="owner").status_code == 200
    assert decide(client, run_id, "redevelop", "developer_a").status_code == 200
    assert stage_statuses(client, run_id)["validate"] == "AWAITING_REVIEW"

    blocked = decide(client, run_id, "validate", "Developer_A", role="validator")
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "INDEPENDENCE_VIOLATION"
    assert stage_statuses(client, run_id)["validate"] == "AWAITING_REVIEW"

    assert decide(client, run_id, "validate", "validator_b", role="validator").status_code == 200
    final = decide(client, run_id, "monitor", "model_owner", role="owner").json()
    Run.model_validate(final)
    run = client.get(f"/api/runs/{run_id}").json()
    assert run["status"] == "COMPLETED"
    assert {stage["status"] for stage in run["stages"]} == {"APPROVED"}
    assert all(stage["gate"]["review_seconds"] >= 0 for stage in run["stages"])


def test_completed_run_fills_every_result_endpoint(pipeline_client: TestClient) -> None:
    """After a full run every stamp has a contract shaped result, built from computed data."""
    client = pipeline_client
    run_id = start(client)
    for stage, reviewer in [
        ("discover", "o"),
        ("document", "o"),
        ("redevelop", "dev"),
        ("validate", "val"),
        ("monitor", "o"),
    ]:
        assert decide(client, run_id, stage, reviewer).status_code == 200
    record = client.get("/api/models/M001").json()
    assert record["tiering"]["tier"] == "Tier 1"
    assert record["revalidation_required"] is True
    documentation = client.get("/api/models/M001/documentation").json()
    assert documentation["groundedness"]["claims_verified"] == 10
    assert documentation["doc_drift"][0]["status"] == "VERIFIED"
    assert client.get("/api/models/M001/redevelopment").json()["status"] == "PARITY_PASSED"
    validation = client.get("/api/models/M001/validation").json()
    assert validation["number_grounding"] == {"numbers_in_narrative": 5, "numbers_verified": 5, "score": 1.0}
    assert client.get("/api/models/M001/monitoring").json()["revalidation_triggered"] is True
    compliance = client.get("/api/models/M001/compliance").json()
    assert compliance["coverage"]["out_of_scope"] == 3
    summary = client.get("/api/models").json()["models"][0]
    assert summary["pipeline_status"] == dict.fromkeys(
        ("discover", "document", "redevelop", "validate", "monitor"), "APPROVED"
    )
    assert summary["overall_rating"] == "AMBER"


def test_audit_trail_records_the_run_and_stays_valid(pipeline_client: TestClient) -> None:
    """Stage changes, agent calls, service calls, artifacts and decisions are all in a valid chain."""
    run_id = start(pipeline_client)
    decide(pipeline_client, run_id, "discover", "model_owner", role="owner")
    with Session(pipeline_client.app.state.engine) as session:
        actions = [event.action for event in list_events(session, "M001", limit=500)]
        assert verify_chain(session) is True
    for action in ("stage_started", "llm_call", "tool_call", "artifact_written", "stage_completed", "gate_decision"):
        assert action in actions
    assert pipeline_client.get("/api/audit").json()["chain_valid"] is True


def test_reject_stops_the_run(pipeline_client: TestClient) -> None:
    """A rejection marks the stage and the run REJECTED and nothing else runs."""
    run_id = start(pipeline_client)
    run = decide(pipeline_client, run_id, "discover", "model_owner", decision="reject", role="owner").json()
    assert (run["status"], run["stages"][0]["status"], run["stages"][1]["status"]) == (
        "REJECTED",
        "REJECTED",
        "PENDING",
    )
    assert run["stages"][0]["gate"]["comment"] == "reject by model_owner"


def test_auto_approve_runs_to_the_end_with_demo_reviewers(pipeline_client: TestClient) -> None:
    """A seeding run approves every gate with demo reviewers, marked automatic in the audit trail."""
    run_id = start(pipeline_client, auto_approve=True)
    run = pipeline_client.get(f"/api/runs/{run_id}").json()
    assert run["status"] == "COMPLETED"
    reviewers = {stage["stage"]: stage["gate"]["reviewer"] for stage in run["stages"]}
    assert reviewers["redevelop"] == "demo_developer" and reviewers["validate"] == "demo_validator"
    events = pipeline_client.get("/api/audit", params={"model_id": "M001", "limit": 1000}).json()["events"]
    decisions = [event for event in events if event["action"] == "gate_decision"]
    assert len(decisions) == 5 and all(event["detail"]["automatic"] for event in decisions)
    assert pipeline_client.get("/api/metrics/factory").json()["human_review_minutes_logged"] == 0


def test_only_requested_stages_run(pipeline_client: TestClient) -> None:
    """Stages not asked for are SKIPPED with a reason; the run completes after the last requested gate."""
    run_id = start(pipeline_client, stages=["discover"])
    run = pipeline_client.get(f"/api/runs/{run_id}").json()
    assert run["stages"][1] | {"status": "SKIPPED"} == run["stages"][1]
    assert run["stages"][1]["skip_reason"] == "Not requested in this run."
    decide(pipeline_client, run_id, "discover", "model_owner", role="owner")
    assert pipeline_client.get(f"/api/runs/{run_id}").json()["status"] == "COMPLETED"


def test_conflicting_requests_are_refused(pipeline_client: TestClient) -> None:
    """A second active run, a decision on a closed gate and a sample model run are all 409."""
    run_id = start(pipeline_client)
    assert pipeline_client.post("/api/models/M001/runs", json={}).json()["error"]["code"] == "RUN_ACTIVE"
    assert decide(pipeline_client, run_id, "monitor", "x").json()["error"]["code"] == "GATE_NOT_OPEN"
    assert pipeline_client.post("/api/models/M999/runs", json={}).json()["error"]["code"] == "MODEL_NOT_FOUND"


def test_sample_model_is_read_only(client: TestClient) -> None:
    """The sample model can be shown but not run or decided on."""
    assert client.post("/api/models/M001/runs", json={}).json()["error"]["code"] == "SAMPLE_MODEL"
    response = decide(client, "run_M001_001", "document", "reviewer")
    assert (response.status_code, response.json()["error"]["code"]) == (409, "SAMPLE_MODEL")


def test_replay_without_recordings_fails_the_stage_visibly(hero_estate) -> None:
    """With no key and no recorded replies, discovery fails with a clear message instead of hanging."""
    with TestClient(create_app(hero_estate, background=False)) as client:
        run_id = start(client)
        run = client.get(f"/api/runs/{run_id}").json()
    assert (run["status"], run["stages"][0]["status"]) == ("FAILED", "FAILED")
    assert "LLM_MODE=live" in run["stages"][0]["error"]


def test_gate_decision_checks_the_stage_name(pipeline_client: TestClient) -> None:
    """Only the five stage names are valid gates."""
    response = decide(pipeline_client, "run_M001_001", "deploy", "reviewer")
    assert (response.status_code, response.json()["error"]["code"]) == (422, "INVALID_REQUEST")
