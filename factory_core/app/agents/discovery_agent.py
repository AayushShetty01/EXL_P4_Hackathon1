"""Discovery agent (stamp 1): builds the inventory record of one model.

Static pass without LLM: languages and code signals found with regular expressions. LLM pass: the
descriptive fields, each with file and line evidence that the evidence verifier checks. Owners, dates
and exposure come from the register only, and the tier comes from the deterministic tiering policy.
"""

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import PurePosixPath
from typing import Any, get_args

from pydantic import BaseModel, ConfigDict

from app.agents.evidence_verifier import EvidenceReply, verify_evidence
from app.agents.source_context import numbered_files, source_paths
from app.api_schemas import FieldEvidence, InputVariable, InventoryRecord
from app.audit_trail import AuditRecorder
from app.config import Settings
from app.database import ModelRow, utc_timestamp
from app.estate_scanner import read_text_file
from app.llm_client import LLMClient
from app.schemas import ModelType
from app.tiering_policy import document_status, tier_model

ACTOR = "discovery_agent"
MAX_SIGNALS_PER_KIND = 30
LANGUAGE_BY_SUFFIX = {".sas": "SAS", ".r": "R", ".py": "Python"}
SIGNAL_PATTERNS: dict[str, dict[str, str]] = {
    "SAS": {
        "procedures": r"\bproc\s+(\w+)",
        "model_statements": r"^\s*model\s+([^;]+);",
        "macro_variables": r"%let\s+(\w+)",
    },
    "R": {
        "glm_formulas": r"\bglm\s*\(\s*([^,]+)",
        "libraries": r"\blibrary\s*\(\s*['\"]?(\w+)",
        "model_functions": r"\b(lm|glm|gbm|randomForest|predict)\s*\(",
    },
    "Python": {
        "imports": r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))",
        "fit_calls": r"(\w+)\.fit\(",
    },
}
SYSTEM_PROMPT = """You are the discovery agent of the model risk team of a UK retail bank.
You read the legacy source files of one model and fill in its inventory record.

Rules:
- Use only what the files show. Every field you fill needs evidence: the file path exactly as given in
  the file header, the first and last line number, and a short quote copied exactly from those lines.
- When the files do not answer a field, return null (or an empty list) and add an open question for the
  model owner instead.
- Never state owners, dates, exposure amounts or approvals. Those come from the bank's register.
- The model document may be outdated. When the document and the code disagree, describe the code.
- model_type is one of: credit_pd, fraud, pricing, other.
- input_variables are the variables the model uses as inputs, each with a short description and its
  transformation (for example "WoE bins"). Protected attributes such as sex or age band are inputs only
  if the code really uses them in the model.
- outputs are what the model produces (for example pd, score, decision).

Reply with JSON in this shape:
{"model_name": str|null, "model_type": str|null, "purpose": str|null, "algorithm": str|null,
 "target_variable": str|null,
 "input_variables": [{"name": str, "description": str|null, "transformation": str|null}],
 "outputs": [str], "upstream_dependencies": [str], "downstream_uses": [str], "open_questions": [str],
 "evidence": {"<field name>": {"file": str, "start_line": int, "end_line": int, "quote": str}}}"""
EVIDENCED_FIELDS = (
    "model_name",
    "model_type",
    "purpose",
    "algorithm",
    "target_variable",
    "input_variables",
    "outputs",
    "upstream_dependencies",
    "downstream_uses",
)


class InputVariableReply(BaseModel):
    """One input variable as the agent returns it."""

    model_config = ConfigDict(extra="ignore")

    name: str
    description: str | None = None
    transformation: str | None = None


class DiscoveryReply(BaseModel):
    """The JSON the discovery agent must return."""

    model_config = ConfigDict(extra="ignore")

    model_name: str | None = None
    model_type: str | None = None
    purpose: str | None = None
    algorithm: str | None = None
    target_variable: str | None = None
    input_variables: list[InputVariableReply] = []
    outputs: list[str] = []
    upstream_dependencies: list[str] = []
    downstream_uses: list[str] = []
    open_questions: list[str] = []
    evidence: dict[str, EvidenceReply | None] = {}


@dataclass(frozen=True)
class DiscoveryOutcome:
    """The inventory record and the stage summary built from it by code."""

    record: InventoryRecord
    summary: str


def static_signals(settings: Settings, code_paths: list[str]) -> dict[str, Any]:
    """Languages by file extension and code signals found with regular expressions."""
    languages = sorted({LANGUAGE_BY_SUFFIX.get(PurePosixPath(path).suffix.lower(), "other") for path in code_paths})
    signals: dict[str, list[str]] = {}
    for path in code_paths:
        language = LANGUAGE_BY_SUFFIX.get(PurePosixPath(path).suffix.lower())
        content = read_text_file(settings, path).content
        for kind, pattern in SIGNAL_PATTERNS.get(language or "", {}).items():
            found = signals.setdefault(kind, [])
            for match in re.finditer(pattern, content, flags=re.IGNORECASE | re.MULTILINE):
                value = " ".join(next(group for group in match.groups() if group).split())
                if value not in found and len(found) < MAX_SIGNALS_PER_KIND:
                    found.append(value)
    return {"detected_languages": languages, **signals}


