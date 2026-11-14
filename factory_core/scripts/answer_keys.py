"""Reads the hidden answer keys in model_estate/_answer_keys/. Only the two evaluation scripts use this.

The agents and the API can never read these files (the safe file reader blocks them).
Expected shape of one key, every part optional:
  {"model_id": "M001",
   "inventory": {"model_type": "credit_pd", "algorithm": "logistic", "input_variables": ["PAY_0", "LIMIT_BAL"]},
   "doc_discrepancies": [{"topic": "Decision cutoff", "keywords": ["520", "540"], "legacy_line": 88}]}
A string value matches when one text contains the other (case and spacing ignored); a list is scored by
recall; {"keywords": [...]} matches when every keyword appears.
"""

import json
from pathlib import Path
from typing import Any

from app.config import Settings

INVENTORY_KEYS = ("inventory", "expected_inventory", "fields")
DISCREPANCY_KEYS = ("doc_discrepancies", "discrepancies", "seeded_discrepancies")


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
