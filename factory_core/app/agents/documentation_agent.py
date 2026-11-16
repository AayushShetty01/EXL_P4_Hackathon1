"""Documentation agent (stamp 2): writes the ten section model document, one LLM call per section.

Every factual sentence is a claim with file and line evidence that the evidence verifier checks.
Claims without evidence are SME_INPUT_NEEDED. Groundedness is computed by code, never by the LLM.
"""

import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.agents.evidence_verifier import EvidenceReply, verify_evidence
from app.agents.source_context import dictionary_path, numbered_files, prompt_json, source_paths
from app.api_schemas import InventoryRecord
from app.audit_trail import AuditRecorder
from app.config import Settings
from app.database import ModelRow
from app.llm_client import LLMClient
from app.stage_result_schemas import Claim, DocumentSection, Groundedness, SectionId

SECTIONS: tuple[tuple[SectionId, str, str], ...] = (
    ("overview", "Overview", "What the model is, what it predicts and where it is used."),
    ("intended_use", "Intended use", "The decisions it supports, its users, and uses it must not be put to."),
    (
        "data_and_variables",
        "Data and variables",
        "Data sources, development and holdout samples, the target definition, the inputs and their transformations.",
    ),
    ("methodology", "Methodology", "The modelling approach, the estimation procedure and the variable transformation."),
    (
        "model_specification",
        "Model specification",
        "The final model exactly as coded: variables, coefficients, bin edges, score scaling and the decision cutoff.",
    ),
    ("assumptions", "Assumptions", "Statistical and business assumptions the model relies on."),
    (
        "limitations",
        "Limitations",
        "Known weaknesses. When the data has no time dimension, say that the holdout is a random holdout, "
        "not a true out of time sample.",
    ),
    (
        "implementation_and_controls",
        "Implementation and controls",
        "How the model runs: the programs and their order, inputs and outputs, and the controls visible in the code.",
    ),
    (
        "monitoring_plan",
        "Monitoring plan",
        "What to monitor (stability, performance, overrides) and what should trigger revalidation.",
    ),
    (
        "change_log",
        "Change log",
        "Changes visible in the files. Ask for SME input on the change history the files cannot show.",
    ),
)
SYSTEM_PROMPT = """You are the documentation agent of the model risk team of a UK retail bank.
You write one section of the current model document of a legacy model.

Rules:
- Every factual sentence is a claim. Give each claim evidence: the file path exactly as in the file
  header, the first and last line number, and a short quote copied exactly from those lines.
- Put the marker {{claim:N}} right after the sentence of claim N (N counts from 1 in your claims list).
- Use only numbers that appear in the files, such as coefficients, bin edges and cutoffs. Never compute,
  round or estimate a number.
- When the files cannot answer something this section needs, write "SME input needed:" followed by the
  question, and add that sentence as a claim with an empty evidence list.
- State limitations honestly. Describe what the code does, not what an old document says.
- Plain English for a model risk reviewer. Markdown lists and tables are fine; no headings.

Reply with JSON in this shape:
{"markdown": str, "claims": [{"text": str,
  "evidence": [{"file": str, "start_line": int, "end_line": int, "quote": str}]}]}"""
PLACEHOLDER = re.compile(r"\{\{claim:(\d+)\}\}")
SME_PREFIX = "SME input needed:"


class ClaimReply(BaseModel):
    """One claim as the agent returns it."""

    model_config = ConfigDict(extra="ignore")

    text: str
    evidence: list[EvidenceReply] = []


class SectionReply(BaseModel):
    """The JSON the documentation agent must return for one section."""

    model_config = ConfigDict(extra="ignore")

    markdown: str
    claims: list[ClaimReply] = []


@dataclass(frozen=True)
class DocumentationDraft:
    """The checked sections, their groundedness and the model id that wrote them."""

    sections: list[DocumentSection]
    groundedness: Groundedness
    generated_by_model: str


def record_context(record: InventoryRecord) -> str:
    """The approved inventory record as JSON, without the source file list and the run specific fields."""
    return prompt_json(record.model_dump(mode="json"), frozenset({"source_files"}))


def section_prompt(section_id: str, title: str, guidance: str, record_text: str, files_text: str) -> str:
    """The user prompt of one section."""
    return (
        f"Section to write: {title} ({section_id})\nWhat this section covers: {guidance}\n\n"
        f"Approved inventory record:\n{record_text}\n\nFiles:\n{files_text}"
    )


