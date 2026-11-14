"""Stage result endpoints return the contract shapes, or NOT_AVAILABLE before a stage has run."""

import pytest
from fastapi.testclient import TestClient

from app.stage_result_schemas import Compliance
from tests.conftest import load_example

RESULT_EXAMPLES = {
    "documentation": "documentation.M001.json",
    "redevelopment": "redevelop_result.M001.json",
    "validation": "validation_view.M001.json",
    "monitoring": "monitoring_result.M001.json",
}


@pytest.mark.parametrize("endpoint", sorted(RESULT_EXAMPLES))
def test_sample_results_match_the_contract_examples(client: TestClient, endpoint: str) -> None:
    """Every result endpoint of the sample returns its contract example exactly."""
    response = client.get(f"/api/models/M001/{endpoint}")
    assert response.status_code == 200
    assert response.json() == load_example(RESULT_EXAMPLES[endpoint])


@pytest.mark.parametrize("endpoint", sorted(RESULT_EXAMPLES))
def test_results_are_not_available_before_the_stage_runs(estate_client: TestClient, endpoint: str) -> None:
    """A registered model with no stage output gives 404 NOT_AVAILABLE."""
    response = estate_client.get(f"/api/models/M001/{endpoint}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_AVAILABLE"


def test_results_of_an_unknown_model_are_404(client: TestClient) -> None:
    """An unregistered model gives MODEL_NOT_FOUND, not NOT_AVAILABLE."""
    assert client.get("/api/models/M999/documentation").json()["error"]["code"] == "MODEL_NOT_FOUND"


def test_compliance_is_computed_for_every_registered_model(estate_client: TestClient) -> None:
    """Compliance is never NOT_AVAILABLE: before any run it shows what is missing."""
    body = estate_client.get("/api/models/M001/compliance").json()
    Compliance.model_validate(body)
    assert [principle["principle"] for principle in body["principles"]] == ["P1", "P2", "P3", "P4", "P5"]
    assert body["coverage"]["met"] == 0
