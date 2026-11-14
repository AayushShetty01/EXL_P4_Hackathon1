"""Artifact writes land under artifacts/ and are recorded in the audit trail."""

import hashlib
import json

import pytest
from sqlalchemy import Engine
from sqlmodel import Session

from app.artifact_store import write_json_artifact, write_text_artifact
from app.audit_trail import AuditRecorder, list_events
from app.config import Settings


def test_json_artifact_is_written_and_audited(settings: Settings, engine: Engine) -> None:
    """The file is written under artifacts/ and an artifact_written event carries its hash."""
    recorder = AuditRecorder(engine, model_id="M001", run_id="run_M001_001", stage="discover")
    path = write_json_artifact(
        settings, recorder, "artifacts/M001/discover/inventory_record.json", {"model_id": "M001"}
    )
    written = settings.artifacts_dir / "M001" / "discover" / "inventory_record.json"
    assert json.loads(written.read_text()) == {"model_id": "M001"}
    with Session(engine) as session:
        [event] = list_events(session)
    assert (event.action, event.stage, event.detail["path"]) == ("artifact_written", "discover", path)
    assert event.detail["sha256"] == hashlib.sha256(written.read_bytes()).hexdigest()


@pytest.mark.parametrize("path", ["model_estate/M001/x.md", "artifacts/../factory_core/app/main.py"])
def test_writes_outside_artifacts_are_refused(settings: Settings, engine: Engine, path: str) -> None:
    """Run outputs never go into source folders."""
    with pytest.raises(ValueError):
        write_text_artifact(settings, AuditRecorder(engine), path, "text")
