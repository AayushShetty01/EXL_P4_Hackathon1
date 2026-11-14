"""The work of the discover, document and redevelop stages (stamps 1 to 3).

Each function stores its contract shaped result, writes its artifacts and returns a summary built by
code from the result, never by the LLM. Validate and monitor are in validation_lab_stages.py.
"""

from app.agents.discovery_agent import run_discovery
from app.agents.document_drift import find_drift
from app.agents.documentation_agent import render_markdown, write_documentation
from app.api_schemas import InventoryRecord
from app.artifact_store import write_json_artifact, write_text_artifact
from app.database import latest_stage_output, pipeline_status, save_stage_output, utc_timestamp
from app.pipeline_context import StageError, StageWork
from app.redev_engine_schemas import RedevelopRequest, RedevelopResult
from app.stage_result_schemas import Documentation

MAX_HEAL_ITERATIONS = 3


def approved_inventory_record(work: StageWork) -> InventoryRecord:
    """The latest inventory record of the model; later stages cannot run without one."""
    stored = latest_stage_output(work.session, work.model.model_id, "inventory_record")
    if stored is None:
        raise StageError("There is no inventory record for this model yet. Run the discover stage first.")
    return InventoryRecord.model_validate(
        stored | {"pipeline_status": pipeline_status(work.session, work.model), "revalidation_required": False}
    )


def discover_stage(work: StageWork) -> str:
    """Stamp 1: build, check and store the inventory record."""
    settings, model = work.context.settings, work.model
    outcome = run_discovery(
        settings,
        model,
        work.context.llm(work.recorder, "discovery_agent"),
        work.recorder,
        pipeline_status=pipeline_status(work.session, model),
        previous_record=latest_stage_output(work.session, model.model_id, "inventory_record"),
        today=work.context.today(),
    )
    record = outcome.record.model_dump(mode="json")
    write_json_artifact(settings, work.recorder, f"artifacts/{model.model_id}/discover/inventory_record.json", record)
    save_stage_output(work.session, model.model_id, work.run.run_id, "discover", "inventory_record", record)
    work.session.commit()
    return outcome.summary


def document_stage(work: StageWork) -> str:
    """Stamp 2: write the cited documentation, find the drift against the old document, store both."""
    settings, model = work.context.settings, work.model
    record = approved_inventory_record(work)
    llm = work.context.llm(work.recorder, "documentation_agent")
    draft = write_documentation(settings, model, record, llm, work.recorder)
    drift = find_drift(settings, model, draft.sections, work.context.llm(work.recorder, "drift_agent"), work.recorder)
    folder = f"artifacts/{model.model_id}/document"
    generated_at = utc_timestamp()
    documentation = Documentation(
        model_id=model.model_id,
        generated_at=generated_at,
        generated_by_model=draft.generated_by_model,
        groundedness=draft.groundedness,
        sections=draft.sections,
        doc_drift=drift,
        markdown_path=f"{folder}/model_document.md",
    )
    payload = documentation.model_dump(mode="json")
    write_json_artifact(settings, work.recorder, f"{folder}/model_document.json", payload)
    markdown = render_markdown(documentation, record.model_name, generated_at[:10])
    write_text_artifact(settings, work.recorder, f"{folder}/model_document.md", markdown)
    write_json_artifact(settings, work.recorder, f"{folder}/doc_drift.json", payload["doc_drift"])
    save_stage_output(work.session, model.model_id, work.run.run_id, "document", "documentation", payload)
    work.session.commit()
    grounded = draft.groundedness
    verified_drift = sum(item.status == "VERIFIED" for item in drift)
    return (
        f"{len(draft.sections)} sections, {grounded.claims_total} claims, {grounded.claims_verified} verified. "
        f"{len(drift)} differences against the old document, {verified_drift} verified."
    )


def redevelopment_summary(result: RedevelopResult) -> str:
    """Plain summary of a rebuild, taken from its JSON fields."""
    parts = [f"Redevelopment status {result.status} after {len(result.iterations)} iterations."]
    if result.unit_tests:
        parts.append(f"{result.unit_tests.passed} of {result.unit_tests.total} unit tests passed.")
    if result.parity:
        levels = {level.level: level for level in result.parity.levels}
        record_level, decision_level = levels.get("L2_record_scores"), levels.get("L3_decisions")
        parts.append(f"{result.parity.records_compared} records compared.")
        if record_level and record_level.max_abs_diff is not None:
            parts.append(f"Largest PD difference {record_level.max_abs_diff:g}.")
        if decision_level and decision_level.match_rate is not None:
            parts.append(f"Decision match rate {decision_level.match_rate:.2%}.")
    return " ".join(parts)


def redevelop_stage(work: StageWork) -> str:
    """Stamp 3: ask redev_engine for the rebuild and parity proof, and store the result as returned."""
    model = work.model
    request = RedevelopRequest(
        run_id=work.run.run_id,
        model_id=model.model_id,
        estate_path=model.folder,
        max_heal_iterations=MAX_HEAL_ITERATIONS,
        use_pitfall_library=True,
    )
    result = work.context.services(work.recorder).redevelop(request)
    if not work.context.settings.use_stubs:
        # A stub answer carries example traces of calls that never happened, so only real ones are audited.
        for trace in result.llm_trace:
            work.recorder.llm_call("redev_engine", trace.model_dump(mode="json"))
    save_stage_output(
        work.session, model.model_id, work.run.run_id, "redevelop", "redevelopment", result.model_dump(mode="json")
    )
    work.session.commit()
    summary = redevelopment_summary(result)
    if result.status in ("PARITY_FAILED", "ERROR"):
        raise StageError(f"{summary} {result.error or 'Parity was not reached.'}".strip())
    return summary
