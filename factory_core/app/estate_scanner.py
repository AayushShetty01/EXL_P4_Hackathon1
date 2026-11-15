"""Finds model folders in the estate, reads their manifests and the bank's register, and registers them.

Also the safe file reader: only files under model_estate/ and artifacts/, never anything in _answer_keys.
"""

import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ValidationError
from sqlmodel import Session, select

from app.api_schemas import FileView, SourceFile
from app.config import Settings
from app.database import ModelRow, utc_timestamp
from app.sample_model import register_sample_model, remove_sample_model
from app.schemas import EstateManifest

MAX_TEXT_FILE_BYTES = 1_048_576
REGISTER_FILE_NAME = "estate_register.csv"
ANSWER_KEYS_FOLDER = "_answer_keys"
LANGUAGE_BY_SUFFIX = {
    ".sas": "sas",
    ".r": "r",
    ".py": "python",
    ".md": "markdown",
    ".json": "json",
    ".csv": "csv",
    ".html": "html",
    ".sql": "sql",
    ".yaml": "yaml",
    ".yml": "yaml",
}


class EstateScanError(Exception):
    """A manifest, a listed file or the register is invalid, so the estate cannot be registered."""

    def __init__(self, code: str, message: str) -> None:
        """Keep the error code for the API response."""
        super().__init__(message)
        self.code = code
        self.message = message


class FileAccessError(Exception):
    """A file request was refused; carries the HTTP status and error code for the API."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        """Keep the HTTP status and error code for the API response."""
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


class RegisterRow(BaseModel):
    """One row of estate_register.csv, the bank's stale inventory spreadsheet."""

    model_id: str
    model_name: str | None = None
    business_line: str | None = None
    model_owner: str | None = None
    exposure_gbp_m: float | None = None
    customer_facing: bool | None = None
    regulatory_use: str | None = None
    last_code_change: str | None = None
    doc_last_updated: str | None = None
    last_validated: str | None = None
    status: str | None = None


@dataclass(frozen=True)
class EstateModel:
    """One model folder found in the estate."""

    model_id: str
    folder: str
    manifest: EstateManifest
    register_row: RegisterRow | None
    source_files: list[SourceFile]


