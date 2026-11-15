"""Reads the hidden answer keys in model_estate/_answer_keys/. Only the two evaluation scripts use this.

The agents and the API can never read these files (the safe file reader blocks them).
Shape of one key as the estate writes it, every part optional:
  {"model_id": "M001",
   "expected_inventory": {"model_type": "credit_pd", "algorithm": "Logistic regression scorecard",
                          "input_variables": ["woe_util", "woe_payr"]},
   "seeded_doc_differences": [{"id": "D002", "topic": "Decision cutoff",
       "legacy_evidence": {"file": "model_estate/.../model_document_2021.md", "start_line": 69, "end_line": 69},
       "code_evidence": {"file": "model_estate/.../03_score.sas", "start_line": 39, "end_line": 39}}]}
The older names "inventory" and "doc_discrepancies" (with "keywords" or "legacy_line") are read too.
A string matches when one text contains the other (case and spacing ignored), and otherwise scores the
share of its words that appear; a list is scored by recall; {"keywords": [...]} matches when every keyword
appears.
"""

import json
import re
from pathlib import Path
from typing import Any

from app.config import Settings

INVENTORY_KEYS = ("expected_inventory", "inventory", "fields")
DISCREPANCY_KEYS = ("seeded_doc_differences", "doc_discrepancies", "discrepancies", "seeded_discrepancies")
WORD_PATTERN = re.compile(r"[a-z0-9]+")
STOP_WORDS = {"a", "an", "and", "by", "for", "in", "of", "on", "plus", "the", "to", "with"}


def load_answer_keys(settings: Settings) -> dict[str, dict[str, Any]]:
    """Every answer key file by model id; empty when the folder does not exist."""
    folder = settings.estate_dir / "_answer_keys"
    keys: dict[str, dict[str, Any]] = {}
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        content = json.loads(path.read_text(encoding="utf-8"))
        keys[content.get("model_id", Path(path).stem)] = content
    return keys


def first_present(content: dict[str, Any], names: tuple[str, ...], default: Any) -> Any:
    """The value of the first of several accepted key names."""
    return next((content[name] for name in names if name in content), default)


def expected_inventory(content: dict[str, Any]) -> dict[str, Any]:
    """The expected inventory fields of one answer key."""
    return first_present(content, INVENTORY_KEYS, {})


def seeded_discrepancies(content: dict[str, Any]) -> list[dict[str, Any]]:
    """The seeded document discrepancies of one answer key."""
    return first_present(content, DISCREPANCY_KEYS, [])


def normalise(value: Any) -> str:
    """Lower case text with single spaces."""
    return " ".join(str(value).lower().split())


def text_matches(expected: Any, actual: Any) -> bool:
    """True when one text contains the other, or every listed keyword appears."""
    if actual in (None, "", []):
        return False
    if isinstance(expected, dict) and "keywords" in expected:
        return all(normalise(keyword) in normalise(actual) for keyword in expected["keywords"])
    expected_text, actual_text = normalise(expected), normalise(actual)
    return expected_text in actual_text or actual_text in expected_text


def content_words(value: Any) -> set[str]:
    """The lower case words of a text, without small joining words such as "on" or "with"."""
    return {word for word in WORD_PATTERN.findall(str(value).lower()) if word not in STOP_WORDS}


def text_score(expected: Any, actual: Any) -> float:
    """1.0 when the texts match; otherwise the share of the expected words found in the actual text."""
    if text_matches(expected, actual):
        return 1.0
    if isinstance(expected, dict) or actual in (None, "", []):
        return 0.0
    wanted = content_words(expected)
    return round(len(wanted & content_words(actual)) / len(wanted), 3) if wanted else 0.0
