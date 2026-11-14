"""Model inventory endpoints: list, estate scan, one inventory record, and the factory metrics."""

from collections import Counter
from typing import Annotated, Any, get_args

from fastapi import APIRouter, Depends
from sqlmodel import Session, col, select

from app.api.api_errors import api_error
from app.api_schemas import FactoryMetrics, InventoryRecord, ModelList, ModelSummary, ScanResult
from app.config import Settings, request_settings
from app.database import ModelRow, RunRow, StageRunRow, get_session, latest_stage_output, pipeline_status
from app.estate_scanner import EstateScanError, register_estate
from app.schemas import Language, Severity, Tier

router = APIRouter(prefix="/api", tags=["models"])
SessionDependency = Annotated[Session, Depends(get_session)]
SettingsDependency = Annotated[Settings, Depends(request_settings)]
MANUAL_BASELINE_WEEKS_PER_VALIDATION = [8, 12]


def get_model_row(session: Session, model_id: str) -> ModelRow:
    """Return a registered model or raise 404 MODEL_NOT_FOUND."""
    model = session.get(ModelRow, model_id)
    if model is None:
        raise api_error(404, "MODEL_NOT_FOUND", f"Model {model_id} is not registered. Run POST /api/estate/scan.")
    return model


def registered_record(model: ModelRow) -> dict[str, Any]:
    """Inventory record before discovery: register and manifest facts only, discovery fields null."""
    register = model.registration.get("register_row") or {}
    return {
        "model_id": model.model_id,
        "model_name": register.get("model_name"),
        "business_line": register.get("business_line"),
        "model_owner": register.get("model_owner"),
        "language": model.language,
        "exposure_gbp_m": register.get("exposure_gbp_m"),
        "regulatory_use": register.get("regulatory_use"),
        "customer_facing": register.get("customer_facing"),
        "doc_last_updated": register.get("doc_last_updated"),
        "last_code_change": register.get("last_code_change"),
        "last_validated": register.get("last_validated"),
        "source_files": model.registration.get("source_files", []),
        "created_at": model.created_at,
        "updated_at": model.updated_at,
    }


def build_inventory_record(session: Session, model: ModelRow) -> InventoryRecord:
    """The stored discovery record (or the registered facts) with the live pipeline status."""
    stored = latest_stage_output(session, model.model_id, "inventory_record")
    record = dict(stored) if stored else registered_record(model)
    record["pipeline_status"] = pipeline_status(session, model)
    record["revalidation_required"] = model.revalidation_required
    return InventoryRecord.model_validate(record)


def build_model_summary(session: Session, model: ModelRow) -> ModelSummary:
    """One dashboard row for a model."""
    record = build_inventory_record(session, model)
    validation = latest_stage_output(session, model.model_id, "validation_view")
    return ModelSummary(
        model_id=model.model_id,
        model_name=record.model_name,
        model_type=record.model_type,
        language=record.language,
        algorithm=record.algorithm,
        business_line=record.business_line,
        tier=record.tiering.tier if record.tiering else None,
        doc_status=record.doc_status,
        last_validated=record.last_validated,
        pipeline_status=record.pipeline_status,
        overall_rating=validation["result"].get("overall_rating") if validation else None,
        revalidation_required=model.revalidation_required,
        active_run_id=model.active_run_id,
    )


@router.get("/models", response_model=ModelList)
def list_models(session: SessionDependency) -> ModelList:
    """Every registered model, ordered by model id."""
    models = session.exec(select(ModelRow).order_by(col(ModelRow.model_id))).all()
    return ModelList(models=[build_model_summary(session, model) for model in models])


@router.post("/estate/scan", response_model=ScanResult)
def scan_estate(session: SessionDependency, settings: SettingsDependency) -> ScanResult:
    """Register every model folder found in model_estate/ (no LLM)."""
    try:
        return ScanResult(models_found=register_estate(session, settings))
    except EstateScanError as error:
        raise api_error(422, error.code, error.message) from error


@router.get("/models/{model_id}", response_model=InventoryRecord)
def get_model(model_id: str, session: SessionDependency) -> InventoryRecord:
    """The inventory record of one model (stamp 1)."""
    return build_inventory_record(session, get_model_row(session, model_id))


@router.get("/metrics/factory", response_model=FactoryMetrics)
def factory_metrics(session: SessionDependency) -> FactoryMetrics:
    """Factory numbers computed from the database; nothing here is typed in by hand."""
    models = session.exec(select(ModelRow)).all()
    records = [build_inventory_record(session, model) for model in models]
    outputs = {
        kind: [latest_stage_output(session, model.model_id, kind) for model in models]
        for kind in ("documentation", "redevelopment", "validation_view", "monitoring")
    }
    documents = [document for document in outputs["documentation"] if document]
    validations = [view["result"] for view in outputs["validation_view"] if view]
    by_tier = dict.fromkeys(get_args(Tier), 0)
    by_tier.update(Counter(record.tiering.tier for record in records if record.tiering))
    by_language = dict.fromkeys(get_args(Language), 0)
    by_language.update(Counter(model.language for model in models))
    open_findings = dict.fromkeys(get_args(Severity), 0)
    open_findings.update(Counter(finding["severity"] for result in validations for finding in result["findings"]))
    runs = {run.run_id: run for run in session.exec(select(RunRow)).all()}
    stage_rows = session.exec(select(StageRunRow)).all()
    agent_seconds = sum(row.duration_seconds or 0.0 for row in stage_rows)
    review_seconds = sum(
        row.gate["review_seconds"] for row in stage_rows if row.gate and not runs[row.run_id].auto_approve
    )
    models_with_runs = {run.model_id for run in runs.values()}
    scores = [document["groundedness"]["score"] for document in documents]
    return FactoryMetrics(
        models_total=len(models),
        by_tier=by_tier,
        by_language=by_language,
        docs_outdated_at_discovery=sum(record.doc_status in ("OUTDATED", "MISSING") for record in records),
        docs_generated=len(documents),
        avg_groundedness=round(sum(scores) / len(scores), 3) if scores else None,
        parity_certificates_issued=sum(
            bool(result) and result["status"] == "PARITY_PASSED" for result in outputs["redevelopment"]
        ),
        validations_completed=sum(result["status"] == "COMPLETED" for result in validations),
        open_findings=open_findings,
        revalidation_triggers=sum(
            bool(result) and result["revalidation_triggered"] for result in outputs["monitoring"]
        ),
        avg_agent_minutes_per_model=round(agent_seconds / 60 / len(models_with_runs), 1) if models_with_runs else None,
        human_review_minutes_logged=round(review_seconds / 60, 1),
        manual_baseline_weeks_per_validation=MANUAL_BASELINE_WEEKS_PER_VALIDATION,
    )
