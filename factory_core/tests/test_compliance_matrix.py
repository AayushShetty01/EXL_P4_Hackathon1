"""The SS1/23 compliance matrix: five principle titles, checks on stored outputs, honest statuses."""

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.agents.compliance_matrix import DISCLAIMER, EXPECTATIONS, PRINCIPLE_TITLES, build_compliance
from app.database import ModelRow
from tests.conftest import decide

STAGES = [
    ("discover", "owner_a"),
    ("document", "owner_a"),
    ("redevelop", "developer_a"),
    ("validate", "validator_b"),
    ("monitor", "owner_a"),
]


def statuses(body: dict) -> dict[str, str]:
    """Status of every item by id."""
    return {item["id"]: item["status"] for principle in body["principles"] for item in principle["items"]}


def test_matrix_uses_only_the_five_principle_titles() -> None:
    """Principles P1 to P5 carry the official titles and no sub principle numbers."""
    assert PRINCIPLE_TITLES["P4"] == "Independent model validation"
    assert {principle for principle, _, _, _ in EXPECTATIONS} == set(PRINCIPLE_TITLES)
    assert len(EXPECTATIONS) == 20


def test_registered_model_without_runs_meets_nothing(estate_client: TestClient) -> None:
    """Before any stage has run, nothing is MET and organisational controls are OUT_OF_SCOPE."""
    body = estate_client.get("/api/models/M001/compliance").json()
    assert body["disclaimer"] == DISCLAIMER
    assert body["coverage"] == {"met": 0, "partial": 0, "not_met": 17, "out_of_scope": 3}


def test_full_run_meets_most_expectations(pipeline_client: TestClient) -> None:
    """After a full run with independent approvals, the evidence based items are MET."""
    run_id = pipeline_client.post("/api/models/M001/runs", json={}).json()["run_id"]
    for stage, reviewer in STAGES:
        decide(pipeline_client, run_id, stage, reviewer)
    found = statuses(pipeline_client.get("/api/models/M001/compliance").json())
    for item in (
        "P1_inventory",
        "P1_tiering",
        "P2_gate_approvals",
        "P3_testing",
        "P4_independent_approval",
        "P4_monitoring",
    ):
        assert found[item] == "MET", item
    assert found["P2_owner"] == "PARTIAL"
    assert found["P5_findings"] == "PARTIAL"
    assert found["P2_board"] == "OUT_OF_SCOPE"


def test_sample_model_matrix_is_computed_from_its_example_outputs(client: TestClient) -> None:
    """The sample has no audit trail, so gate approvals are NOT_MET even though its outputs exist."""
    with Session(client.app.state.engine) as session:
        compliance = build_compliance(session, session.get(ModelRow, "M001"))
    found = {item.id: item.status for principle in compliance.principles for item in principle.items}
    assert found["P2_gate_approvals"] == "NOT_MET"
    assert found["P3_testing"] == "MET"
