"""Deterministic risk tiering and document status (no LLM).

An illustrative policy for the demonstration, not a regulatory rule: materiality from the register,
complexity from the discovered algorithm, a tier from both, and the next validation date from the tier.
"""

import calendar
from dataclasses import dataclass, field
from datetime import date

from app.api_schemas import Tiering
from app.schemas import DocStatus, Tier

COMPLEXITY_KEYWORDS: tuple[tuple[int, tuple[str, ...]], ...] = (
    (3, ("neural", "deep learning", "lstm", "transformer", "support vector")),
    (
        2,
        ("gradient boost", "boosting", "xgboost", "lightgbm", "catboost", "random forest", "decision tree", "ensemble"),
    ),
    (1, ("rule", "linear", "logistic", "glm", "generalised linear", "generalized linear", "scorecard", "regression")),
)
COMPLEXITY_DESCRIPTIONS = {
    1: "rules, linear or logistic regression, GLM or scorecard",
    2: "tree ensembles or gradient boosting",
    3: "neural networks or other methods with low explainability",
}
NO_REGULATORY_USE = {"", "none", "no", "n/a", "na", "not applicable"}
MANY_INPUTS = 30
REVALIDATION_MONTHS: dict[str, int] = {"Tier 1": 12, "Tier 2": 24, "Tier 3": 36}


@dataclass(frozen=True)
class TieringOutcome:
    """Tier with its rationale, the next validation date and any open questions."""

    tiering: Tiering
    next_validation_due: str | None
    open_questions: list[str] = field(default_factory=list)


def parse_date(text: str | None) -> date | None:
    """Read an ISO date (YYYY-MM-DD, extra time text ignored); None when missing or invalid."""
    try:
        return date.fromisoformat(text[:10]) if text else None
    except ValueError:
        return None


def add_months(start: date, months: int) -> date:
    """Same day a number of months later, moved back to the month end when that day does not exist."""
    month_index = start.month - 1 + months
    year, month = start.year + month_index // 12, month_index % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def has_regulatory_use(regulatory_use: str | None) -> bool:
    """True when the register names a regulatory use."""
    return (regulatory_use or "").strip().lower() not in NO_REGULATORY_USE


def materiality_score(
    exposure_gbp_m: float | None, regulatory_use: str | None, customer_facing: bool | None
) -> tuple[int, list[str], list[str]]:
    """Materiality 1 to 3 from exposure, regulatory use and customer impact, with rationale and questions."""
    rationale: list[str] = []
    questions: list[str] = []
    exposure = exposure_gbp_m or 0.0
    if exposure_gbp_m is None:
        questions.append("What is the exposure of this model? The register does not record it.")
    if exposure >= 1000:
        rationale.append(f"Exposure of GBP {exposure:,.0f}m is at or above GBP 1,000m.")
    if has_regulatory_use(regulatory_use):
        rationale.append(f"Used for a regulatory purpose ({regulatory_use}).")
    if rationale:
        return 3, rationale, questions
    if 100 <= exposure < 1000:
        rationale.append(f"Exposure of GBP {exposure:,.0f}m is between GBP 100m and GBP 1,000m.")
    if customer_facing:
        rationale.append("Customer facing model.")
    if rationale:
        return 2, rationale, questions
    rationale.append("Exposure below GBP 100m, no regulatory use and not customer facing.")
    return 1, rationale, questions


def complexity_score(algorithm: str | None, input_count: int) -> tuple[int, list[str], list[str]]:
    """Complexity 1 to 3 from the algorithm text and the number of inputs, with rationale and questions."""
    text = (algorithm or "").lower()
    score = next((level for level, words in COMPLEXITY_KEYWORDS if any(word in text for word in words)), None)
    if score is None:
        rationale = [f"Algorithm {algorithm!r} is not in the keyword table, so complexity is set to 2."]
        if not algorithm:
            rationale = ["The algorithm could not be determined, so complexity is set to 2."]
        return 2, rationale, ["What algorithm does the model use? Complexity was set to 2 until this is confirmed."]
    rationale = [f"Algorithm {algorithm!r} is rated complexity {score} ({COMPLEXITY_DESCRIPTIONS[score]})."]
    if input_count > MANY_INPUTS and score < 2:
        rationale.append(f"{input_count} inputs, more than {MANY_INPUTS}, raise complexity to 2.")
        score = 2
    return score, rationale, []


def assign_tier(materiality: int, complexity: int) -> tuple[Tier, str]:
    """Tier from the two scores, with the sentence that explains it."""
    if materiality == 3:
        return "Tier 1", "Tier 1 because materiality is 3."
    if materiality == 2 and complexity >= 2:
        return "Tier 1", "Tier 1 because materiality is 2 and complexity is 2 or more."
    if materiality == 2:
        return "Tier 2", "Tier 2 because materiality is 2."
    if complexity == 3:
        return "Tier 2", "Tier 2 because complexity is 3."
    return "Tier 3", "Tier 3 because materiality and complexity are both low."


def tier_model(
    *,
    exposure_gbp_m: float | None,
    regulatory_use: str | None,
    customer_facing: bool | None,
    algorithm: str | None,
    input_count: int,
    last_validated: str | None,
) -> TieringOutcome:
    """Apply the whole tiering policy to one model."""
    materiality, materiality_reasons, materiality_questions = materiality_score(
        exposure_gbp_m, regulatory_use, customer_facing
    )
    complexity, complexity_reasons, complexity_questions = complexity_score(algorithm, input_count)
    tier, tier_reason = assign_tier(materiality, complexity)
    validated = parse_date(last_validated)
    questions = materiality_questions + complexity_questions
    if validated is None:
        questions.append("When was the model last validated? The register does not record a valid date.")
    due = add_months(validated, REVALIDATION_MONTHS[tier]).isoformat() if validated else None
    return TieringOutcome(
        tiering=Tiering(
            tier=tier,
            materiality_score=materiality,
            complexity_score=complexity,
            rationale=materiality_reasons + complexity_reasons + [tier_reason],
        ),
        next_validation_due=due,
        open_questions=questions,
    )


def document_status(
    has_document: bool, doc_last_updated: str | None, last_code_change: str | None, today: date
) -> tuple[DocStatus, list[str]]:
    """MISSING without a document, OUTDATED when older than the code or 12 months, otherwise CURRENT."""
    if not has_document:
        return "MISSING", ["There is no model document in the estate folder."]
    document_date = parse_date(doc_last_updated)
    if document_date is None:
        return "OUTDATED", ["When was the model document last updated? The register does not record it."]
    code_date = parse_date(last_code_change)
    if code_date and document_date < code_date:
        return "OUTDATED", []
    if add_months(document_date, 12) < today:
        return "OUTDATED", []
    return "CURRENT", []
