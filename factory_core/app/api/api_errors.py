"""Error responses in the contract shape {"error": {"code": ..., "message": ...}} for every endpoint."""

import logging
from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("factory_core")
DEFAULT_CODES = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}


def api_error(status_code: int, code: str, message: str) -> HTTPException:
    """Build the exception an endpoint raises to answer with a contract error body."""
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    """A JSON response with the contract error body."""
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message}})


def http_error_handler(_request: Request, error: StarletteHTTPException) -> JSONResponse:
    """Turn any HTTP exception, including unknown routes, into the contract error body."""
    detail: Any = error.detail
    if isinstance(detail, dict) and "code" in detail and "message" in detail:
        return error_response(error.status_code, str(detail.get("code")), str(detail.get("message")))
    code = DEFAULT_CODES.get(error.status_code, f"HTTP_{error.status_code}")
    return error_response(error.status_code, code, str(detail))


def validation_error_handler(_request: Request, error: RequestValidationError) -> JSONResponse:
    """Report an invalid request body, path or query as 422 INVALID_REQUEST with readable details."""
    problems = [f"{'.'.join(str(part) for part in problem['loc'])}: {problem['msg']}" for problem in error.errors()]
    return error_response(422, "INVALID_REQUEST", "; ".join(problems))


def unexpected_error_handler(_request: Request, error: Exception) -> JSONResponse:
    """Answer an unexpected failure with 500 INTERNAL_ERROR; the log holds the traceback, never request text."""
    logger.exception("Unexpected error while answering a request")
    return error_response(500, "INTERNAL_ERROR", f"{type(error).__name__}: {error}")
