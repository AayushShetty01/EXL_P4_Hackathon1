"""Shared enumerations and base classes for every contract shape, plus the estate manifest.

Service shapes: redev_engine_schemas.py (section 9.1), validation_lab_schemas.py (section 9.2),
api_schemas.py (section 9.3). Enumerations follow section 8 of docs/PROJECT_CONTEXT.md.
"""

from __future__ import annotations

from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict

StageName = Literal["discover", "document", "redevelop", "validate", "monitor"]
StageStatus = Literal["PENDING", "RUNNING", "AWAITING_REVIEW", "APPROVED", "REJECTED", "FAILED", "SKIPPED"]
RunStatus = Literal["RUNNING", "AWAITING_REVIEW", "COMPLETED", "REJECTED", "FAILED"]
ModelType = Literal["credit_pd", "fraud", "pricing", "other"]
Language = Literal["SAS", "R", "Python"]
Tier = Literal["Tier 1", "Tier 2", "Tier 3"]
DocStatus = Literal["MISSING", "OUTDATED", "CURRENT"]
Rating = Literal["GREEN", "AMBER", "RED"]
Severity = Literal["HIGH", "MEDIUM", "LOW"]
ReviewerRole = Literal["developer", "validator", "owner"]
RedevelopStatus = Literal["PARITY_PASSED", "PARITY_FAILED", "TRANSLATED_NO_GOLDEN", "ERROR"]
ParityLevelStatus = Literal["PASSED", "FAILED", "NOT_APPLICABLE"]

STAGE_NAMES: tuple[str, ...] = get_args(StageName)


class ContractModel(BaseModel):
    """Base for shapes factory_core owns: unknown fields are rejected so the contract cannot drift."""

    model_config = ConfigDict(extra="forbid")


class ServiceModel(BaseModel):
    """Base for shapes another service owns: optional contract additions are kept and passed on."""

    model_config = ConfigDict(extra="allow")


# ---- Section 7: model manifest (owned by model_estate) ----


class ManifestData(ServiceModel):
    """Data pointers in a manifest, relative to the model folder."""

    dev_path: str
    oot_path: str
    dictionary_path: str | None = None
    id_col: str
    target_col: str
    protected_cols: list[str] = []


class ManifestGolden(ServiceModel):
    """Legacy output pointers in a manifest, relative to the model folder."""

    scored_dev_path: str
    scored_oot_path: str
    coefficients_path: str | None = None
    produced_by: str | None = None
    produced_on: str | None = None


class EstateManifest(ServiceModel):
    """The manifest.json of one model folder."""

    model_id: str
    folder: str
    language: Language
    code_files: list[str]
    doc_files: list[str] = []
    data: ManifestData | None = None
    golden: ManifestGolden | None = None
    redevelop: bool
