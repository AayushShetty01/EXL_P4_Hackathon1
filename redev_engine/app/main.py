"""Entry point of redev_engine: /health, /redevelop, /parity, /pitfalls."""

import json

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import REPO_ROOT, SERVICE_NAME, VERSION, get_settings
from app.pitfall_library import list_pitfalls
from app.redevelop_pipeline import PipelineError, parity_only, redevelop
from app.schemas import Parity, ParityRequest, RedevelopRequest, RedevelopResult

STUB_EXAMPLE = REPO_ROOT / "contracts" / "examples" / "redevelop_result.M001.json"

app = FastAPI(title="redev_engine", version=VERSION)


def error_response(status: int, code: str, message: str) -> JSONResponse:
    """Error body in the shared format."""
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


@app.exception_handler(PipelineError)
def pipeline_error_handler(_: Request, error: PipelineError) -> JSONResponse:
    """Turn pipeline errors into the shared error format."""
    return error_response(error.http_status, error.code, error.message)


@app.exception_handler(RequestValidationError)
def validation_error_handler(_: Request, error: RequestValidationError) -> JSONResponse:
    """Turn request validation errors into the shared error format."""
    return error_response(422, "INVALID_REQUEST", str(error.errors()))


@app.get("/health")
def health() -> dict:
    """Liveness check."""
    return {"status": "ok", "service": SERVICE_NAME, "version": VERSION}


def stub_result(request: RedevelopRequest) -> RedevelopResult:
    """The contract example with the ids of the request, for integration without the LLM."""
    if not STUB_EXAMPLE.exists():
        raise PipelineError("STUB_UNAVAILABLE", "contracts/examples/redevelop_result.M001.json is missing", 503)
    text = STUB_EXAMPLE.read_text(encoding="utf-8").replace("M001", request.model_id)
    example = json.loads(text)
    example["run_id"] = request.run_id
    return RedevelopResult.model_validate(example)


@app.post("/redevelop", response_model=RedevelopResult)
def post_redevelop(request: RedevelopRequest) -> RedevelopResult:
    """Run the full rebuild for one model (synchronous, can take minutes)."""
    if get_settings().stub_mode:
        return stub_result(request)
    return redevelop(request)


@app.post("/parity", response_model=Parity)
def post_parity(request: ParityRequest) -> Parity:
    """Re-run only the deterministic parity check for an existing rebuilt model.py."""
    return parity_only(request.model_id, request.estate_path)


@app.get("/pitfalls")
def get_pitfalls() -> dict:
    """The translation pitfall library."""
    return {"pitfalls": [p.model_dump() for p in list_pitfalls()]}
