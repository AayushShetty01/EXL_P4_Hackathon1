"""Built-in sample model, registered from the contract examples while model_estate/ holds no models.

Its name marks it as a sample, every value in it is an illustrative contract example (never a result),
and it is removed as soon as a scan finds real models. It writes no audit events.
"""

import json
from typing import Any

from sqlmodel import Session, select

from app.api_schemas import Run
from app.config import Settings
from app.database import (
    ModelRow,
    OutputKind,
    RunRow,
    StageRunRow,
    delete_model_data,
    save_stage_output,
    utc_timestamp,
)

SAMPLE_NAME_SUFFIX = " (sample from contract examples)"
SAMPLE_OUTPUTS: tuple[tuple[OutputKind, str | None, str], ...] = (
    ("documentation", "document", "documentation.M001.json"),
    ("redevelopment", "redevelop", "redevelop_result.M001.json"),
    ("validation_view", "validate", "validation_view.M001.json"),
    ("monitoring", "monitor", "monitoring_result.M001.json"),
)


def load_example(settings: Settings, file_name: str) -> dict[str, Any]:
    """Read one file from contracts/examples/."""
    return json.loads((settings.contracts_examples_dir / file_name).read_text(encoding="utf-8"))


def register_sample_model(session: Session, settings: Settings) -> str:
    """Store the sample model, its example run and its example stage outputs; return its model id."""
    inventory = load_example(settings, "inventory_record.M001.json")
    manifest = load_example(settings, "estate_manifest.M001.json")
    run = Run.model_validate(load_example(settings, "run.json"))
    model_id = inventory["model_id"]
    inventory["model_name"] = (inventory.get("model_name") or model_id) + SAMPLE_NAME_SUFFIX
    now = utc_timestamp()
    session.add(
        ModelRow(
            model_id=model_id,
            source="sample",
            folder=manifest["folder"],
            language=manifest["language"],
            registration={"manifest": manifest, "register_row": None, "source_files": inventory["source_files"]},
            active_run_id=run.run_id,
            created_at=now,
            updated_at=now,
        )
    )
    session.add(
        RunRow(
            run_id=run.run_id,
            model_id=model_id,
            status=run.status,
            current_stage=run.current_stage,
            auto_approve=run.auto_approve,
            started_at=run.started_at,
            finished_at=run.finished_at,
        )
    )
    for position, stage in enumerate(run.stages):
        session.add(
            StageRunRow(
                run_id=run.run_id,
                stage=stage.stage,
                position=position,
                status=stage.status,
                started_at=stage.started_at,
                finished_at=stage.finished_at,
                duration_seconds=stage.duration_seconds,
                summary=stage.summary,
                skip_reason=stage.skip_reason,
                error=stage.error,
                gate=stage.gate.model_dump(mode="json") if stage.gate else None,
            )
        )
    save_stage_output(session, model_id, run.run_id, "discover", "inventory_record", inventory)
    for kind, stage_name, file_name in SAMPLE_OUTPUTS:
        save_stage_output(session, model_id, run.run_id, stage_name, kind, load_example(settings, file_name))
    session.commit()
    return model_id


def remove_sample_model(session: Session) -> None:
    """Delete the sample model and everything stored for it."""
    for row in session.exec(select(ModelRow).where(ModelRow.source == "sample")).all():
        delete_model_data(session, row.model_id)
    session.commit()
