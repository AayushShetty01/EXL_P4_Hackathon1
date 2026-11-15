"""Calls to redev_engine and validation_lab: stub mode, success, and every kind of failure."""

import dataclasses
import json

import httpx
import pytest

from app.config import Settings
from app.monitoring_schemas import MonitorRunRequest, MonitorSimulateRequest
from app.redev_engine_schemas import RedevelopRequest
from app.service_clients import ServiceCallError, ServiceClients, replace_identifiers
from app.stage_result_schemas import ReportRequest
from app.validation_lab_schemas import ValidateRequest
from tests.conftest import load_example

REDEVELOP_REQUEST = RedevelopRequest(
    run_id="run_M002_004", model_id="M002", estate_path="model_estate/M002_loan_pd_glm_r"
)


def live_clients(settings: Settings, handler) -> ServiceClients:
    """Clients in live mode whose HTTP calls go to a test handler."""
    return ServiceClients(dataclasses.replace(settings, use_stubs=False), transport=httpx.MockTransport(handler))


def test_replace_identifiers_updates_ids_and_artifact_paths() -> None:
    """model_id, run_id and artifacts/M001/ paths take the real values; other text is untouched."""
    replaced = replace_identifiers(
        {"model_id": "M001", "run_id": "run_M001_001", "files": [{"path": "artifacts/M001/x.py"}], "note": "M001"},
        "M002",
        "run_M002_004",
    )
    assert replaced == {
        "model_id": "M002",
        "run_id": "run_M002_004",
        "files": [{"path": "artifacts/M002/x.py"}],
        "note": "M001",
    }


def test_stub_redevelop_returns_the_example_for_this_model(settings: Settings) -> None:
    """In stub mode /redevelop answers with the contract example, carrying this model and run."""
    result = ServiceClients(settings).redevelop(REDEVELOP_REQUEST)
    assert (result.model_id, result.run_id, result.status) == ("M002", "run_M002_004", "PARITY_PASSED")
    assert result.generated_files[0].path == "artifacts/M002/redevelop/model.py"


def test_stub_validation_lab_calls_return_contract_shapes(settings: Settings) -> None:
    """Every validation_lab call has a stub answer in contract shape."""
    clients = ServiceClients(settings)
    validate = ValidateRequest.model_validate(load_example("validate_request.json") | {"model_id": "M003"})
    assert clients.validate(validate).model_id == "M003"
    report = clients.render_report(ReportRequest.model_validate(load_example("report_request.json")))
    assert report.html_path == "artifacts/M001/validation/validation_report.html"
    simulated = clients.simulate_monitoring(
        MonitorSimulateRequest.model_validate(load_example("monitor_simulate_request.json"))
    )
    assert simulated.simulated is True
    monitoring = clients.run_monitoring(MonitorRunRequest.model_validate(load_example("monitor_run_request.json")))
    assert monitoring.revalidation_triggered is True


def test_live_call_sends_the_request_and_parses_the_reply(settings: Settings) -> None:
    """A live call posts the request JSON and returns the parsed contract reply."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        """Record the request and answer with the redevelop example."""
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=load_example("redevelop_result.M001.json"))

    result = live_clients(settings, handler).redevelop(REDEVELOP_REQUEST)
    assert seen["url"] == "http://redev-engine.test/redevelop"
    assert seen["body"]["model_id"] == "M002"
    assert result.status == "PARITY_PASSED"


def test_unreachable_service_gives_a_clear_stage_error(settings: Settings) -> None:
    """A refused connection names the service, its address and what to do."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Refuse the connection."""
        raise httpx.ConnectError("Connection refused", request=request)

    clients = live_clients(settings, handler)
    with pytest.raises(ServiceCallError) as raised:
        clients.redevelop(REDEVELOP_REQUEST)
    assert raised.value.code == "SERVICE_UNREACHABLE"
    assert str(raised.value).startswith("redev_engine: not reachable at http://redev-engine.test")
    assert "USE_STUBS=true" in str(raised.value)


def test_timeout_is_reported(settings: Settings) -> None:
    """A call that runs past the timeout is reported as SERVICE_TIMEOUT."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Never answer in time."""
        raise httpx.ReadTimeout("timed out", request=request)

    clients = live_clients(settings, handler)
    with pytest.raises(ServiceCallError) as raised:
        clients.redevelop(REDEVELOP_REQUEST)
    assert raised.value.code == "SERVICE_TIMEOUT"


def test_error_body_from_the_service_is_passed_on(settings: Settings) -> None:
    """The service's own error code and message reach the stage error."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Answer with a contract error body."""
        return httpx.Response(422, json={"error": {"code": "NO_GOLDEN", "message": "golden files missing"}})

    clients = live_clients(settings, handler)
    with pytest.raises(ServiceCallError) as raised:
        clients.redevelop(REDEVELOP_REQUEST)
    assert raised.value.code == "NO_GOLDEN"
    assert "golden files missing" in str(raised.value)


def test_reply_that_breaks_the_contract_is_refused(settings: Settings) -> None:
    """A reply missing contract fields is a CONTRACT_MISMATCH, never passed on."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Answer with a reply that misses contract fields."""
        return httpx.Response(200, json={"model_id": "M002"})

    clients = live_clients(settings, handler)
    with pytest.raises(ServiceCallError) as raised:
        clients.redevelop(REDEVELOP_REQUEST)
    assert raised.value.code == "CONTRACT_MISMATCH"


def test_every_call_is_reported_with_its_outcome(settings: Settings) -> None:
    """Stub calls, successful calls and failed calls are all reported for the audit trail."""
    reported: list[dict] = []
    ServiceClients(settings, on_call=reported.append).redevelop(REDEVELOP_REQUEST)

    def handler(request: httpx.Request) -> httpx.Response:
        """Refuse the connection."""
        raise httpx.ConnectError("Connection refused", request=request)

    failing = ServiceClients(
        dataclasses.replace(settings, use_stubs=False), transport=httpx.MockTransport(handler), on_call=reported.append
    )
    with pytest.raises(ServiceCallError):
        failing.redevelop(REDEVELOP_REQUEST)
    assert [(call["service"], call["stub"], call["outcome"]) for call in reported] == [
        ("redev_engine", True, "ok"),
        ("redev_engine", False, "SERVICE_UNREACHABLE"),
    ]
    assert all("duration_ms" in call for call in reported)
