"""Drift recall: how many seeded document discrepancies the drift detector found.

Run from the factory_core folder: python -m scripts.evaluate_document_drift
A seeded discrepancy is found when a drift item matches its keywords, covers its legacy line, or shares
most words of its topic. Recall is reported on VERIFIED items, and separately including UNVERIFIED ones.
Writes artifacts/evaluation/document_drift.json for the deck.
"""

import argparse
import json
import sys
from typing import Any

from sqlmodel import Session

from app.config import Settings, load_settings
from app.database import create_database_engine, latest_stage_output
from scripts.answer_keys import load_answer_keys, normalise, seeded_discrepancies, text_matches


def item_text(item: dict[str, Any]) -> str:
    """Topic and both statements of a drift item as one text."""
    return " ".join(str(item.get(name, "")) for name in ("topic", "legacy_doc_says", "code_says"))


def is_found(seeded: dict[str, Any], item: dict[str, Any]) -> bool:
    """True when a drift item describes the seeded discrepancy."""
    if seeded.get("keywords"):
        return text_matches({"keywords": seeded["keywords"]}, item_text(item))
    legacy = item.get("legacy_evidence") or {}
    if seeded.get("legacy_line") and legacy.get("start_line"):
        return legacy["start_line"] <= seeded["legacy_line"] <= legacy.get("end_line", legacy["start_line"])
    topic_words = set(normalise(seeded.get("topic", "")).split())
    shared = topic_words & set(normalise(item.get("topic", "")).split())
    return bool(topic_words) and len(shared) / len(topic_words) >= 0.5


def recall(seeded: list[dict[str, Any]], items: list[dict[str, Any]]) -> tuple[int, list[str]]:
    """How many seeded discrepancies were found, and the topics of those that were missed."""
    missed = [entry.get("topic", "unnamed") for entry in seeded if not any(is_found(entry, item) for item in items)]
    return len(seeded) - len(missed), missed


def evaluate(settings: Settings) -> dict[str, Any]:
    """Recall per model and overall, on verified items and on all items."""
    engine = create_database_engine(settings.database_path)
    models: dict[str, Any] = {}
    with Session(engine) as session:
        for model_id, content in load_answer_keys(settings).items():
            seeded = seeded_discrepancies(content)
            documentation = latest_stage_output(session, model_id, "documentation")
            if not seeded or documentation is None:
                models[model_id] = {"seeded": len(seeded), "documented": documentation is not None}
                continue
            items = documentation.get("doc_drift", [])
            verified = [item for item in items if item.get("status") == "VERIFIED"]
            found_verified, missed = recall(seeded, verified)
            found_any, _ = recall(seeded, items)
            models[model_id] = {
                "seeded": len(seeded),
                "documented": True,
                "found_verified": found_verified,
                "found_including_unverified": found_any,
                "missed": missed,
                "drift_items": len(items),
                "drift_items_verified": len(verified),
            }
    scored = [model for model in models.values() if "found_verified" in model]
    seeded_total = sum(model["seeded"] for model in scored)
    return {
        "models": models,
        "seeded_total": seeded_total,
        "recall_verified": round(sum(m["found_verified"] for m in scored) / seeded_total, 3) if seeded_total else None,
        "recall_including_unverified": (
            round(sum(m["found_including_unverified"] for m in scored) / seeded_total, 3) if seeded_total else None
        ),
    }


def main(argv: list[str] | None = None) -> int:
    """Print the evaluation and save it under artifacts/evaluation/."""
    argparse.ArgumentParser(description="Measure how many seeded document discrepancies were found.").parse_args(argv)
    settings = load_settings()
    result = evaluate(settings)
    if not result["models"]:
        print("No answer keys found in model_estate/_answer_keys/.")
        return 1
    for model_id, model in result["models"].items():
        if "found_verified" not in model:
            print(f"{model_id}: not evaluated ({model['seeded']} seeded, documented: {model['documented']})")
            continue
        found = f"{model['found_verified']} of {model['seeded']} found with verified evidence"
        print(f"{model_id}: {found}; missed {model['missed']}")
    print(f"Drift recall (verified): {result['recall_verified']}")
    print(f"Drift recall including unverified items: {result['recall_including_unverified']}")
    target = settings.artifacts_dir / "evaluation" / "document_drift.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
