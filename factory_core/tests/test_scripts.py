"""The command line scripts: seeding, snapshot export, and evaluation against the answer keys."""

import json

import pytest

from app.config import Settings
from scripts.answer_keys import load_answer_keys, text_matches, text_score
from scripts.evaluate_discovery import evaluate as evaluate_discovery
from scripts.evaluate_discovery import field_score
from scripts.evaluate_document_drift import evaluate as evaluate_drift
from scripts.evaluate_document_drift import same_lines
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


def lines(file: str, start: int, end: int) -> dict:
    """Evidence lines of one file in the hero model folder, as the estate answer keys write them."""
    return {"file": f"{HERO_FOLDER}/{file}", "start_line": start, "end_line": end}


ESTATE_ANSWER_KEY = {
    "model_id": "M001",
    "expected_inventory": {
        "model_type": "credit_pd",
        "language": "SAS",
        "algorithm": "Logistic regression scorecard with WoE binning",
        "input_variables": ["PAY_0", "LIMIT_BAL"],
        "raw_input_columns": ["PAY_0"],
    },
    "seeded_doc_differences": [
        {
            "id": "D001",
            "topic": "Decision cutoff",
            "legacy_evidence": lines("docs/model_document_2021.md", 7, 7),
            "code_evidence": lines("code/03_score.sas", 4, 4),
        },
        {
            "id": "D002",
            "topic": "Number of input variables",
            "legacy_evidence": lines("docs/model_document_2021.md", 3, 3),
            "code_evidence": lines("code/02_train.sas", 3, 3),
        },
    ],
}


def seed_with(hero_estate: Settings, answer_key: dict) -> Settings:
    """Write one answer key into the test estate and run M001 once automatically."""
    (hero_estate.estate_dir / "_answer_keys" / "M001.json").write_text(json.dumps(answer_key))
    settings = live_settings(hero_estate)
    assert seed(settings, context_options={"llm_provider": pipeline_provider()}) == 0
    return settings


@pytest.fixture
def seeded(hero_estate: Settings) -> Settings:
    """The test estate with an answer key in the older shape, after one automatic run of M001."""
    return seed_with(hero_estate, ANSWER_KEY)


@pytest.fixture
def seeded_estate_key(hero_estate: Settings) -> Settings:
    """The test estate with an answer key in the shape model_estate uses, after one automatic run of M001."""
    return seed_with(hero_estate, ESTATE_ANSWER_KEY)


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


def test_discovery_scores_the_estate_answer_key(seeded_estate_key: Settings) -> None:
    """Free text earns the share of its words found; fields outside the inventory record are not scored."""
    model = evaluate_discovery(seeded_estate_key)["models"]["M001"]
    assert model["fields"] == {"model_type": 1.0, "language": 1.0, "algorithm": 0.8, "input_variables": 0.5}
    assert model["not_scored"] == ["raw_input_columns"]
    assert model["accuracy"] == 0.825


def test_drift_recall_uses_the_cited_lines_of_the_estate_answer_key(seeded_estate_key: Settings) -> None:
    """A drift item citing a seeded line is found; one citing other lines is missed."""
    model = evaluate_drift(seeded_estate_key)["models"]["M001"]
    assert (model["seeded"], model["found_verified"], model["missed"]) == (2, 1, ["Number of input variables"])


def test_line_ranges_and_word_scores() -> None:
    """Evidence matches on a shared line of the same file; text scores count the expected words."""
    seeded = {"file": "a.md", "start_line": 5, "end_line": 8}
    assert same_lines(seeded, {"file": "a.md", "start_line": 8, "end_line": 9})
    assert not same_lines(seeded, {"file": "b.md", "start_line": 6, "end_line": 6})
    assert not same_lines(seeded, {"file": "a.md", "start_line": 9})
    assert text_score("Binomial GLM with logit link", "GLM, binomial family and logit link") == 1.0
    assert text_score("Gradient boosting classifier", "Random forest") == 0.0


def test_answer_key_helpers(seeded: Settings) -> None:
    """Keys are read by model id; text matching ignores case and accepts keyword lists."""
    assert set(load_answer_keys(seeded)) == {"M001"}
    assert text_matches("Logistic Regression", "logistic regression scorecard on WoE variables")
    assert not text_matches({"keywords": ["gbm"]}, "logistic regression")
    assert field_score(["PAY_0"], [{"name": "pay_0"}]) == 1.0
