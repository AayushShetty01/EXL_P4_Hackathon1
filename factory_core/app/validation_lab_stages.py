"""The work of the validate and monitor stages (stamps 4 and 5); both call validation_lab.

Scores come from the rebuild when it was translated and scored (parity passed, or there are no legacy
outputs to compare against), otherwise from the legacy golden files. Feature columns
are the discovered inputs that exist in the data header. All numbers come from validation_lab; the
validator agent only writes words around them.
"""

import csv
from dataclasses import dataclass

from app.agents.validator_agent import write_narrative
from app.api_schemas import InventoryRecord
from app.database import latest_stage_output, save_stage_output
from app.estate_scanner import resolve_safe_path
from app.monitoring_schemas import MonitorReference, MonitorRunRequest, MonitorSimulateRequest
from app.pipeline_context import StageError, StageWork, error_text
from app.pipeline_stages import approved_inventory_record
from app.redev_engine_schemas import RedevelopResult
from app.schemas import EstateManifest, ManifestData
from app.stage_result_schemas import ParitySummary, ReportPaths, ReportRequest, SignOff, ValidationView
from app.validation_lab_schemas import ValidateData, ValidateRequest, ValidateScores

SCORE_COLUMNS = {"pd_col": "pd", "score_col": "score", "decision_col": "decision"}
REBUILT_STATUSES = ("PARITY_PASSED", "TRANSLATED_NO_GOLDEN")
MONITORING_BATCHES = 6
MONITORING_BATCH_SIZE = 3000
DRIFT_START_BATCH = 4
DRIFT_STRENGTH = 0.5
MONITORING_SEED = 42


@dataclass(frozen=True)
class ModelData:
    """Repository paths and columns of one model's data and scores."""

    data: ManifestData
    dev_path: str
    oot_path: str
    scores_dev: str
    scores_oot: str
    model_module_path: str | None
    feature_cols: list[str]
    parity_summary: ParitySummary | None


def parity_summary(result: RedevelopResult) -> ParitySummary:
    """The parity facts the validation report needs, taken from the rebuild result."""
    levels = {level.level: level for level in (result.parity.levels if result.parity else [])}
    record_level, decision_level = levels.get("L2_record_scores"), levels.get("L3_decisions")
    return ParitySummary(
        status=result.status,
        records_compared=result.parity.records_compared if result.parity else 0,
        max_abs_diff_pd=record_level.max_abs_diff if record_level else None,
        decision_match_rate=decision_level.match_rate if decision_level else None,
        certificate_md_path=result.parity.certificate_md_path if result.parity else None,
    )


def read_header(work: StageWork, path: str) -> list[str]:
    """Column names of a CSV file in the estate."""
    with resolve_safe_path(work.context.settings, path).open(newline="", encoding="utf-8-sig") as handle:
        return next(csv.reader(handle), [])


def count_rows(work: StageWork, path: str) -> int:
    """Number of data rows of a CSV file (header excluded)."""
    with resolve_safe_path(work.context.settings, path).open(encoding="utf-8-sig") as handle:
        return max(sum(1 for _ in handle) - 1, 0)


def feature_columns(header: list[str], record: InventoryRecord, data: ManifestData) -> list[str]:
    """Discovered inputs found in the header (any case); all other columns when none match."""
    excluded = {data.id_col, data.target_col, *data.protected_cols}
    by_lower = {column.lower(): column for column in header if column not in excluded}
    matched = [
        by_lower[variable.name.lower()] for variable in record.input_variables if variable.name.lower() in by_lower
    ]
    return list(dict.fromkeys(matched)) or [column for column in header if column not in excluded]


def model_data(work: StageWork, record: InventoryRecord) -> ModelData:
    """Data, score files and features for validation_lab; fails clearly when no scores exist."""
    model = work.model
    manifest = EstateManifest.model_validate(model.registration["manifest"])
    if manifest.data is None:
        raise StageError("The model has no data.")
    dev_path, oot_path = f"{model.folder}/{manifest.data.dev_path}", f"{model.folder}/{manifest.data.oot_path}"
    stored = latest_stage_output(work.session, model.model_id, "redevelopment")
    rebuild = RedevelopResult.model_validate(stored) if stored else None
    if rebuild and rebuild.status in REBUILT_STATUSES:
        files = {generated.kind: generated.path for generated in rebuild.generated_files}
        folder = f"artifacts/{model.model_id}/redevelop"
        scores_dev = files.get("scores_dev", f"{folder}/scored_dev.csv")
        scores_oot = files.get("scores_oot", f"{folder}/scored_oot.csv")
        module, parity = files.get("model_code", f"{folder}/model.py"), parity_summary(rebuild)
    elif manifest.golden:
        scores_dev = f"{model.folder}/{manifest.golden.scored_dev_path}"
        scores_oot = f"{model.folder}/{manifest.golden.scored_oot_path}"
        module, parity = None, None
    else:
        raise StageError("No scores to validate: parity has not passed and the estate has no golden scored files.")
    header = read_header(work, dev_path)
    return ModelData(
        manifest.data,
        dev_path,
        oot_path,
        scores_dev,
        scores_oot,
        module,
        feature_columns(header, record, manifest.data),
        parity,
    )


