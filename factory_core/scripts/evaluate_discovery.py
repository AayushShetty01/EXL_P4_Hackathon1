"""Discovery accuracy: compare the stored inventory records with the hidden answer keys.

Run from the factory_core folder: python -m scripts.evaluate_discovery
Prints field accuracy per model and overall, and writes artifacts/evaluation/discovery.json for the deck.
"""

import json
import sys
from typing import Any

from sqlmodel import Session

from app.config import Settings, load_settings
from app.database import create_database_engine, latest_stage_output
from scripts.answer_keys import expected_inventory, load_answer_keys, normalise, text_matches


def field_score(expected: Any, actual: Any) -> float:
    """1.0 for a match, the recall for lists, 0.0 otherwise."""
    if isinstance(expected, list):
        found = {normalise(item["name"] if isinstance(item, dict) else item) for item in actual or []}
        wanted = [normalise(item) for item in expected]
        return sum(item in found for item in wanted) / len(wanted) if wanted else 1.0
    if isinstance(expected, (bool, int, float)):
        return float(expected == actual)
    return float(text_matches(expected, actual))


def evaluate(settings: Settings) -> dict[str, Any]:
    """Field scores per model and the overall accuracy over every scored field."""
    keys = load_answer_keys(settings)
    engine = create_database_engine(settings.database_path)
    models: dict[str, Any] = {}
    with Session(engine) as session:
        for model_id, content in keys.items():
            record = latest_stage_output(session, model_id, "inventory_record")
            expected = expected_inventory(content)
            if record is None or not expected:
                models[model_id] = {"discovered": record is not None, "fields": {}}
                continue
            scores = {name: field_score(value, record.get(name)) for name, value in expected.items()}
            models[model_id] = {"discovered": True, "fields": scores, "accuracy": sum(scores.values()) / len(scores)}
    all_scores = [score for model in models.values() for score in model["fields"].values()]
    overall = round(sum(all_scores) / len(all_scores), 3) if all_scores else None
    return {"models": models, "fields_scored": len(all_scores), "field_accuracy": overall}


def main(argv: list[str] | None = None) -> int:
    """Print the evaluation and save it under artifacts/evaluation/."""
    settings = load_settings()
    result = evaluate(settings)
    if not result["models"]:
        print("No answer keys found in model_estate/_answer_keys/.")
        return 1
    for model_id, model in result["models"].items():
        if not model["fields"]:
            print(
                f"{model_id}: not evaluated ({'no expected fields' if model['discovered'] else 'not discovered yet'})"
            )
            continue
        print(f"{model_id}: accuracy {model['accuracy']:.2f}")
        for name, score in model["fields"].items():
            print(f"  {name:<24} {score:.2f}")
    print(f"Overall field accuracy: {result['field_accuracy']} over {result['fields_scored']} fields")
    target = settings.artifacts_dir / "evaluation" / "discovery.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
