"""The deterministic tiering policy and the document status rule."""

from datetime import date

import pytest

from app.tiering_policy import add_months, assign_tier, complexity_score, document_status, tier_model


@pytest.mark.parametrize(
    ("exposure", "regulatory_use", "customer_facing", "algorithm", "expected"),
    [
        (1850, "IRB", True, "Logistic regression scorecard on WoE variables", ("Tier 1", 3, 1)),
        (500, None, False, "Gradient boosting classifier", ("Tier 1", 2, 2)),
        (500, "none", False, "Logistic regression", ("Tier 2", 2, 1)),
        (50, None, True, "Rules plus linear regression", ("Tier 2", 2, 1)),
        (50, None, False, "Neural network", ("Tier 2", 1, 3)),
        (50, None, False, "Binomial GLM", ("Tier 3", 1, 1)),
        (50, None, False, None, ("Tier 3", 1, 2)),
    ],
)
def test_tier_follows_the_policy(exposure, regulatory_use, customer_facing, algorithm, expected) -> None:
    """Materiality, complexity and tier follow the illustrative policy table."""
    outcome = tier_model(
        exposure_gbp_m=exposure,
        regulatory_use=regulatory_use,
        customer_facing=customer_facing,
        algorithm=algorithm,
        input_count=8,
        last_validated="2023-02-14",
    )
    tiering = outcome.tiering
    actual = (tiering.tier, tiering.materiality_score, tiering.complexity_score)
    assert actual == expected
    assert tiering.rationale[-1].startswith(expected[0])


def test_rationale_is_plain_sentences() -> None:
    """The hero model's rationale names exposure, regulatory use, algorithm and the tier rule."""
    outcome = tier_model(
        exposure_gbp_m=1850,
        regulatory_use="IRB",
        customer_facing=True,
        algorithm="Logistic regression scorecard",
        input_count=8,
        last_validated="2023-02-14",
    )
    assert outcome.tiering.rationale == [
        "Exposure of GBP 1,850m is at or above GBP 1,000m.",
        "Used for a regulatory purpose (IRB).",
        "Algorithm 'Logistic regression scorecard' is rated complexity 1 "
        "(rules, linear or logistic regression, GLM or scorecard).",
        "Tier 1 because materiality is 3.",
    ]
    assert outcome.next_validation_due == "2024-02-14"
    assert outcome.open_questions == []


def test_many_inputs_raise_complexity() -> None:
    """More than 30 inputs make even a logistic regression complexity 2."""
    score, rationale, _ = complexity_score("Logistic regression", 40)
    assert score == 2
    assert "40 inputs" in rationale[-1]


def test_unknown_algorithm_gives_complexity_two_and_a_question() -> None:
    """An algorithm the table does not know is complexity 2 with an open question."""
    score, _, questions = complexity_score("Proprietary method", 5)
    assert score == 2
    assert questions


def test_tier_rules_at_the_boundaries() -> None:
    """Materiality 2 with complexity 2 is Tier 1; complexity 3 alone is Tier 2."""
    assert assign_tier(2, 2)[0] == "Tier 1"
    assert assign_tier(1, 3)[0] == "Tier 2"
    assert assign_tier(1, 2)[0] == "Tier 3"


def test_next_validation_due_depends_on_the_tier() -> None:
    """Tier 1, 2 and 3 are due 12, 24 and 36 months after the last validation."""
    common = {"regulatory_use": None, "customer_facing": False, "input_count": 5, "last_validated": "2023-02-14"}
    assert tier_model(exposure_gbp_m=2000, algorithm="glm", **common).next_validation_due == "2024-02-14"
    assert tier_model(exposure_gbp_m=200, algorithm="glm", **common).next_validation_due == "2025-02-14"
    assert tier_model(exposure_gbp_m=20, algorithm="glm", **common).next_validation_due == "2026-02-14"


def test_missing_register_values_become_open_questions() -> None:
    """No exposure and no validation date give open questions and no due date."""
    outcome = tier_model(
        exposure_gbp_m=None,
        regulatory_use=None,
        customer_facing=None,
        algorithm="glm",
        input_count=3,
        last_validated=None,
    )
    assert outcome.next_validation_due is None
    assert len(outcome.open_questions) == 2


def test_add_months_moves_to_the_month_end() -> None:
    """A date that does not exist in the target month moves back to the last day."""
    assert add_months(date(2024, 2, 29), 12) == date(2025, 2, 28)
    assert add_months(date(2023, 1, 31), 1) == date(2023, 2, 28)


@pytest.mark.parametrize(
    ("has_document", "doc_date", "code_date", "expected"),
    [
        (False, None, None, "MISSING"),
        (True, "2021-03-01", "2023-06-20", "OUTDATED"),
        (True, "2026-06-01", "2026-01-10", "CURRENT"),
        (True, "2025-01-10", "2024-12-01", "OUTDATED"),
        (True, None, "2024-12-01", "OUTDATED"),
    ],
)
def test_document_status(has_document, doc_date, code_date, expected) -> None:
    """Missing, older than the code, older than 12 months, or current."""
    status, _ = document_status(has_document, doc_date, code_date, today=date(2026, 11, 15))
    assert status == expected