def check_claims(settings: Settings, folder: str, reply: SectionReply, first_number: int) -> tuple[str, list[Claim]]:
    """Verify every claim, give it an id and put its marker [Cnnn] into the markdown."""
    markdown = reply.markdown
    claims: list[Claim] = []
    for index, claim in enumerate(reply.claims, start=1):
        claim_id = f"C{first_number + index - 1:03d}"
        if claim.evidence:
            checks = [verify_evidence(settings, evidence, allowed_folder=folder) for evidence in claim.evidence]
            status = "VERIFIED" if all(check.status == "VERIFIED" for check in checks) else "UNVERIFIED"
            evidence = [check.evidence for check in checks]
        else:
            status, evidence = "SME_INPUT_NEEDED", []
        claims.append(Claim(id=claim_id, text=claim.text, status=status, evidence=evidence))
        marker = f"{{{{claim:{index}}}}}"
        if marker in markdown:
            markdown = markdown.replace(marker, f" [{claim_id}]")
        elif claim.text in markdown:
            markdown = markdown.replace(claim.text, f"{claim.text} [{claim_id}]", 1)
        else:
            markdown = f"{markdown.rstrip()}\n\n{claim.text} [{claim_id}]"
    markdown = PLACEHOLDER.sub("", markdown).replace("  [C", " [C")
    return markdown.strip(), claims


def compute_groundedness(sections: list[DocumentSection]) -> Groundedness:
    """Claim counts by status and the share of claims verified against the files."""
    claims = [claim for section in sections for claim in section.claims]
    verified = sum(claim.status == "VERIFIED" for claim in claims)
    return Groundedness(
        claims_total=len(claims),
        claims_verified=verified,
        claims_unverified=sum(claim.status == "UNVERIFIED" for claim in claims),
        claims_sme_input_needed=sum(claim.status == "SME_INPUT_NEEDED" for claim in claims),
        score=round(verified / len(claims), 3) if claims else 0.0,
    )


def write_documentation(
    settings: Settings, model: ModelRow, record: InventoryRecord, llm: LLMClient, recorder: AuditRecorder
) -> DocumentationDraft:
    """Write and check all ten sections."""
    paths = source_paths(model.registration, "code")
    dictionary = dictionary_path(model.registration, model.folder)
    files_text = numbered_files(settings, paths + ([dictionary] if dictionary else []))
    record_text = record_context(record)
    sections: list[DocumentSection] = []
    models_used: list[str] = []
    for section_id, title, guidance in SECTIONS:
        response = llm.complete(
            SYSTEM_PROMPT,
            section_prompt(section_id, title, guidance, record_text, files_text),
            json_mode=True,
            step=f"section:{section_id}",
            schema=SectionReply,
        )
        models_used.append(response.model)
        first_number = sum(len(section.claims) for section in sections) + 1
        markdown, claims = check_claims(settings, model.folder, response.parsed, first_number)
        sections.append(DocumentSection(id=section_id, title=title, markdown=markdown, claims=claims))
    groundedness = compute_groundedness(sections)
    recorder.tool_call("evidence_verifier", groundedness.model_dump())
    return DocumentationDraft(sections, groundedness, models_used[0] if models_used else "")


def render_markdown(documentation: Any, model_name: str | None, generated_on: str) -> str:
    """The model document as one Markdown file: sections, claim evidence and the drift list."""
    groundedness = documentation.groundedness
    lines = [
        f"# {model_name or documentation.model_id} ({documentation.model_id}): model document",
        "",
        f"Draft for expert review, written on {generated_on} by the documentation agent "
        f"({documentation.generated_by_model}). {groundedness.claims_verified} of {groundedness.claims_total} "
        "claims are verified against the model files by code.",
    ]
    for section in documentation.sections:
        lines += ["", f"## {section.title}", "", section.markdown]
        if section.claims:
            lines += ["", "| Claim | Status | Evidence |", "|---|---|---|"]
            for claim in section.claims:
                cited = "; ".join(f"`{e.file}` lines {e.start_line}-{e.end_line}" for e in claim.evidence) or "none"
                lines.append(f"| {claim.id} | {claim.status} | {cited} |")
    lines += ["", "## Differences against the old document", ""]
    if not documentation.doc_drift:
        lines.append("No differences were reported.")
    else:
        lines += ["| Id | Severity | Topic | Old document says | Code says | Status |", "|---|---|---|---|---|---|"]
        for item in documentation.doc_drift:
            cells = [item.id, item.severity, item.topic, item.legacy_doc_says, item.code_says, item.status]
            lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"
