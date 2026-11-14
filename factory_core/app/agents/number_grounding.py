"""Number grounding (no LLM): every number in the validation narrative must exist in the computed results.

A number in the text matches a source value after rounding to the decimals written (0.764 matches
0.7641), in percent form (76.4% or 76.4 percent matches 0.764), or as a count of a list in the results.
Whole numbers must match exactly, so "0" or "1" cannot be matched by rounding a small value.
"""

import math
import re
from typing import Any

from app.stage_result_schemas import NumberGrounding

NUMBER_PATTERN = re.compile(r"(?<![\w./-])[-+]?\d+(?:,\d{3})*(?:\.\d+)?(?:[eE][-+]?\d+)?%?(?![\w/])")
LIST_MARKER_PATTERN = re.compile(r"^\s*\d+[.)]\s", re.MULTILINE)


def extract_numbers(text: str) -> list[str]:
    """Every number written in a text, leaving out list markers such as "1." at the start of a line."""
    return NUMBER_PATTERN.findall(LIST_MARKER_PATTERN.sub(" ", text))


def source_values(*sources: Any) -> set[float]:
    """Every number in the sources: numeric values, numbers inside strings, and list lengths."""
    values: set[float] = set()

    def walk(value: Any) -> None:
        """Collect the numbers of one JSON value."""
        if isinstance(value, bool) or value is None:
            return
        if isinstance(value, (int, float)):
            values.add(float(value))
        elif isinstance(value, str):
            values.update(parse_number(token)[0] for token in extract_numbers(value))
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            values.add(float(len(value)))
            for item in value:
                walk(item)

    for source in sources:
        walk(source)
    return values


def parse_number(token: str) -> tuple[float, bool, int | None]:
    """Value, whether it is a percent, and the decimals written (None for scientific notation)."""
    percent = token.endswith("%")
    text = token.rstrip("%").replace(",", "")
    if "e" in text.lower():
        return float(text), percent, None
    decimals = len(text.split(".")[1]) if "." in text else 0
    return float(text), percent, decimals


def rounds_to(value: float, decimals: int, number: float) -> bool:
    """True when value rounded to the given decimals equals the written number."""
    return math.isclose(round(value, decimals), number, abs_tol=1e-9)


def matches(token: str, value: float) -> bool:
    """True when a written number stands for a source value (the sign may be dropped in words)."""
    number, percent, decimals = parse_number(token)
    for magnitude in (value, abs(value)):
        if decimals is None:
            if math.isclose(number, magnitude, rel_tol=1e-6):
                return True
        elif percent:
            if rounds_to(magnitude * 100, decimals, number) or rounds_to(magnitude, decimals, number):
                return True
        elif decimals == 0:
            if magnitude == number:
                return True
        elif rounds_to(magnitude, decimals, number) or rounds_to(magnitude * 100, decimals, number):
            return True
    return False


def check_numbers(text: str, values: set[float]) -> tuple[list[str], list[str]]:
    """All numbers in a text, and those that match no source value."""
    tokens = extract_numbers(text)
    unmatched = [token for token in tokens if not any(matches(token, value) for value in values)]
    return tokens, unmatched


def grounding_score(text: str, values: set[float]) -> tuple[NumberGrounding, list[str]]:
    """The grounding counts of a narrative and its unverified numbers (each listed once)."""
    tokens, unmatched = check_numbers(text, values)
    verified = len(tokens) - len(unmatched)
    score = round(verified / len(tokens), 3) if tokens else 1.0
    grounding = NumberGrounding(numbers_in_narrative=len(tokens), numbers_verified=verified, score=score)
    return grounding, list(dict.fromkeys(unmatched))
