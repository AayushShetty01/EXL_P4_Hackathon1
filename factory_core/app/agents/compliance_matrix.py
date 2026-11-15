"""SS1/23 compliance matrix (no LLM): a simplified team mapping of what the stored outputs show for a model.

Only the five principle titles of SS1/23 are used, never sub principle numbers. Organisational controls
are OUT_OF_SCOPE. This is a demonstration mapping, not a legal or regulatory assessment.
"""

from collections.abc import Callable

from sqlmodel import Session, col, select

from app.agents.compliance_checks import (
    ModelEvidence,
    Verdict,
    dependencies_recorded,
    development_tested,
    documentation_current,
    documented,
    findings_recorded,
    gates_audited,
    implementation_verified,
    independently_validated,
    inventory_recorded,
    monitoring_in_place,
    out_of_scope,
    owner_recorded,
    restriction_of_use,
    revalidation_defined,
    soundness_reviewed,
    tier_assigned,
)
from app.audit_trail import verify_chain
from app.database import AuditEventRow, ModelRow, RunRow, StageRunRow, latest_stage_output
from app.stage_result_schemas import Compliance, ComplianceCoverage, ComplianceItem, CompliancePrinciple

DISCLAIMER = (
    "Simplified team mapping to the five SS1/23 principles for demonstration. Not a legal or regulatory assessment."
)
PRINCIPLE_TITLES = {
    "P1": "Model identification and model risk classification",
    "P2": "Governance",
    "P3": "Model development, implementation and use",
    "P4": "Independent model validation",
    "P5": "Model risk mitigants",
}


def collect_evidence(session: Session, model: ModelRow) -> ModelEvidence:
    """Load the stored outputs, gate approvals and audit facts of one model."""
    rows = session.exec(
        select(StageRunRow)
        .join(RunRow, col(RunRow.run_id) == col(StageRunRow.run_id))
        .where(RunRow.model_id == model.model_id, StageRunRow.status == "APPROVED")
    ).all()
    approvals: dict[str, list[str]] = {}
    for row in rows:
        if row.gate:
            approvals.setdefault(row.stage, []).append(row.gate["reviewer"])
    gate_events = session.exec(
        select(AuditEventRow).where(AuditEventRow.model_id == model.model_id, AuditEventRow.action == "gate_decision")
    ).all()
    return ModelEvidence(
        model_id=model.model_id,
        language=model.language,
        inventory=latest_stage_output(session, model.model_id, "inventory_record"),
        documentation=latest_stage_output(session, model.model_id, "documentation"),
        redevelopment=latest_stage_output(session, model.model_id, "redevelopment"),
        validation=latest_stage_output(session, model.model_id, "validation_view"),
        monitoring=latest_stage_output(session, model.model_id, "monitoring"),
        approvals=approvals,
        gate_events=len(gate_events),
        chain_valid=verify_chain(session),
    )


EXPECTATIONS: tuple[tuple[str, str, str, Callable[[ModelEvidence], Verdict]], ...] = (
    (
        "P1",
        "P1_inventory",
        "The model is recorded in the inventory with owner, purpose and dependencies",
        inventory_recorded,
    ),
    ("P1", "P1_tiering", "A risk tier is assigned from materiality and complexity", tier_assigned),
    ("P1", "P1_dependencies", "Upstream and downstream dependencies are recorded", dependencies_recorded),
    ("P2", "P2_owner", "An accountable model owner is recorded", owner_recorded),
    ("P2", "P2_gate_approvals", "Approvals at each stage are recorded in a tamper evident audit trail", gates_audited),
    (
        "P2",
        "P2_board",
        "Board and senior management oversight of the framework",
        out_of_scope("Organisational control, outside a prototype"),
    ),
    (
        "P2",
        "P2_policies",
        "Model risk policies and internal audit",
        out_of_scope("Organisational control, outside a prototype"),
    ),
    ("P3", "P3_purpose_design", "Purpose and design are documented", documented(("overview", "methodology"))),
    ("P3", "P3_data", "Data and variables are documented", documented(("data_and_variables",))),
    ("P3", "P3_testing", "Development testing is evidenced (unit tests and parity)", development_tested),
    (
        "P3",
        "P3_documentation_current",
        "Documentation is current and differences to the old document are listed",
        documentation_current,
    ),
    (
        "P3",
        "P3_assumptions_limitations",
        "Assumptions and limitations are documented",
        documented(("assumptions", "limitations")),
    ),
    (
        "P4",
        "P4_independent_approval",
        "Validation is approved by a reviewer independent of development",
        independently_validated,
    ),
    ("P4", "P4_conceptual_soundness", "Conceptual soundness is reviewed", soundness_reviewed),
    ("P4", "P4_implementation", "The implementation is verified", implementation_verified),
    ("P4", "P4_monitoring", "Performance monitoring is in place", monitoring_in_place),
    ("P4", "P4_revalidation", "Revalidation schedule and triggers are defined", revalidation_defined),
    ("P5", "P5_findings", "Findings are recorded with recommendations", findings_recorded),
    ("P5", "P5_post_model_adjustments", "Post model adjustments are governed", out_of_scope("Outside the prototype")),
    ("P5", "P5_restriction", "Use is restricted when the rating is RED", restriction_of_use),
)


def build_compliance(session: Session, model: ModelRow) -> Compliance:
    """Run every check for one model and count the statuses."""
    evidence = collect_evidence(session, model)
    principles = {
        key: CompliancePrinciple(principle=key, title=title, items=[]) for key, title in PRINCIPLE_TITLES.items()
    }
    for principle, item_id, expectation, check in EXPECTATIONS:
        status, path, note = check(evidence)
        principles[principle].items.append(
            ComplianceItem(id=item_id, expectation=expectation, status=status, evidence_path=path, note=note)
        )
    statuses = [item.status for principle in principles.values() for item in principle.items]
    return Compliance(
        model_id=model.model_id,
        disclaimer=DISCLAIMER,
        principles=list(principles.values()),
        coverage=ComplianceCoverage(
            met=statuses.count("MET"),
            partial=statuses.count("PARTIAL"),
            not_met=statuses.count("NOT_MET"),
            out_of_scope=statuses.count("OUT_OF_SCOPE"),
        ),
    )
