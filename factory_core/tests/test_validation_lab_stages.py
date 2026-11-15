"""The validate and monitor stages: requests built from the estate, scores, features and the trigger."""

import dataclasses
import json

import httpx
from fastapi.testclient import TestClient

from app.api_schemas import InputVariable, InventoryRecord
from app.main import create_app
from app.schemas import ManifestData
from app.validation_lab_stages import feature_columns
from tests.conftest import HERO_FOLDER, decide, live_settings, load_example, pipeline_provider

STAGE_ORDER = ["discover", "document", "redevelop", "validate", "monitor"]


def recording_services(seen: dict[str, dict]) -> httpx.MockTransport:
    """Fake redev_engine and validation_lab that answer with the contract examples and keep each request."""
    answers = {
        "/redevelop": load_example("redevelop_result.M001.json"),
        "/validate": load_example("validation_result.M001.json"),
        "/report": {
            "model_id": "M001",
            "html_path": "artifacts/M001/validation/validation_report.html",
            "docx_path": None,
            "error": None,
        },
        "/monitor/simulate": {
            "model_id": "M001",
            "simulated": True,
            "batches_dir": "artifacts/M001/monitoring/batches",
            "batches": [],
            "error": None,
        },
        "/monitor/run": load_example("monitoring_result.M001.json"),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        """Keep the request body and answer from the examples."""
        seen[request.url.path] = json.loads(request.content)
        return httpx.Response(200, json=answers[request.url.path])

    return httpx.MockTransport(handler)


def run_through(client: TestClient, stages: list[str]) -> str:
    """Start a run and approve each requested stage with independent reviewers."""
    run_id = client.post("/api/models/M001/runs", json={"stages": stages}).json()["run_id"]
    for stage in stages:
        reviewer = "validator_b" if stage == "validate" else "developer_a"
        assert decide(client, run_id, stage, reviewer).status_code == 200
    return run_id


def test_feature_columns_match_discovered_inputs_in_any_case() -> None:
    """Discovered inputs are mapped to header names; id, target and protected columns never are."""
    data = ManifestData(dev_path="d", oot_path="o", id_col="ID", target_col="default_flag", protected_cols=["SEX"])
    record = InventoryRecord.model_validate(load_example("inventory_record.M001.json"))
    record.input_variables = [InputVariable(name="pay_0"), InputVariable(name="SEX"), InputVariable(name="missing")]
    header = ["ID", "PAY_0", "LIMIT_BAL", "SEX", "default_flag"]
    assert feature_columns(header, record, data) == ["PAY_0"]
    record.input_variables = []
    assert feature_columns(header, record, data) == ["PAY_0", "LIMIT_BAL"]


def test_validate_and_monitor_requests_follow_the_contract(hero_estate) -> None:
    """Scores come from the rebuild after parity passed; paths are repository relative; monitoring follows."""
    seen: dict[str, dict] = {}
    settings = dataclasses.replace(live_settings(hero_estate), use_stubs=False)
    app = create_app(
        settings, llm_provider=pipeline_provider(), service_transport=recording_services(seen), background=False
    )
    with TestClient(app) as client:
        run_id = run_through(client, STAGE_ORDER)
        run = client.get(f"/api/runs/{run_id}").json()
        assert run["status"] == "COMPLETED"
        assert run["stages"][3]["summary"] == (
            "Overall rating AMBER. 1 findings (0 high, 1 medium, 0 low). 5 of 5 narrative numbers verified."
        )
        assert run["stages"][4]["summary"].endswith("Revalidation triggered: Score PSI above 0.25 in batch 2026_05.")
        assert client.get("/api/models/M001").json()["revalidation_required"] is True
    validate = seen["/validate"]
    assert validate["data"]["dev_path"] == f"{HERO_FOLDER}/data/dev.csv"
    assert validate["scores"]["dev_path"] == "artifacts/M001/redevelop/scored_dev.csv"
    assert validate["model_module_path"] == "artifacts/M001/redevelop/model.py"
    assert validate["feature_cols"] == ["PAY_0"] and validate["protected_cols"] == ["SEX", "AGE_BAND"]
    report = seen["/report"]
    assert report["parity_summary"]["max_abs_diff_pd"] == 3.1e-9
    assert report["narrative"]["unverified_numbers"] == []
    assert report["inventory_record"]["model_id"] == "M001"
    assert seen["/monitor/simulate"]["batch_size"] == 100
    assert seen["/monitor/run"]["reference"]["scores_path"] == "artifacts/M001/redevelop/scored_dev.csv"


def test_model_without_rebuild_is_validated_on_golden_scores(hero_estate) -> None:
    """When redevelopment was not run, validation uses the legacy golden files and no parity summary."""
    seen: dict[str, dict] = {}
    settings = dataclasses.replace(live_settings(hero_estate), use_stubs=False)
    app = create_app(
        settings, llm_provider=pipeline_provider(), service_transport=recording_services(seen), background=False
    )
    with TestClient(app) as client:
        run_through(client, ["discover", "validate"])
    assert seen["/validate"]["scores"]["oot_path"] == f"{HERO_FOLDER}/golden/scored_oot_legacy.csv"
    assert seen["/validate"]["model_module_path"] is None
    assert seen["/report"]["parity_summary"] is None


def test_failed_validation_is_shown_as_a_failed_stage(hero_estate) -> None:
    """A validation_lab result that is not COMPLETED fails the stage with its error."""
    failing = load_example("validation_result.M001.json") | {"status": "FAILED", "error": "target column missing"}

    def handler(request: httpx.Request) -> httpx.Response:
        """Answer /validate with a failed result."""
        return httpx.Response(200, json=failing)

    settings = dataclasses.replace(live_settings(hero_estate), use_stubs=False)
    app = create_app(
        settings, llm_provider=pipeline_provider(), service_transport=httpx.MockTransport(handler), background=False
    )
    with TestClient(app) as client:
        run_id = client.post("/api/models/M001/runs", json={"stages": ["discover", "validate"]}).json()["run_id"]
        decide(client, run_id, "discover", "developer_a")
        stage = client.get(f"/api/runs/{run_id}").json()["stages"][3]
    assert (stage["status"], stage["error"]) == (
        "FAILED",
        "validation_lab returned status FAILED: target column missing",
    )


def test_null_metrics_and_object_errors_from_validation_lab_are_accepted(hero_estate) -> None:
    """validation_lab may return null for a metric it cannot compute; that is shown, not a contract failure."""
    result = load_example("validation_result.M001.json")
    result["sections"]["discrimination"]["oot"]["auc"] = None
    result["sections"]["fairness"]["by_attribute"][0]["groups"][0]["approval_rate_bad_customers"] = None
    monitoring = load_example("monitoring_result.M001.json")
    monitoring["batches"][0]["max_csi"] = {"feature": None, "csi": None}
    answers = {
        "/validate": result,
        "/report": {
            "model_id": "M001",
            "html_path": "artifacts/M001/validation/validation_report.html",
            "docx_path": None,
            "error": None,
        },
        "/monitor/simulate": {
            "model_id": "M001",
            "simulated": True,
            "batches_dir": "artifacts/M001/monitoring/batches",
            "batches": [],
            "error": None,
        },
        "/monitor/run": monitoring,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        """Answer like validation_lab with some metrics left null."""
        return httpx.Response(200, json=answers[request.url.path])

    settings = dataclasses.replace(live_settings(hero_estate), use_stubs=False)
    app = create_app(
        settings, llm_provider=pipeline_provider(), service_transport=httpx.MockTransport(handler), background=False
    )
    with TestClient(app) as client:
        run_id = run_through(client, ["discover", "validate", "monitor"])
        assert client.get(f"/api/runs/{run_id}").json()["status"] == "COMPLETED"
        view = client.get("/api/models/M001/validation").json()
    assert view["result"]["sections"]["discrimination"]["oot"]["auc"] is None


def test_object_error_from_validation_lab_becomes_a_readable_stage_error(hero_estate) -> None:
    """An {"code", "message"} error object is shown by its message."""
    failing = load_example("validation_result.M001.json") | {
        "error": {"code": "DATA_ERROR", "message": "target column missing"}
    }

    def handler(request: httpx.Request) -> httpx.Response:
        """Answer /validate with an error object."""
        return httpx.Response(200, json=failing)

    settings = dataclasses.replace(live_settings(hero_estate), use_stubs=False)
    app = create_app(
        settings, llm_provider=pipeline_provider(), service_transport=httpx.MockTransport(handler), background=False
    )
    with TestClient(app) as client:
        run_id = client.post("/api/models/M001/runs", json={"stages": ["discover", "validate"]}).json()["run_id"]
        decide(client, run_id, "discover", "developer_a")
        stage = client.get(f"/api/runs/{run_id}").json()["stages"][3]
    assert stage["error"] == "validation_lab returned status COMPLETED: target column missing"
