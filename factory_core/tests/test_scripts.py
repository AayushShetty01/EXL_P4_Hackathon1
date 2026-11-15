"""The command line scripts: seeding, snapshot export, and evaluation against the answer keys."""

import json

import pytest

from app.config import Settings
from scripts.answer_keys import load_answer_keys, text_matches
from scripts.evaluate_discovery import evaluate as evaluate_discovery
from scripts.evaluate_discovery import field_score
from scripts.evaluate_document_drift import evaluate as evaluate_drift
from scripts.export_snapshot import export
from scripts.seed_demo import seed
from tests.conftest import HERO_FOLDER, live_settings, pipeline_provider

ANSWER_KEY = {
    "model_id": "M001",
    "inventory": {
        "model_type": "credit_pd",
        "algorithm": {"keywords": ["logistic"]},
        "target_variable": "default_flag",
        "input_variables": ["PAY_0", "LIMIT_BAL"],
    },
    "doc_discrepancies": [
        {"topic": "Decision cutoff", "keywords": ["520", "540"]},
        {"topic": "Variable list", "legacy_line": 3},
    ],
}


@pytest.fixture
def seeded(hero_estate: Settings) -> Settings:
    """The test estate with a real answer key, after one automatic run of M001."""
    (hero_estate.estate_dir / "_answer_keys" / "M001.json").write_text(json.dumps(ANSWER_KEY))
    settings = live_settings(hero_estate)
    assert seed(settings, context_options={"llm_provider": pipeline_provider()}) == 0
    return settings


def test_seed_runs_every_estate_model_to_completion(hero_estate: Settings, capsys) -> None:
    """Seeding prints each stage and ends with every run completed."""
    assert seed(live_settings(hero_estate), context_options={"llm_provider": pipeline_provider()}) == 0
    output = capsys.readouterr().out
    assert "M001 run_M001_001: COMPLETED" in output
    assert "1 of 1 runs completed." in output


def test_seed_reports_an_empty_estate(settings: Settings, capsys) -> None:
    """With no estate models there is nothing to seed."""
    assert seed(settings) == 1
    assert "No models in the estate" in capsys.readouterr().out


def test_snapshot_follows_the_layout(seeded: Settings) -> None:
    """Endpoint responses, runs and referenced files are written as section 9.4 describes."""
    output = seeded.artifacts_dir / "snapshot"
    counts = export(seeded, output)
    for relative in (
        "models.json",
        "metrics.json",
        "audit.json",
        "models/M001.json",
        "models/M001/documentation.json",
        "models/M001/compliance.json",
        "runs/run_M001_001.json",
        f"files/{HERO_FOLDER.replace('/', '__')}__code__02_train.sas.json",
    ):
        assert (output / relative).is_file(), relative
    assert counts["endpoints"] >= 9
    assert not list(output.rglob("*answer_keys*"))


def test_snapshot_refuses_to_clear_a_folder_outside_artifacts(seeded: Settings, tmp_path) -> None:
    """The export only ever deletes its own folder under artifacts/."""
    outside = tmp_path / "keep_me"
    outside.mkdir()
    with pytest.raises(SystemExit):
        export(seeded, outside)
    assert outside.is_dir()


def test_discovery_accuracy_against_the_answer_key(seeded: Settings) -> None:
    """Each expected field is scored; lists are scored by recall."""
    result = evaluate_discovery(seeded)
    fields = result["models"]["M001"]["fields"]
    assert fields == {"model_type": 1.0, "algorithm": 1.0, "target_variable": 1.0, "input_variables": 0.5}
    assert result["field_accuracy"] == 0.875


def test_drift_recall_against_the_answer_key(seeded: Settings) -> None:
    """The seeded cutoff difference is found; the variable list difference is reported as missed."""
    result = evaluate_drift(seeded)
    model = result["models"]["M001"]
    assert (model["found_verified"], model["missed"]) == (1, ["Variable list"])
    assert result["recall_verified"] == 0.5


def test_answer_key_helpers(seeded: Settings) -> None:
    """Keys are read by model id; text matching ignores case and accepts keyword lists."""
    assert set(load_answer_keys(seeded)) == {"M001"}
    assert text_matches("Logistic Regression", "logistic regression scorecard on WoE variables")
    assert not text_matches({"keywords": ["gbm"]}, "logistic regression")
    assert field_score(["PAY_0"], [{"name": "pay_0"}]) == 1.0
