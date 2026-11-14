"""Shapes of the factory_core public API, section 9.3 of docs/PROJECT_CONTEXT.md: models, runs, audit, files.

The stage result shapes are in stage_result_schemas.py. Fields the discover stage fills are null
until discovery has run (see the README, Contract notes).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.schemas import (
    STAGE_NAMES,
    ContractModel,
    DocStatus,
    Language,
    ModelType,
    Rating,
    ReviewerRole,
    RunStatus,
    StageName,
    StageStatus,
    Tier,
)

ClaimStatus = Literal["VERIFIED", "UNVERIFIED", "SME_INPUT_NEEDED"]
ActorType = Literal["agent", "human", "system"]
AuditAction = Literal[
    "stage_started",
    "stage_completed",
    "stage_failed",
    "stage_skipped",
    "llm_call",
    "tool_call",
    "service_call",
    "artifact_written",
    "gate_decision",
    "revalidation_triggered",
]


class HealthStatus(ContractModel):
    """Response of GET /health."""

    status: str
    service: str
    version: str


class ErrorDetail(ContractModel):
    """Code and message of an error response."""

    code: str
    message: str


class ErrorBody(ContractModel):
    """Body of every error response."""

    error: ErrorDetail


PipelineStatus = dict[StageName, StageStatus]


class ModelSummary(ContractModel):
    """One row of GET /api/models."""

    model_id: str
    model_name: str | None
    model_type: ModelType | None
    language: Language
    algorithm: str | None
    business_line: str | None
    tier: Tier | None
    doc_status: DocStatus | None
    last_validated: str | None
    pipeline_status: PipelineStatus
    overall_rating: Rating | None
    revalidation_required: bool
    active_run_id: str | None


class ModelList(ContractModel):
    """Response of GET /api/models."""

    models: list[ModelSummary]


class ScanResult(ContractModel):
    """Response of POST /api/estate/scan."""

    models_found: list[str]


class Evidence(ContractModel):
    """File and line evidence for a claim."""

    file: str
    start_line: int
    end_line: int
    quote: str


class FieldEvidence(Evidence):
    """Evidence for one inventory field, with the verifier's result."""

    status: ClaimStatus


class InputVariable(ContractModel):
    """One model input."""

    name: str
    description: str | None = None
    transformation: str | None = None


class Tiering(ContractModel):
    """Risk tier with its scores and plain sentence rationale."""

    tier: Tier
    materiality_score: int
    complexity_score: int
    rationale: list[str]


class SourceFile(ContractModel):
    """A file of the model folder with its size and hash."""

    path: str
    kind: str
    lines: int
    sha256: str


class InventoryRecord(ContractModel):
    """Response of GET /api/models/{model_id}: stamp 1."""

    model_id: str
    model_name: str | None = None
    model_type: ModelType | None = None
    purpose: str | None = None
    business_line: str | None = None
    model_owner: str | None = None
    language: Language
    algorithm: str | None = None
    target_variable: str | None = None
    input_variables: list[InputVariable] = []
    outputs: list[str] = []
    upstream_dependencies: list[str] = []
    downstream_uses: list[str] = []
    exposure_gbp_m: float | None = None
    regulatory_use: str | None = None
    customer_facing: bool | None = None
    tiering: Tiering | None = None
    doc_status: DocStatus | None = None
    doc_last_updated: str | None = None
    last_code_change: str | None = None
    last_validated: str | None = None
    next_validation_due: str | None = None
    source_files: list[SourceFile] = []
    field_evidence: dict[str, FieldEvidence] = {}
    open_questions: list[str] = []
    pipeline_status: PipelineStatus
    revalidation_required: bool
    created_at: str
    updated_at: str


class RunCreateRequest(ContractModel):
    """Body of POST /api/models/{model_id}/runs."""

    stages: list[StageName] = Field(default_factory=lambda: list(STAGE_NAMES), min_length=1)
    auto_approve: bool = False


class RunCreated(ContractModel):
    """Response of POST /api/models/{model_id}/runs."""

    run_id: str


class GateDecisionRequest(ContractModel):
    """Body of POST /api/runs/{run_id}/gates/{stage}/decision."""

    decision: Literal["approve", "reject"]
    reviewer: str = Field(min_length=1)
    role: ReviewerRole
    comment: str | None = None


class GateRecord(ContractModel):
    """A recorded human decision at a gate."""

    decision: Literal["approve", "reject"]
    reviewer: str
    role: ReviewerRole
    comment: str | None = None
    decided_at: str
    review_seconds: int


class StageRun(ContractModel):
    """One stage of a run."""

    stage: StageName
    status: StageStatus
    started_at: str | None = None
    finished_at: str | None = None
    duration_seconds: float | None = None
    summary: str | None = None
    skip_reason: str | None = None
    error: str | None = None
    gate: GateRecord | None = None


class Run(ContractModel):
    """Response of GET /api/runs/{run_id}."""

    run_id: str
    model_id: str
    status: RunStatus
    current_stage: StageName | None
    auto_approve: bool
    stages: list[StageRun]
    started_at: str
    finished_at: str | None = None
    total_agent_seconds: float
    total_review_seconds: int


class AuditEvent(ContractModel):
    """One hash chained audit event."""

    seq: int
    ts: str
    model_id: str | None = None
    run_id: str | None = None
    stage: StageName | None = None
    actor_type: ActorType
    actor: str
    action: AuditAction
    detail: dict[str, Any] = {}
    prev_hash: str
    hash: str


class Audit(ContractModel):
    """Response of GET /api/audit."""

    chain_valid: bool
    events: list[AuditEvent]


class FactoryMetrics(ContractModel):
    """Response of GET /api/metrics/factory."""

    models_total: int
    by_tier: dict[str, int]
    by_language: dict[str, int]
    docs_outdated_at_discovery: int
    docs_generated: int
    avg_groundedness: float | None
    parity_certificates_issued: int
    validations_completed: int
    open_findings: dict[str, int]
    revalidation_triggers: int
    avg_agent_minutes_per_model: float | None
    human_review_minutes_logged: float
    manual_baseline_weeks_per_validation: list[int]


class FileView(ContractModel):
    """Response of GET /api/files."""

    path: str
    language: str
    lines: int
    content: str
