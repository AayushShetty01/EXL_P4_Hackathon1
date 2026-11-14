"""Calls to redev_engine and validation_lab, with a stub mode for working without them.

USE_STUBS=true returns the contract examples with model_id and run_id replaced. Otherwise each call
goes over HTTP with a 600 second timeout, and every failure becomes a ServiceCallError whose
message is ready to show as the stage error.
"""

import json
import time
from collections.abc import Callable
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.monitoring_schemas import (
    MonitoringResult,
    MonitorRunRequest,
    MonitorSimulateRequest,
    MonitorSimulateResponse,
)
from app.redev_engine_schemas import RedevelopRequest, RedevelopResult
from app.stage_result_schemas import ReportRequest
from app.validation_lab_schemas import ReportResponse, ValidateRequest, ValidationResult

SERVICE_TIMEOUT_SECONDS = 600.0
EXAMPLE_MODEL_ID = "M001"
ResponseModel = TypeVar("ResponseModel", bound=BaseModel)


class ServiceCallError(Exception):
    """A call to redev_engine or validation_lab failed; str(error) is the stage error text."""

    def __init__(self, service: str, code: str, message: str) -> None:
        """Prefix the message with the service name and keep the error code."""
        super().__init__(f"{service}: {message}")
        self.service = service
        self.code = code


def replace_identifiers(value: Any, model_id: str, run_id: str | None) -> Any:
    """Put the real model_id and run_id into an example, including artifacts/M001/ style paths."""
    if isinstance(value, dict):
        replaced = {}
        for key, item in value.items():
            if key == "model_id":
                replaced[key] = model_id
            elif key == "run_id" and run_id is not None:
                replaced[key] = run_id
            else:
                replaced[key] = replace_identifiers(item, model_id, run_id)
        return replaced
    if isinstance(value, list):
        return [replace_identifiers(item, model_id, run_id) for item in value]
    if isinstance(value, str):
        return value.replace(f"artifacts/{EXAMPLE_MODEL_ID}/", f"artifacts/{model_id}/")
    return value