def build_user_prompt(settings: Settings, model: ModelRow, signals: dict[str, Any]) -> str:
    """The user prompt: register row, static signals and the numbered source files."""
    register = model.registration.get("register_row") or {}
    paths = source_paths(model.registration, "code") + source_paths(model.registration, "doc")
    return (
        f"Model id: {model.model_id}\nModel folder: {model.folder}\nLanguage in the manifest: {model.language}\n\n"
        f"Register row (context only):\n{json.dumps(register, sort_keys=True)}\n\n"
        f"Signals found by code:\n{json.dumps(signals, sort_keys=True)}\n\n"
        f"Source files:\n{numbered_files(settings, paths)}"
    )


def verify_fields(settings: Settings, model: ModelRow, reply: DiscoveryReply) -> dict[str, FieldEvidence]:
    """Verify the evidence of every filled field; fields without evidence get none."""
    checked: dict[str, FieldEvidence] = {}
    for field_name in EVIDENCED_FIELDS:
        evidence = reply.evidence.get(field_name)
        if evidence is None or getattr(reply, field_name) in (None, []):
            continue
        check = verify_evidence(settings, evidence, allowed_folder=model.folder)
        checked[field_name] = FieldEvidence(**check.evidence.model_dump(), status=check.status)
    return checked


def run_discovery(
    settings: Settings,
    model: ModelRow,
    llm: LLMClient,
    recorder: AuditRecorder,
    *,
    pipeline_status: dict[str, str],
    previous_record: dict[str, Any] | None,
    today: date,
) -> DiscoveryOutcome:
    """Run the static pass, the LLM pass, evidence verification, tiering and document status."""
    code_paths = source_paths(model.registration, "code")
    signals = static_signals(settings, code_paths)
    recorder.tool_call("static_signals", {"files": len(code_paths), "signal_kinds": sorted(signals)})
    response = llm.complete(
        SYSTEM_PROMPT,
        build_user_prompt(settings, model, signals),
        json_mode=True,
        step="discover",
        schema=DiscoveryReply,
    )
    reply: DiscoveryReply = response.parsed
    field_evidence = verify_fields(settings, model, reply)
    verified = sum(evidence.status == "VERIFIED" for evidence in field_evidence.values())
    recorder.tool_call("evidence_verifier", {"fields_checked": len(field_evidence), "verified": verified})
    register = model.registration.get("register_row") or {}
    questions = list(reply.open_questions)
    if not register:
        questions.append("The model is not in the estate register, so owner, exposure and dates are unknown.")
    if model.language not in signals["detected_languages"]:
        questions.append(f"The manifest says {model.language} but the code files are {signals['detected_languages']}.")
    unsupported = [
        name for name in EVIDENCED_FIELDS if getattr(reply, name) not in (None, []) and name not in field_evidence
    ]
    questions += [f"No evidence was given for {name}; please confirm it." for name in unsupported]
    outcome = tier_model(
        exposure_gbp_m=register.get("exposure_gbp_m"),
        regulatory_use=register.get("regulatory_use"),
        customer_facing=register.get("customer_facing"),
        algorithm=reply.algorithm,
        input_count=len(reply.input_variables),
        last_validated=register.get("last_validated"),
    )
    doc_status, doc_questions = document_status(
        bool(source_paths(model.registration, "doc")),
        register.get("doc_last_updated"),
        register.get("last_code_change"),
        today,
    )
    recorder.tool_call(
        "tiering_policy",
        {"tier": outcome.tiering.tier, "materiality": outcome.tiering.materiality_score, "doc_status": doc_status},
    )
    now = utc_timestamp()
    model_type = (
        reply.model_type if reply.model_type in get_args(ModelType) else ("other" if reply.model_type else None)
    )
    record = InventoryRecord(
        model_id=model.model_id,
        model_name=register.get("model_name") or reply.model_name,
        model_type=model_type,
        purpose=reply.purpose,
        business_line=register.get("business_line"),
        model_owner=register.get("model_owner"),
        language=model.language,
        algorithm=reply.algorithm,
        target_variable=reply.target_variable,
        input_variables=[InputVariable(**variable.model_dump()) for variable in reply.input_variables],
        outputs=reply.outputs,
        upstream_dependencies=reply.upstream_dependencies,
        downstream_uses=reply.downstream_uses,
        exposure_gbp_m=register.get("exposure_gbp_m"),
        regulatory_use=register.get("regulatory_use"),
        customer_facing=register.get("customer_facing"),
        tiering=outcome.tiering,
        doc_status=doc_status,
        doc_last_updated=register.get("doc_last_updated"),
        last_code_change=register.get("last_code_change"),
        last_validated=register.get("last_validated"),
        next_validation_due=outcome.next_validation_due,
        source_files=model.registration.get("source_files", []),
        field_evidence=field_evidence,
        open_questions=list(dict.fromkeys(questions + outcome.open_questions + doc_questions)),
        pipeline_status=pipeline_status,
        revalidation_required=model.revalidation_required,
        created_at=(previous_record or {}).get("created_at", now),
        updated_at=now,
    )
    summary = (
        f"Inventory record created. {outcome.tiering.tier}. "
        f"{verified} of {len(field_evidence)} field evidence quotes verified. "
        f"{len(record.open_questions)} open questions."
    )
    return DiscoveryOutcome(record=record, summary=summary)
