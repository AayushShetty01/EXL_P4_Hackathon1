"""Writes run outputs under artifacts/ and records every write in the audit trail.

Paths are given relative to the repository root, for example artifacts/M001/discover/inventory_record.json.
"""

import hashlib
import json
from typing import Any

from app.audit_trail import AuditRecorder
from app.config import Settings


def write_text_artifact(settings: Settings, recorder: AuditRecorder, path: str, content: str) -> str:
    """Write a text file under artifacts/, record an artifact_written event and return the path."""
    if not path.startswith("artifacts/") or ".." in path:
        raise ValueError(f"Artifacts are written under artifacts/ only, got {path!r}")
    target = settings.artifacts_dir / path.removeprefix("artifacts/")
    target.parent.mkdir(parents=True, exist_ok=True)
    data = content.encode("utf-8")
    target.write_bytes(data)
    recorder.record("artifact_written", detail={"path": path, "sha256": hashlib.sha256(data).hexdigest()})
    return path


def write_json_artifact(settings: Settings, recorder: AuditRecorder, path: str, payload: Any) -> str:
    """Write a JSON file under artifacts/ (indented, UTF-8) and record the write."""
    return write_text_artifact(settings, recorder, path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