def validate_stage(work: StageWork) -> str:
    """Stamp 4: compute the validation in validation_lab, write the narrative, render the report."""
    settings, model = work.context.settings, work.model
    record = approved_inventory_record(work)
    data = model_data(work, record)
    services = work.context.services(work.recorder)
    result = services.validate(
        ValidateRequest(
            run_id=work.run.run_id,
            model_id=model.model_id,
            model_type=record.model_type or "other",
            data=ValidateData(
                dev_path=data.dev_path, oot_path=data.oot_path, id_col=data.data.id_col, target_col=data.data.target_col
            ),
            scores=ValidateScores(dev_path=data.scores_dev, oot_path=data.scores_oot, **SCORE_COLUMNS),
            feature_cols=data.feature_cols,
            protected_cols=data.data.protected_cols,
            model_module_path=data.model_module_path,
            thresholds=None,
        )
    )
    if result.status != "COMPLETED" or result.error:
        raise StageError(f"validation_lab returned status {result.status}: {error_text(result.error)}")
    documentation = latest_stage_output(work.session, model.model_id, "documentation") or {}
    limitations = next((s["markdown"] for s in documentation.get("sections", []) if s["id"] == "limitations"), None)
    outcome = write_narrative(
        work.context.llm(work.recorder, "validator_agent"),
        work.recorder,
        result=result,
        record=record,
        limitations=limitations,
        parity=data.parity_summary,
        validator_model=settings.llm_model_validator,
    )
    report = services.render_report(
        ReportRequest(
            run_id=work.run.run_id,
            model_id=model.model_id,
            validation_result_path=result.result_path or f"artifacts/{model.model_id}/validation/result.json",
            inventory_record=record,
            parity_summary=data.parity_summary,
            narrative=outcome.narrative,
            sign_off=SignOff(validator_agent_model=outcome.validator_model),
            formats=["html", "docx"],
        )
    )
    if report.error:
        raise StageError(f"validation_lab could not render the report: {error_text(report.error)}")
    view = ValidationView(
        model_id=model.model_id,
        result=result,
        narrative=outcome.narrative,
        number_grounding=outcome.number_grounding,
        validator_agent_model=outcome.validator_model,
        report=ReportPaths(html_path=report.html_path, docx_path=report.docx_path),
    )
    save_stage_output(
        work.session, model.model_id, work.run.run_id, "validate", "validation_view", view.model_dump(mode="json")
    )
    work.session.commit()
    severities = [finding.severity for finding in result.findings]
    grounding = outcome.number_grounding
    return (
        f"Overall rating {result.overall_rating}. {len(severities)} findings ({severities.count('HIGH')} high, "
        f"{severities.count('MEDIUM')} medium, {severities.count('LOW')} low). "
        f"{grounding.numbers_verified} of {grounding.numbers_in_narrative} narrative numbers verified."
    )


def monitor_stage(work: StageWork) -> str:
    """Stamp 5: simulate production batches with drift, monitor them, and flag revalidation when triggered."""
    model = work.model
    record = approved_inventory_record(work)
    data = model_data(work, record)
    services = work.context.services(work.recorder)
    columns = {"id_col": data.data.id_col, "target_col": data.data.target_col, "pd_col": "pd", "score_col": "score"}
    simulated = services.simulate_monitoring(
        MonitorSimulateRequest(
            model_id=model.model_id,
            data_path=data.oot_path,
            scores_path=data.scores_oot,
            feature_cols=data.feature_cols,
            n_batches=MONITORING_BATCHES,
            batch_size=max(100, min(MONITORING_BATCH_SIZE, count_rows(work, data.oot_path))),
            drift_start_batch=DRIFT_START_BATCH,
            drift_strength=DRIFT_STRENGTH,
            seed=MONITORING_SEED,
            **columns,
        )
    )
    if simulated.error:
        raise StageError(f"validation_lab could not simulate batches: {error_text(simulated.error)}")
    result = services.run_monitoring(
        MonitorRunRequest(
            model_id=model.model_id,
            reference=MonitorReference(data_path=data.dev_path, scores_path=data.scores_dev),
            batches_dir=simulated.batches_dir,
            feature_cols=data.feature_cols,
            thresholds=None,
            **columns,
        )
    )
    if result.status != "COMPLETED" or result.error:
        raise StageError(f"validation_lab monitoring returned status {result.status}: {error_text(result.error)}")
    save_stage_output(
        work.session, model.model_id, work.run.run_id, "monitor", "monitoring", result.model_dump(mode="json")
    )
    if result.revalidation_triggered:
        model.revalidation_required = True
        work.session.add(model)
        work.recorder.record("revalidation_triggered", detail={"reason": result.trigger_reason})
    work.session.commit()
    alerts = [batch.alert for batch in result.batches]
    trigger = (
        f"Revalidation triggered: {result.trigger_reason}."
        if result.revalidation_triggered
        else "No revalidation trigger."
    )
    return (
        f"{len(result.batches)} simulated batches monitored: {alerts.count('RED')} red, {alerts.count('AMBER')} amber. "
        f"{trigger}"
    )