class ServiceClients:
    """One client for both downstream services. on_call receives a summary of every call, stub or real."""

    def __init__(
        self,
        settings: Settings,
        transport: httpx.BaseTransport | None = None,
        on_call: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        """Keep the settings, the optional test transport and the call reporter."""
        self.settings = settings
        self.transport = transport
        self.on_call = on_call

    def redevelop(self, request: RedevelopRequest) -> RedevelopResult:
        """POST /redevelop on redev_engine."""
        return self._call(
            "redev_engine",
            self.settings.redev_engine_url,
            "/redevelop",
            request,
            RedevelopResult,
            lambda: self._stub("redevelop_result.M001.json", RedevelopResult, request.model_id, request.run_id),
        )

    def validate(self, request: ValidateRequest) -> ValidationResult:
        """POST /validate on validation_lab."""
        return self._call(
            "validation_lab",
            self.settings.validation_lab_url,
            "/validate",
            request,
            ValidationResult,
            lambda: self._stub("validation_result.M001.json", ValidationResult, request.model_id, request.run_id),
        )

    def render_report(self, request: ReportRequest) -> ReportResponse:
        """POST /report on validation_lab."""
        folder = f"artifacts/{request.model_id}/validation"
        return self._call(
            "validation_lab",
            self.settings.validation_lab_url,
            "/report",
            request,
            ReportResponse,
            lambda: ReportResponse(
                model_id=request.model_id,
                html_path=f"{folder}/validation_report.html",
                docx_path=f"{folder}/validation_report.docx" if "docx" in request.formats else None,
                error=None,
            ),
        )

    def simulate_monitoring(self, request: MonitorSimulateRequest) -> MonitorSimulateResponse:
        """POST /monitor/simulate on validation_lab."""
        batches_dir = f"artifacts/{request.model_id}/monitoring/batches"
        batch = {"batch": "2026_01", "path": f"{batches_dir}/batch_2026_01.csv", "n": 3000, "drift_injected": False}
        return self._call(
            "validation_lab",
            self.settings.validation_lab_url,
            "/monitor/simulate",
            request,
            MonitorSimulateResponse,
            lambda: MonitorSimulateResponse(
                model_id=request.model_id, simulated=True, batches_dir=batches_dir, batches=[batch], error=None
            ),
        )

    def run_monitoring(self, request: MonitorRunRequest) -> MonitoringResult:
        """POST /monitor/run on validation_lab."""
        return self._call(
            "validation_lab",
            self.settings.validation_lab_url,
            "/monitor/run",
            request,
            MonitoringResult,
            lambda: self._stub("monitoring_result.M001.json", MonitoringResult, request.model_id, None),
        )

    def _call(
        self,
        service: str,
        base_url: str,
        path: str,
        request: BaseModel,
        response_type: type[ResponseModel],
        stub: Callable[[], ResponseModel],
    ) -> ResponseModel:
        """Answer from the stub or the real service, and report the outcome of the call."""
        started = time.perf_counter()
        summary: dict[str, Any] = {"service": service, "endpoint": f"POST {path}", "stub": self.settings.use_stubs}
        try:
            result = stub() if self.settings.use_stubs else self._post(service, base_url, path, request, response_type)
        except ServiceCallError as error:
            self._report(summary | {"outcome": error.code, "message": str(error)}, started)
            raise
        except Exception as error:
            self._report(summary | {"outcome": "ERROR", "message": f"{type(error).__name__}: {error}"}, started)
            raise
        self._report(summary | {"outcome": "ok"}, started)
        return result

    def _report(self, summary: dict[str, Any], started: float) -> None:
        """Pass the call summary, with its duration, to the reporter."""
        if self.on_call:
            self.on_call(summary | {"duration_ms": int((time.perf_counter() - started) * 1000)})

    def _stub(
        self, file_name: str, response_type: type[ResponseModel], model_id: str, run_id: str | None
    ) -> ResponseModel:
        """Load a contract example and give it this model's identifiers."""
        example = json.loads((self.settings.contracts_examples_dir / file_name).read_text(encoding="utf-8"))
        return response_type.model_validate(replace_identifiers(example, model_id, run_id))

    def _post(
        self, service: str, base_url: str, path: str, request: BaseModel, response_type: type[ResponseModel]
    ) -> ResponseModel:
        """Send one request and check the reply against the contract."""
        try:
            with httpx.Client(base_url=base_url, timeout=SERVICE_TIMEOUT_SECONDS, transport=self.transport) as client:
                response = client.post(path, json=request.model_dump(mode="json"))
        except httpx.ConnectError as error:
            raise ServiceCallError(
                service,
                "SERVICE_UNREACHABLE",
                f"not reachable at {base_url} ({error}). Start it or set USE_STUBS=true.",
            ) from error
        except httpx.TimeoutException as error:
            raise ServiceCallError(
                service, "SERVICE_TIMEOUT", f"POST {path} gave no answer within {SERVICE_TIMEOUT_SECONDS:.0f} seconds"
            ) from error
        except httpx.HTTPError as error:
            raise ServiceCallError(service, "SERVICE_ERROR", f"POST {path} failed: {error}") from error
        if response.status_code >= 400:
            code, message = read_error_body(response)
            raise ServiceCallError(service, code, f"POST {path} returned {response.status_code}: {message}")
        try:
            return response_type.model_validate(response.json())
        except (ValueError, ValidationError) as error:
            raise ServiceCallError(
                service, "CONTRACT_MISMATCH", f"POST {path} reply does not match the contract: {error}"
            ) from error


def read_error_body(response: httpx.Response) -> tuple[str, str]:
    """Read the {"error": {"code", "message"}} body, falling back to the raw text."""
    try:
        error = response.json()["error"]
        return str(error["code"]), str(error["message"])
    except (ValueError, KeyError, TypeError):
        return f"HTTP_{response.status_code}", response.text[:500] or response.reason_phrase
