"""Document drift: where the old model document no longer matches the code.

The LLM compares the old document (numbered lines) with the verified claims. Both quotes of every
difference are checked by the evidence verifier: the old document quote must be in a document file and
the code quote in a code file. Differences that fail a check stay in the list, marked UNVERIFIED.
"""

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.agents.evidence_verifier import EvidenceReply, verify_evidence
from app.agents.source_context import numbered_files, source_paths
from app.audit_trail import AuditRecorder
from app.config import Settings
from app.database import ModelRow
from app.llm_client import LLMClient
from app.stage_result_schemas import DocumentSection, DriftItem

SYSTEM_PROMPT = """You compare the old model document of a UK bank with what the model code does today.

Rules:
- Report only real differences: something the old document states that the code contradicts, or
  something important in the code that the document describes differently or leaves out.
- Each difference needs two pieces of evidence, each with the file path exactly as in the file header,
  the first and last line number, and a short quote copied exactly from those lines:
  legacy_evidence from the old document, and code_evidence copied from the evidence of a verified claim.
- severity: HIGH when the difference changes decisions, scores or risk (for example a cutoff, a variable
  or a coefficient), MEDIUM when it changes how the model is understood or used, LOW otherwise.
- Never invent a difference. An empty list is a valid answer.

Reply with JSON in this shape:
{"differences": [{"topic": str, "severity": "HIGH"|"MEDIUM"|"LOW", "legacy_doc_says": str, "code_says": str,
  "legacy_evidence": {"file": str, "start_line": int, "end_line": int, "quote": str},
  "code_evidence": {"file": str, "start_line": int, "end_line": int, "quote": str}}]}"""


class DifferenceReply(BaseModel):
    """One difference as the agent returns it."""

    model_config = ConfigDict(extra="ignore")

    topic: str
    severity: Literal["HIGH", "MEDIUM", "LOW"]
    legacy_doc_says: str
    code_says: str
    legacy_evidence: EvidenceReply | None = None
    code_evidence: EvidenceReply | None = None


class DriftReply(BaseModel):
    """The JSON the drift agent must return."""

    model_config = ConfigDict(extra="ignore")

    differences: list[DifferenceReply] = []


def verified_claims_text(sections: list[DocumentSection]) -> str:
    """The verified claims with their evidence, as compact JSON lines."""
    lines = [
        json.dumps({"claim": claim.text, "evidence": [item.model_dump() for item in claim.evidence]})
        for section in sections
        for claim in section.claims
        if claim.status == "VERIFIED"
    ]
    return "\n".join(lines) or "(no verified claims)"


def check_side(settings: Settings, folder: str, evidence: EvidenceReply | None, allowed_files: list[str]):
    """Verify one side of a difference; it must cite one of the allowed files."""
    if evidence is None or evidence.file not in allowed_files:
        return None, "UNVERIFIED"
    check = verify_evidence(settings, evidence, allowed_folder=folder)
    return check.evidence, check.status


def find_drift(
    settings: Settings,
    model: ModelRow,
    sections: list[DocumentSection],
    llm: LLMClient,
    recorder: AuditRecorder,
) -> list[DriftItem]:
    """Ask for the differences and verify both sides of each one; no old document means no drift."""
    doc_files = source_paths(model.registration, "doc")
    code_files = source_paths(model.registration, "code")
    if not doc_files:
        return []
    response = llm.complete(
        SYSTEM_PROMPT,
        f"Old model document:\n{numbered_files(settings, doc_files)}\n\n"
        f"Verified claims about the code:\n{verified_claims_text(sections)}",
        json_mode=True,
        step="document_drift",
        schema=DriftReply,
    )
    items: list[DriftItem] = []
    for number, difference in enumerate(response.parsed.differences, start=1):
        legacy, legacy_status = check_side(settings, model.folder, difference.legacy_evidence, doc_files)
        code, code_status = check_side(settings, model.folder, difference.code_evidence, code_files)
        items.append(
            DriftItem(
                id=f"D{number:03d}",
                severity=difference.severity,
                topic=difference.topic,
                legacy_doc_says=difference.legacy_doc_says,
                code_says=difference.code_says,
                legacy_evidence=legacy,
                code_evidence=code,
                status="VERIFIED" if legacy_status == code_status == "VERIFIED" else "UNVERIFIED",
            )
        )
    verified = sum(item.status == "VERIFIED" for item in items)
    recorder.tool_call("evidence_verifier", {"drift_items": len(items), "drift_items_verified": verified})
    return items
