"""Every contract example validates against its schema and survives a round trip unchanged."""

import pytest
from pydantic import BaseModel, ValidationError

from app.api_schemas import (
    Audit,
    FactoryMetrics,
    FileView,
    GateDecisionRequest,
    InventoryRecord,
    ModelList,
    Run,
    RunCreateRequest,
)
from app.monitoring_schemas import MonitoringResult, MonitorRunRequest, MonitorSimulateRequest
from app.redev_engine_schemas import RedevelopRequest, RedevelopResult
from app.schemas import STAGE_NAMES, EstateManifest
from app.stage_result_schemas import Compliance, Documentation, ReportRequest, ValidationView
from app.validation_lab_schemas import ValidateRequest, ValidationResult
from tests.conftest import EXAMPLES_DIR, load_example

SCHEMA_BY_EXAMPLE: dict[str, type[BaseModel]] = {
    "estate_manifest.M001.json": EstateManifest,
    "redevelop_request.json": RedevelopRequest,
    "redevelop_result.M001.json": RedevelopResult,
    "validate_request.json": ValidateRequest,
    "validation_result.M001.json": ValidationResult,
    "report_request.json": ReportRequest,
    "monitor_simulate_request.json": MonitorSimulateRequest,
    "monitor_run_request.json": MonitorRunRequest,
    "monitoring_result.M001.json": MonitoringResult,
    "models_list.json": ModelList,
    "inventory_record.M001.json": InventoryRecord,
    "run.json": Run,
    "gate_decision_request.json": GateDecisionRequest,
    "documentation.M001.json": Documentation,
    "validation_view.M001.json": ValidationView,
    "compliance.M001.json": Compliance,
    "audit.json": Audit,
    "factory_metrics.json": FactoryMetrics,
    "file_view.json": FileView,
}


def test_every_example_file_has_a_schema() -> None:
    """No example in contracts/examples/ is left untested."""
    assert set(SCHEMA_BY_EXAMPLE) == {path.name for path in EXAMPLES_DIR.glob("*.json")}


@pytest.mark.parametrize("file_name", sorted(SCHEMA_BY_EXAMPLE))
def test_example_round_trips_through_its_schema(file_name: str) -> None:
    """Validating and dumping an example gives back exactly the example."""
    example = load_example(file_name)
    assert SCHEMA_BY_EXAMPLE[file_name].model_validate(example).model_dump(mode="json") == example


def test_shapes_owned_by_factory_core_reject_unknown_fields() -> None:
    """An unknown field in a factory_core shape is an error, so the contract cannot drift silently."""
    request = load_example("gate_decision_request.json") | {"approved_by_agent": True}
    with pytest.raises(ValidationError):
        GateDecisionRequest.model_validate(request)


def test_shapes_owned_by_other_services_keep_contract_additions() -> None:
    """An optional field another service adds is kept and passed on to the dashboard."""
    result = load_example("redevelop_result.M001.json") | {"extra_note": "listed under Contract additions"}
    assert RedevelopResult.model_validate(result).model_dump()["extra_note"] == "listed under Contract additions"


def test_run_request_defaults_to_all_five_stages() -> None:
    """An empty run request asks for every stage without auto approval."""
    request = RunCreateRequest.model_validate({})
    assert request.stages == list(STAGE_NAMES)
    assert request.auto_approve is False


def test_gate_decision_must_be_approve_or_reject() -> None:
    """Only approve and reject are valid gate decisions."""
    with pytest.raises(ValidationError):
        GateDecisionRequest.model_validate(load_example("gate_decision_request.json") | {"decision": "maybe"})