def repository_relative(settings: Settings, path: Path) -> str:
    """Path relative to the repository root with forward slashes (absolute when outside the root)."""
    try:
        return path.resolve().relative_to(settings.repository_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def read_register(settings: Settings) -> dict[str, RegisterRow]:
    """Read estate_register.csv into rows keyed by model id; empty when the file does not exist."""
    path = settings.estate_dir / REGISTER_FILE_NAME
    if not path.is_file():
        return {}
    rows: dict[str, RegisterRow] = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = set(RegisterRow.model_fields) - set(reader.fieldnames or [])
        if missing:
            raise EstateScanError("INVALID_REGISTER", f"{REGISTER_FILE_NAME} is missing columns: {sorted(missing)}")
        for line_number, raw in enumerate(reader, start=2):
            values = {key: (value or "").strip() or None for key, value in raw.items() if key}
            try:
                row = RegisterRow.model_validate(values)
            except ValidationError as error:
                raise EstateScanError(
                    "INVALID_REGISTER", f"{REGISTER_FILE_NAME} line {line_number}: {error}"
                ) from error
            rows[row.model_id] = row
    return rows


def load_manifest(manifest_path: Path, folder: str) -> EstateManifest:
    """Read and validate one manifest.json; its folder field must match where it was found."""
    try:
        manifest = EstateManifest.model_validate(json.loads(manifest_path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, ValidationError) as error:
        raise EstateScanError("INVALID_MANIFEST", f"{folder}/manifest.json is invalid: {error}") from error
    if manifest.folder != folder:
        raise EstateScanError(
            "INVALID_MANIFEST", f"{folder}/manifest.json says folder {manifest.folder!r}, expected {folder!r}"
        )
    return manifest


def describe_source_files(settings: Settings, folder_path: Path, manifest: EstateManifest) -> list[SourceFile]:
    """List the code and document files of a manifest with line counts and SHA 256 hashes."""
    listed = [("code", name) for name in manifest.code_files] + [("doc", name) for name in manifest.doc_files]
    files = []
    for kind, name in listed:
        path = (folder_path / name).resolve()
        if not path.is_relative_to(folder_path.resolve()) or not path.is_file():
            raise EstateScanError("INVALID_MANIFEST", f"{manifest.folder}: listed file {name!r} not found")
        data = path.read_bytes()
        files.append(
            SourceFile(
                path=repository_relative(settings, path),
                kind=kind,
                lines=len(data.decode("utf-8", errors="replace").splitlines()),
                sha256=hashlib.sha256(data).hexdigest(),
            )
        )
    return files


def scan_estate(settings: Settings) -> list[EstateModel]:
    """Find every folder with a manifest.json; folders starting with _ or . are skipped."""
    if not settings.estate_dir.is_dir():
        return []
    register = read_register(settings)
    models: list[EstateModel] = []
    for folder_path in sorted(path for path in settings.estate_dir.iterdir() if path.is_dir()):
        manifest_path = folder_path / "manifest.json"
        if folder_path.name.startswith(("_", ".")) or not manifest_path.is_file():
            continue
        folder = repository_relative(settings, folder_path)
        manifest = load_manifest(manifest_path, folder)
        if any(model.model_id == manifest.model_id for model in models):
            raise EstateScanError("INVALID_MANIFEST", f"model id {manifest.model_id} appears in two folders")
        source_files = describe_source_files(settings, folder_path, manifest)
        models.append(EstateModel(manifest.model_id, folder, manifest, register.get(manifest.model_id), source_files))
    return models


def register_estate(session: Session, settings: Settings) -> list[str]:
    """Register every estate model; register the built-in sample only when nothing is registered at all."""
    models = scan_estate(settings)
    if not models:
        if session.exec(select(ModelRow)).first() is None:
            register_sample_model(session, settings)
        return []
    remove_sample_model(session)
    now = utc_timestamp()
    for model in models:
        registration = {
            "manifest": model.manifest.model_dump(mode="json"),
            "register_row": model.register_row.model_dump(mode="json") if model.register_row else None,
            "source_files": [source_file.model_dump(mode="json") for source_file in model.source_files],
        }
        row = session.get(ModelRow, model.model_id)
        if row is not None and row.registration == registration and row.folder == model.folder:
            continue
        if row is None:
            row = ModelRow(
                model_id=model.model_id,
                source="estate",
                folder=model.folder,
                language=model.manifest.language,
                registration=registration,
                created_at=now,
                updated_at=now,
            )
        else:
            row.folder = model.folder
            row.language = model.manifest.language
            row.registration = registration
            row.updated_at = now
        session.add(row)
    session.commit()
    return [model.model_id for model in models]


def check_requested_path(path: str) -> None:
    """Refuse empty, absolute or parent paths and anything that mentions the answer keys."""
    if not path or path.startswith(("/", "~")) or "\\" in path or ":" in path or ".." in path:
        raise FileAccessError(400, "INVALID_PATH", f"Path {path!r} must be relative to the repository root")
    if ANSWER_KEYS_FOLDER in path.lower():
        raise FileAccessError(403, "FORBIDDEN_PATH", "The answer keys are only read by the evaluation scripts")


def resolve_safe_path(settings: Settings, relative_path: str) -> Path:
    """Resolve a repository relative path that must stay inside model_estate/ or artifacts/."""
    check_requested_path(relative_path)
    candidate = (settings.repository_root / relative_path).resolve()
    allowed_roots = (settings.estate_dir.resolve(), settings.artifacts_dir.resolve())
    inside = any(candidate.is_relative_to(root) for root in allowed_roots)
    if not inside or ANSWER_KEYS_FOLDER in (part.lower() for part in candidate.parts):
        raise FileAccessError(403, "FORBIDDEN_PATH", "Only files under model_estate/ and artifacts/ can be read")
    return candidate


def read_text_file(settings: Settings, relative_path: str) -> FileView:
    """Read one text file (at most 1 MB) through the safe path rules."""
    path = resolve_safe_path(settings, relative_path)
    if not path.is_file():
        raise FileAccessError(404, "FILE_NOT_FOUND", f"File {relative_path!r} does not exist")
    if path.stat().st_size > MAX_TEXT_FILE_BYTES:
        raise FileAccessError(413, "FILE_TOO_LARGE", f"File {relative_path!r} is larger than 1 MB")
    try:
        content = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as error:
        raise FileAccessError(415, "FILE_NOT_TEXT", f"File {relative_path!r} is not UTF-8 text") from error
    return FileView(
        path=repository_relative(settings, path),
        language=LANGUAGE_BY_SUFFIX.get(path.suffix.lower(), "text"),
        lines=len(content.splitlines()),
        content=content,
    )


def resolve_artifact_path(settings: Settings, path: str) -> Path:
    """Resolve an artifact path given relative to artifacts/ (a leading artifacts/ is accepted too)."""
    check_requested_path(path)
    relative = path.removeprefix("artifacts/")
    candidate = (settings.artifacts_dir / relative).resolve()
    if not candidate.is_relative_to(settings.artifacts_dir.resolve()):
        raise FileAccessError(403, "FORBIDDEN_PATH", "Only files under artifacts/ can be streamed")
    if not candidate.is_file():
        raise FileAccessError(404, "FILE_NOT_FOUND", f"Artifact {path!r} does not exist")
    return candidate
