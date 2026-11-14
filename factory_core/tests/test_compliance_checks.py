"""Single compliance checks on hand made evidence."""

from app.agents.compliance_checks import (
    ModelEvidence,
    development_tested,
    implementation_verified,
    independently_validated,
    restriction_of_use,
)
from tests.conftest import load_example


def evidence(**parts) -> ModelEvidence:
    """Evidence for a SAS model with only the given outputs."""
    base = {"inventory": None, "documentation": None, "redevelopment": None, "validation": None, "monitoring": None}
    return ModelEvidence(model_id="M001", language="SAS", **(base | parts))


def test_same_person_approving_both_gates_is_not_independent() -> None:
    """Validation approved by the redevelopment approver stays PARTIAL."""
    view = load_example("validation_view.M001.json")
    same = evidence(validation=view, approvals={"redevelop": ["alex"], "validate": ["alex"]})
    other = evidence(validation=view, approvals={"redevelop": ["alex"], "validate": ["sam"]})
    assert independently_validated(same)[0] == "PARTIAL"
    assert independently_validated(other)[0] == "MET"


def test_parity_drives_testing_and_implementation() -> None:
    """A passed certificate meets both; a failed one meets neither; a SAS model not yet rebuilt is NOT_MET."""
    passed = evidence(redevelopment=load_example("redevelop_result.M001.json"))
    failed = evidence(redevelopment=load_example("redevelop_result.M001.json") | {"status": "PARITY_FAILED"})
    assert (development_tested(passed)[0], implementation_verified(passed)[0]) == ("MET", "MET")
    assert (development_tested(failed)[0], implementation_verified(failed)[0]) == ("NOT_MET", "NOT_MET")
    assert implementation_verified(evidence())[0] == "NOT_MET"


def test_red_rating_needs_an_owner_decision_on_restriction() -> None:
    """RED is PARTIAL until the owner decides; any other rating needs no restriction."""
    view = load_example("validation_view.M001.json")
    red = view | {"result": view["result"] | {"overall_rating": "RED"}}
    assert restriction_of_use(evidence(validation=red))[0] == "PARTIAL"
    assert restriction_of_use(evidence(validation=view))[0] == "MET"
