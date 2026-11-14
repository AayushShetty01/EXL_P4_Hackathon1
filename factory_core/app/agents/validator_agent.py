"""Validator agent (stamp 4 words): an independent agent that writes the validation narrative.

It has its own instructions, uses LLM_MODEL_VALIDATOR when set, and sees only the validation results,
the inventory record, the documented limitations and the parity summary, never the other agents' traces.
Every number it writes is checked by number grounding; one rewrite is allowed, after that the numbers
that still fail stay visible as unverified.
"""

import json
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.agents.number_grounding import grounding_score, source_values
from app.api_schemas import InventoryRecord
from app.audit_trail import AuditRecorder
from app.llm_client import LLMClient
from app.stage_result_schemas import Narrative, NumberGrounding, ParitySummary
from app.validation_lab_schemas import ValidationResult

SYSTEM_PROMPT = """You are an independent model validator at a UK retail bank. You did not build this model
and you have not seen how it was built or rebuilt. You write the narrative of the validation report.

Rules:
- Every number you write must be copied exactly from the validation results, the inventory record or the
  parity summary given to you. Never compute, add, subtract or estimate a number. If a point needs a number
  that is not given, describe it in words.
- The thresholds and ratings are illustrative defaults for this demonstration, not regulatory limits.
  Say so where you discuss ratings.
- The "oot" sample is a random holdout sample, not a true out of time sample. Call it the holdout sample.
- Be balanced: strengths, weaknesses, and each finding with its severity and recommendation.
- Markdown paragraphs and lists are fine; no headings.

Reply with JSON in this shape:
{"executive_summary": str, "conceptual_soundness": str, "findings_commentary": str, "conclusion": str}"""
NARRATIVE_FIELDS = ("executive_summary", "conceptual_soundness", "findings_commentary", "conclusion")


class NarrativeReply(BaseModel):
    """The JSON the validator agent must return."""

    model_config = ConfigDict(extra="ignore")

    executive_summary: str
    conceptual_soundness: str
    findings_commentary: str
    conclusion: str


@dataclass(frozen=True)
class ValidatorOutcome:
    """The checked narrative, its grounding and the model that wrote it."""

    narrative: Narrative
    number_grounding: NumberGrounding
    validator_model: str


def user_prompt(
    result: ValidationResult, record: InventoryRecord, limitations: str | None, parity: ParitySummary | None
) -> str:
    """The validator's input: results without chart data, the record, the limitations and the parity facts."""
    results = result.model_dump(mode="json", exclude={"series", "charts"})
    inventory = record.model_dump(mode="json", exclude={"source_files", "field_evidence", "pipeline_status"})
    return (
        f"Validation results:\n{json.dumps(results, indent=1, sort_keys=True)}\n\n"
        f"Inventory record:\n{json.dumps(inventory, indent=1, sort_keys=True)}\n\n"
        f"Documented limitations:\n{limitations or 'No documentation is available.'}\n\n"
        f"Parity summary:\n{json.dumps(parity.model_dump(mode='json') if parity else None, sort_keys=True)}"
    )


def narrative_text(reply: NarrativeReply) -> str:
    """All four narrative parts as one text, for number checking."""
    return "\n\n".join(getattr(reply, name) for name in NARRATIVE_FIELDS)


def write_narrative(
    llm: LLMClient,
    recorder: AuditRecorder,
    *,
    result: ValidationResult,
    record: InventoryRecord,
    limitations: str | None,
    parity: ParitySummary | None,
    validator_model: str | None,
) -> ValidatorOutcome:
    """Write the narrative, check its numbers, and rewrite once if any number is not in the results."""
    sources: list[Any] = [result.model_dump(mode="json"), record.model_dump(mode="json")]
    if parity:
        sources.append(parity.model_dump(mode="json"))
    values = source_values(*sources)
    prompt = user_prompt(result, record, limitations, parity)
    model = validator_model or None
    response = llm.complete(
        SYSTEM_PROMPT, prompt, json_mode=True, step="validation_narrative", model=model, schema=NarrativeReply
    )
    grounding, unverified = grounding_score(narrative_text(response.parsed), values)
    recorder.tool_call("number_grounding", grounding.model_dump() | {"unverified": unverified, "attempt": 1})
    if unverified:
        rewrite = (
            f"{prompt}\n\nThese numbers in your previous narrative are not in the results: {', '.join(unverified)}.\n"
            "Rewrite the narrative so that every number is copied exactly from the results above."
        )
        response = llm.complete(
            SYSTEM_PROMPT,
            rewrite,
            json_mode=True,
            step="validation_narrative:rewrite",
            model=model,
            schema=NarrativeReply,
        )
        grounding, unverified = grounding_score(narrative_text(response.parsed), values)
        recorder.tool_call("number_grounding", grounding.model_dump() | {"unverified": unverified, "attempt": 2})
    reply: NarrativeReply = response.parsed
    narrative = Narrative(**reply.model_dump(), unverified_numbers=unverified)
    return ValidatorOutcome(narrative=narrative, number_grounding=grounding, validator_model=response.model)
