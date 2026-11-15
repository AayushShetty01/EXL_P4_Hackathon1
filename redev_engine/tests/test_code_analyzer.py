"""Tests for the legacy code analyzer."""

import json

from app.code_analyzer import analyze, numbered_source, static_facts, verify_sources
from conftest import SPEC_REPLY


def test_numbered_source_has_header_and_line_numbers(tiny_estate):
    """Each file gets a header and every line a number."""
    folder, _ = tiny_estate
    text = numbered_source(folder, ["code/model.R"])
    assert text.startswith("=== code/model.R ===") and "   4| fit <- glm(" in text


def test_static_scan_finds_estimation_and_prediction(tiny_estate):
    """The R patterns find glm, predict and ifelse lines."""
    folder, _ = tiny_estate
    kinds = {(f["kind"], f["line"]) for f in static_facts("R", folder, ["code/model.R"])}
    assert {("estimation", 4), ("prediction", 5), ("decision", 7)} <= kinds


def test_sources_outside_the_file_are_flagged(tiny_estate):
    """A cited line range beyond the end of the file is marked as not verified."""
    folder, _ = tiny_estate
    spec = {"a": {"source": {"file": "code/model.R", "start_line": 2, "end_line": 3}},
            "b": [{"source": {"file": "code/model.R", "start_line": 5, "end_line": 99}}]}
    assert verify_sources(spec, folder, ["code/model.R"]) == 1
    assert spec["a"]["source"]["source_verified"] and not spec["b"][0]["source"]["source_verified"]


def test_analyze_writes_logic_spec(tiny_estate, fake_llm, tmp_path):
    """analyze saves logic_spec.json with the LLM spec, the static facts and the verification count."""
    folder, manifest = tiny_estate
    fake_llm[0]["analyze"] = SPEC_REPLY
    spec, response = analyze(manifest, folder, tmp_path)
    stored = json.loads((tmp_path / "logic_spec.json").read_text())
    assert stored["derived_variables"][0]["name"] == "ratio" and stored["unverified_sources"] == 0
    assert stored["static_facts"] and response.step == "analyze"
    assert "   2| d$ratio" in fake_llm[1][0]["user"]
