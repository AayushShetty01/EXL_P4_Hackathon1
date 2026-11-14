"""Shapes of the stage result endpoints: documentation, validation view and compliance (section 9.3).

Also holds the validation_lab POST /report request (section 9.2), because factory_core builds it
from the inventory record and the validator narrative.
"""

from __future__ import annotations

from typing import Literal

from app.api_schemas import ClaimStatus, Evidence, InventoryRecord
from app.schemas import ContractModel, Severity
from app.validation_lab_schemas import ValidationResult

ComplianceStatus = Literal["MET", "PARTIAL", "NOT_MET", "OUT_OF_SCOPE"]
SectionId = Literal[
    "overview",
    "intended_use",
    "data_and_variables",
    "methodology",
    "model_specification",
    "assumptions",
    "limitations",
    "implementation_and_controls",
    "monitoring_plan",
    "change_log",
]


class Groundedness(ContractModel):
    """Share of documentation claims verified against the code."""

    claims_total: int
    claims_verified: int
    claims_unverified: int
    claims_sme_input_needed: int
    score: float


class Claim(ContractModel):
    """One factual sentence of the documentation and its evidence."""

    id: str
    text: str
    status: ClaimStatus
    evidence: list[Evidence]


class DocumentSection(ContractModel):
    """One of the ten documentation sections."""

    id: SectionId
    title: str
    markdown: str
    claims: list[Claim]


class DriftItem(ContractModel):
    """A difference between the old model document and the code."""

    id: str
    severity: Severity
    topic: str
    legacy_doc_says: str
    code_says: str
    legacy_evidence: Evidence | None = None
    code_evidence: Evidence | None = None
    status: Literal["VERIFIED", "UNVERIFIED"]


class Documentation(ContractModel):
    """Response of GET /api/models/{model_id}/documentation: stamp 2."""

    model_id: str
    generated_at: str
    generated_by_model: str
    groundedness: Groundedness
    sections: list[DocumentSection]
    doc_drift: list[DriftItem]
    markdown_path: str


class Narrative(ContractModel):
    """Validation narrative written by the validator agent."""

    executive_summary: str
    conceptual_soundness: str
    findings_commentary: str
    conclusion: str
    unverified_numbers: list[str] = []


class NumberGrounding(ContractModel):
    """Share of narrative numbers found in the computed results."""

    numbers_in_narrative: int
    numbers_verified: int
    score: float


class ReportPaths(ContractModel):
    """Rendered validation report files."""

    html_path: str | None = None
    docx_path: str | None = None


class ValidationView(ContractModel):
    """Response of GET /api/models/{model_id}/validation: stamp 4."""

    model_id: str
    result: ValidationResult
    narrative: Narrative
    number_grounding: NumberGrounding
    validator_agent_model: str | None
    report: ReportPaths


class ParitySummary(ContractModel):
    """Parity facts passed to the validation report."""

    status: str
    records_compared: int
    max_abs_diff_pd: float | None = None
    decision_match_rate: float | None = None
    certificate_md_path: str | None = None


class SignOff(ContractModel):
    """Sign off block of the validation report."""

    validator_agent_model: str | None = None
    human_validator: str | None = None
    signed_at: str | None = None


class ReportRequest(ContractModel):
    """Body of validation_lab POST /report."""

    run_id: str
    model_id: str
    validation_result_path: str
    inventory_record: InventoryRecord
    parity_summary: ParitySummary | None = None
    narrative: Narrative
    sign_off: SignOff
    formats: list[Literal["html", "docx"]] = ["html"]


class ComplianceItem(ContractModel):
    """One SS1/23 expectation and how this model meets it."""

    id: str
    expectation: str
    status: ComplianceStatus
    evidence_path: str | None = None
    note: str | None = None


class CompliancePrinciple(ContractModel):
    """One of the five SS1/23 principles."""

    principle: Literal["P1", "P2", "P3", "P4", "P5"]
    title: str
    items: list[ComplianceItem]


class ComplianceCoverage(ContractModel):
    """Item counts by status."""

    met: int
    partial: int
    not_met: int
    out_of_scope: int


class Compliance(ContractModel):
    """Response of GET /api/models/{model_id}/compliance."""

    model_id: str
    disclaimer: str
    principles: list[CompliancePrinciple]
    coverage: ComplianceCoverage
