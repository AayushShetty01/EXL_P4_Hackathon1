"""Seed the demo: scan the estate and run every model through its stages with automatic approvals.

Run from the factory_core folder: python -m scripts.seed_demo [--models M001 M002]
Needs a key (LLM_MODE=live) or recorded replies (LLM_MODE=replay), and the other services or USE_STUBS=true.
Gates are approved by demo_developer and demo_validator, marked automatic in the audit trail, and left out
of the human review minutes.
"""

import argparse
import sys

from sqlmodel import Session, select

from app.api_schemas import RunCreateRequest
from app.config import Settings, load_settings
from app.database import ModelRow, create_database_engine, load_run
from app.estate_scanner import register_estate
from app.gate_decisions import GateError
from app.pipeline_context import PipelineContext
from app.pipeline_runner import PipelineRunner


def seed(settings: Settings, model_ids: list[str] | None = None, context_options: dict | None = None) -> int:
    """Run the chosen (or all estate) models with auto approval; return 0 when every run completed."""
    engine = create_database_engine(settings.database_path)
    with Session(engine) as session:
        register_estate(session, settings)
        estate_models = [row.model_id for row in session.exec(select(ModelRow).where(ModelRow.source == "estate"))]
    targets = model_ids or sorted(estate_models)
    if not targets:
        print("No models in the estate. Add model folders to model_estate/ first.")
        return 1
    runner = PipelineRunner(PipelineContext(settings, engine, **(context_options or {})), background=False)
    completed = 0
    for model_id in targets:
        try:
            run_id = runner.start_run(model_id, RunCreateRequest(auto_approve=True))
        except GateError as error:
            print(f"{model_id}: not started: {error.message}")
            continue
        with Session(engine) as session:
            run = load_run(session, run_id)
        completed += run.status == "COMPLETED"
        print(f"{model_id} {run_id}: {run.status}")
        for stage in run.stages:
            detail = stage.summary or stage.skip_reason or stage.error or ""
            print(f"  {stage.stage:<10} {stage.status:<16} {detail}")
    runner.close()
    print(f"{completed} of {len(targets)} runs completed.")
    return 0 if completed == len(targets) else 1


def main(argv: list[str] | None = None) -> int:
    """Read the arguments and seed the demo."""
    parser = argparse.ArgumentParser(description="Run every estate model through the pipeline with auto approval.")
    parser.add_argument("--models", nargs="*", help="model ids to run (default: every estate model)")
    arguments = parser.parse_args(argv)
    return seed(load_settings(), arguments.models)


if __name__ == "__main__":
    sys.exit(main())
