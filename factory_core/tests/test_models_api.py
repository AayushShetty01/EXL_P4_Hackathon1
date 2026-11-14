"""Model inventory endpoints: list, scan, one record and factory metrics."""

from fastapi.testclient import TestClient

from app.api_schemas import FactoryMetrics, InventoryRecord, ModelList
from tests.conftest import load_example

ALL_PENDING = {stage: "PENDING" for stage in ("discover", "document", "redevelop", "validate", "monitor")}


def test_models_list_matches_the_contract_example_for_the_sample(client: TestClient) -> None:
    """The sample row equals the models_list example apart from the sample label."""
    body = client.get("/api/models").json()
    ModelList.model_validate(body)
    expected = load_example("models_list.json")["models"][0]
    expected["model_name"] += " (sample from contract examples)"
    expected["overall_rating"] = load_example("validation_result.M001.json")["overall_rating"]
    assert body["models"] == [expected]


def test_scan_registers_estate_models_and_removes_the_sample(client: TestClient, hero_estate) -> None:
    """Scanning after the estate arrives registers M001 from the estate in place of the sample."""
    response = client.post("/api/estate/scan")
    assert response.json() == {"models_found": ["M001"]}
    [model] = client.get("/api/models").json()["models"]
    assert model["model_name"] == "Credit Card PD Scorecard"
    assert model["pipeline_status"] == ALL_PENDING
    assert model["active_run_id"] is None


def test_scan_of_an_empty_estate_finds_nothing(client: TestClient) -> None:
    """With no model folders the scan reports no models found."""
    assert client.post("/api/estate/scan").json() == {"models_found": []}


def test_scan_reports_a_broken_manifest(client: TestClient, hero_estate) -> None:
    """A broken manifest gives 422 INVALID_MANIFEST instead of a partial registration."""
    (hero_estate.repository_root / "model_estate/M001_cc_pd_scorecard_sas/manifest.json").write_text("[]")
    response = client.post("/api/estate/scan")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_MANIFEST"


def test_record_before_discovery_has_register_facts_and_null_discovery_fields(estate_client: TestClient) -> None:
    """Before stamp 1 the record shows register and file facts; discovered fields stay null."""
    record = estate_client.get("/api/models/M001").json()
    InventoryRecord.model_validate(record)
    assert record["model_owner"] == "Head of Cards Credit Risk"
    assert record["exposure_gbp_m"] == 1850
    assert record["customer_facing"] is True
    assert len(record["source_files"]) == 4
    assert record["purpose"] is None and record["algorithm"] is None and record["tiering"] is None
    assert record["pipeline_status"] == ALL_PENDING


def test_sample_record_matches_the_inventory_example(client: TestClient) -> None:
    """The stored sample record equals the inventory example apart from the sample label."""
    expected = load_example("inventory_record.M001.json")
    expected["model_name"] += " (sample from contract examples)"
    assert client.get("/api/models/M001").json() == expected


def test_unknown_model_is_404(client: TestClient) -> None:
    """A model id that is not registered gives 404 MODEL_NOT_FOUND."""
    response = client.get("/api/models/M999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "MODEL_NOT_FOUND"


def test_factory_metrics_are_computed_from_the_database(client: TestClient) -> None:
    """Metrics for the sample come from its stored records, run and gates."""
    metrics = client.get("/api/metrics/factory").json()
    FactoryMetrics.model_validate(metrics)
    assert metrics["models_total"] == 1
    assert metrics["by_language"] == {"SAS": 1, "R": 0, "Python": 0}
    assert metrics["avg_groundedness"] == load_example("documentation.M001.json")["groundedness"]["score"]
    assert metrics["open_findings"] == {"HIGH": 0, "MEDIUM": 1, "LOW": 0}
    assert metrics["human_review_minutes_logged"] == round(89 / 60, 1)
    assert metrics["manual_baseline_weeks_per_validation"] == [8, 12]


def test_factory_metrics_before_any_run(estate_client: TestClient) -> None:
    """With no runs and no outputs the averages are null, never invented."""
    metrics = estate_client.get("/api/metrics/factory").json()
    assert metrics["avg_groundedness"] is None
    assert metrics["avg_agent_minutes_per_model"] is None
    assert metrics["docs_generated"] == 0
