"""File endpoints: text content of estate and artifact files, and streaming of binary artifacts.

Only model_estate/ and artifacts/ are readable, _answer_keys is always blocked, text is capped at 1 MB.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.api.api_errors import api_error
from app.api_schemas import FileView
from app.config import Settings, request_settings
from app.estate_scanner import FileAccessError, read_text_file, resolve_artifact_path

router = APIRouter(prefix="/api", tags=["files"])
SettingsDependency = Annotated[Settings, Depends(request_settings)]


@router.get("/files")
def read_file(path: str, settings: SettingsDependency) -> FileView:
    """Text content of one file, by its path relative to the repository root."""
    try:
        return read_text_file(settings, path)
    except FileAccessError as error:
        raise api_error(error.status_code, error.code, error.message) from error


@router.get("/artifacts/{path:path}")
def stream_artifact(path: str, settings: SettingsDependency) -> FileResponse:
    """Stream a binary artifact such as a chart or a report; the path is relative to artifacts/."""
    try:
        return FileResponse(resolve_artifact_path(settings, path))
    except FileAccessError as error:
        raise api_error(error.status_code, error.code, error.message) from error
