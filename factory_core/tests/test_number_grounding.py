"""Number grounding: every number in the narrative must exist in the computed results."""

import pytest

from app.agents.number_grounding import extract_numbers, grounding_score, matches, source_values


def test_extract_numbers_skips_list_markers_and_names() -> None:
    """List markers, SS1/23 and model ids are not numbers of the narrative; dates give their year."""
    text = "1. AUC is 0.764 under PRA SS1/23 for M001.\n2. Validated on 2023-02-14, PSI 0.012 and 1,850 cases."
    assert extract_numbers(text) == ["0.764", "2023", "0.012", "1,850"]


def test_source_values_reads_numbers_strings_and_list_lengths() -> None:
    """Numeric values, numbers inside strings and list lengths all count as computed values."""
    values = source_values({"auc": 0.764, "tier": "Tier 1", "findings": [{"id": "F001"}, {"id": "F002"}], "ok": True})
    assert {0.764, 1.0, 2.0} <= values
    assert 1.0 in values


@pytest.mark.parametrize(
    ("token", "value", "expected"),
    [
        ("0.764", 0.7641, True),
        ("0.76", 0.764, True),
        ("76.4%", 0.764, True),
        ("76.4", 0.764, True),
        ("0.0021", -0.0021, True),
        ("3.1e-09", 3.1e-9, True),
        ("1,850", 1850, True),
        ("2", 2, True),
        ("0", 0.012, False),
        ("1", 0.6, False),
        ("0.80", 0.764, False),
    ],
)
def test_matches(token: str, value: float, expected: bool) -> None:
    """Decimals round to what is written; whole numbers must match exactly."""
    assert matches(token, value) is expected


def test_grounding_score_counts_and_lists_unverified_numbers() -> None:
    """An invented number is counted and listed once."""
    text = "The AUC is 0.764. The Gini is 0.61. Again, the Gini is 0.61."
    grounding, unverified = grounding_score(text, source_values({"auc": 0.764, "gini": 0.528}))
    assert grounding.model_dump() == {"numbers_in_narrative": 3, "numbers_verified": 1, "score": 0.333}
    assert unverified == ["0.61"]


def test_text_without_numbers_is_fully_grounded() -> None:
    """A narrative with no numbers scores 1.0."""
    grounding, unverified = grounding_score("Discrimination is strong.", set())
    assert (grounding.score, unverified) == (1.0, [])


def test_numbers_followed_by_a_comma_keep_their_value() -> None:
    """A thousands separator is part of a number; a comma after it is not."""
    assert extract_numbers("Exposure is 1,850, the AUC 0.764, and 12% of cases.") == ["1,850", "0.764", "12%"]
