"""The checks of the SS1/23 compliance matrix: each looks at one model's stored outputs and returns a verdict.

A verdict is (status, evidence_path, note) with status MET, PARTIAL, NOT_MET or OUT_OF_SCOPE.
The table that lists the checks under the five principles is in compliance_matrix.py.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

Verdict = tuple[str, str | None, str | None]
INVENTORY_RECORD = ("discover", "inventory_record.json")
MODEL_DOCUMENT = ("document", "model_document.json")
NOT_VALIDATED = "Not validated yet"


@dataclass
class ModelEvidence:
    """Everything the checks look at for one model."""

    model_id: str
    language: str
    inventory: dict[str, Any] | None
    documentation: dict[str, Any] | None
    redevelopment: dict[str, Any] | None
    validation: dict[str, Any] | None
    monitoring: dict[str, Any] | None
    approvals: dict[str, list[str]] = field(default_factory=dict)
    gate_events: int = 0
    chain_valid: bool = True

    def path(self, folder: str, name: str) -> str:
        """Artifact path of this model."""
        return f"artifacts/{self.model_id}/{folder}/{name}"

    def section_has_claims(self, section_id: str) -> bool:
        """True when a documentation section has at least one verified claim."""
        sections = (self.documentation or {}).get("sections", [])
        return any(
            section["id"] == section_id and any(claim["status"] == "VERIFIED" for claim in section["claims"])
            for section in sections
        )


def inventory_recorded(e: ModelEvidence) -> Verdict:
    """P1: the inventory record exists and its gate is approved."""
    path = e.path(*INVENTORY_RECORD)
    if e.inventory and "discover" in e.approvals:
        return "MET", path, None
    return (
        ("PARTIAL", path, "Waiting for the discover gate") if e.inventory else ("NOT_MET", None, "Not discovered yet")
    )


def tier_assigned(e: ModelEvidence) -> Verdict:
    """P1: a tier with rationale."""
    tiering = (e.inventory or {}).get("tiering")
    return ("MET", e.path(*INVENTORY_RECORD), None) if tiering else ("NOT_MET", None, "No tier yet")


def dependencies_recorded(e: ModelEvidence) -> Verdict:
    """P1: upstream and downstream dependencies."""
    if not e.inventory:
        return "NOT_MET", None, "Not discovered yet"
    if e.inventory.get("upstream_dependencies") or e.inventory.get("downstream_uses"):
        return "MET", e.path(*INVENTORY_RECORD), None
    return (
        "PARTIAL",
        e.path(*INVENTORY_RECORD),
        "No dependencies found in the files; confirm with the owner",
    )


def owner_recorded(e: ModelEvidence) -> Verdict:
    """P2: an accountable owner (a role title only is partial)."""
    if not (e.inventory or {}).get("model_owner"):
        return "NOT_MET", None, "No owner in the register"
    return "PARTIAL", e.path(*INVENTORY_RECORD), "Owner recorded as a role title only"


def gates_audited(e: ModelEvidence) -> Verdict:
    """P2: gate approvals in an intact audit trail."""
    if e.gate_events and e.chain_valid:
        return "MET", None, f"{e.gate_events} gate decisions in the audit trail"
    if e.gate_events:
        return "PARTIAL", None, "Gate decisions recorded but the audit chain does not verify"
    return "NOT_MET", None, "No gate decision recorded yet"


def out_of_scope(note: str) -> Callable[[ModelEvidence], Verdict]:
    """An organisational control that a prototype cannot evidence."""

    def check(e: ModelEvidence) -> Verdict:
        """Always OUT_OF_SCOPE, with the reason."""
        return "OUT_OF_SCOPE", None, note

    return check


def documented(section_ids: tuple[str, ...]) -> Callable[[ModelEvidence], Verdict]:
    """P3: the given documentation sections hold verified claims."""

    def check(e: ModelEvidence) -> Verdict:
        """MET when every listed section has a verified claim."""
        if not e.documentation:
            return "NOT_MET", None, "Not documented yet"
        path = e.path(*MODEL_DOCUMENT)
        if all(e.section_has_claims(section_id) for section_id in section_ids):
            return "MET", path, None
        return "PARTIAL", path, "Some sections have no verified claim"

    return check


def development_tested(e: ModelEvidence) -> Verdict:
    """P3: unit tests and parity of the rebuild."""
    status = (e.redevelopment or {}).get("status")
    certificate = ((e.redevelopment or {}).get("parity") or {}).get("certificate_md_path")
    if status == "PARITY_PASSED":
        return "MET", certificate, None
    if status == "TRANSLATED_NO_GOLDEN":
        return "PARTIAL", None, "Unit tested, but no legacy outputs to prove parity"
    if e.language == "Python" and not e.redevelopment:
        return "PARTIAL", None, "Python model, not redeveloped; development tests are outside the prototype"
    return "NOT_MET", None, f"Redevelopment status {status}" if status else "Not redeveloped"


def documentation_current(e: ModelEvidence) -> Verdict:
    """P3: documentation generated and drift against the old document listed."""
    if not e.documentation:
        return "NOT_MET", None, "Not documented yet"
    drift = len(e.documentation.get("doc_drift", []))
    return "MET", e.path(*MODEL_DOCUMENT), f"{drift} differences against the old document listed"


def independently_validated(e: ModelEvidence) -> Verdict:
    """P4: validation approved by a reviewer who did not approve redevelopment."""
    if not e.validation:
        return "NOT_MET", None, NOT_VALIDATED
    report = e.validation["report"].get("html_path")
    validators, developers = set(e.approvals.get("validate", [])), set(e.approvals.get("redevelop", []))
    if validators and not validators & developers:
        return "MET", report, None
    return "PARTIAL", report, "Waiting for an independent approval at the validate gate"


def soundness_reviewed(e: ModelEvidence) -> Verdict:
    """P4: conceptual soundness reviewed in the validation narrative."""
    text = ((e.validation or {}).get("narrative") or {}).get("conceptual_soundness")
    return ("MET", e.validation["report"].get("html_path"), None) if text else ("NOT_MET", None, NOT_VALIDATED)


def implementation_verified(e: ModelEvidence) -> Verdict:
    """P4: the implementation is verified by a parity certificate."""
    if (e.redevelopment or {}).get("status") == "PARITY_PASSED":
        return "MET", e.redevelopment["parity"]["certificate_md_path"], None
    if e.redevelopment:
        return "NOT_MET", None, f"Parity status {e.redevelopment['status']}"
    if e.language == "Python":
        return "PARTIAL", None, "Python model, not redeveloped, so there is no parity certificate"
    return "NOT_MET", None, "Not redeveloped yet"


def monitoring_in_place(e: ModelEvidence) -> Verdict:
    """P4: performance monitoring results exist."""
    return ("MET", e.monitoring.get("result_path"), None) if e.monitoring else ("NOT_MET", None, "Not monitored yet")


def revalidation_defined(e: ModelEvidence) -> Verdict:
    """P4: a revalidation date and monitoring triggers are defined."""
    has_date = bool((e.inventory or {}).get("next_validation_due"))
    has_triggers = bool((e.monitoring or {}).get("thresholds_used"))
    if has_date and has_triggers:
        return "MET", e.monitoring.get("result_path"), None
    if has_date or has_triggers:
        return "PARTIAL", None, "Only one of revalidation date and triggers is defined"
    return "NOT_MET", None, "No revalidation date or trigger yet"


def findings_recorded(e: ModelEvidence) -> Verdict:
    """P5: findings with recommendations (tracking to closure is outside the prototype)."""
    if not e.validation:
        return "NOT_MET", None, NOT_VALIDATED
    if e.validation["result"].get("findings"):
        return (
            "PARTIAL",
            e.validation["report"].get("html_path"),
            "Findings recorded; tracking to closure is outside the prototype",
        )
    return "MET", e.validation["report"].get("html_path"), "No findings raised"


def restriction_of_use(e: ModelEvidence) -> Verdict:
    """P5: restriction of use when the overall rating is RED."""
    if not e.validation:
        return "NOT_MET", None, NOT_VALIDATED
    rating = e.validation["result"].get("overall_rating")
    if rating == "RED":
        return (
            "PARTIAL",
            e.validation["report"].get("html_path"),
            "Rating is RED: the owner must decide on restricting use",
        )
    return "MET", e.validation["report"].get("html_path"), f"Rating is {rating}; no restriction of use is required"
