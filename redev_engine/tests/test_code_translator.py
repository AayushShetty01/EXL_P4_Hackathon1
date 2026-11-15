"""Tests for the translator: coefficient injection, line mapping, notes and the LLM call."""

import ast

import pytest

from app.code_translator import build_line_mapping, inject_coefficients, legacy_coefficients, translate, write_notes
from conftest import REFERENCE_MODEL, SPEC_REPLY


def test_coefficients_are_injected_exactly():
    """The injected values round trip exactly and the rest of the file is kept."""
    code = inject_coefficients(REFERENCE_MODEL, {"Intercept": -0.34694060476323546, "woe": 1 / 3})
    module = ast.parse(code)
    assign = next(n for n in module.body if isinstance(n, ast.Assign) and n.targets[0].id == "DEPLOYED_COEFFICIENTS")
    assert ast.literal_eval(assign.value) == {"Intercept": -0.34694060476323546, "woe": 1 / 3}
    assert "def score(df, coefficients=None):" in code


def test_injection_needs_the_assignment():
    """A file without DEPLOYED_COEFFICIENTS is rejected."""
    with pytest.raises(ValueError):
        inject_coefficients("x = 1\n", {})


def test_line_mapping_from_source_comments(tiny_estate, tmp_path):
    """Every '# source:' comment becomes a mapping and invalid citations are reported."""
    folder, manifest = tiny_estate
    code = REFERENCE_MODEL + "\n# source: code/model.R L50 to L60 - does not exist\nx = 1\n"
    mapping, problems = build_line_mapping(code, tmp_path / "model.py", manifest, folder)
    assert [(m.legacy_start, m.legacy_end) for m in mapping] == [(2, 3), (4, 4), (5, 7)]
    assert mapping[0].note.startswith("ratio") and mapping[0].python_start < mapping[0].python_end < mapping[1].python_start
    assert len(problems) == 1 and "L50" in problems[0]


def test_translate_prompt_carries_interface_and_pitfalls(tiny_estate, fake_llm):
    """The prompt names the legacy coefficient names, the protected columns and the R pitfalls."""
    folder, manifest = tiny_estate
    fake_llm[0]["translate"] = {"model_code": REFERENCE_MODEL, "pitfalls_applied": [], "notes": ""}
    reply, _ = translate(manifest, folder, {"static_facts": [], **SPEC_REPLY}, use_pitfalls=True)
    prompt = fake_llm[1][0]["user"]
    assert "['Intercept', 'woe', 'x2']" in prompt and "['SEX']" in prompt and "R_CUT_INTERVALS" in prompt
    assert reply.model_code == REFERENCE_MODEL
    translate(manifest, folder, SPEC_REPLY, use_pitfalls=False)
    assert "R_CUT_INTERVALS" not in fake_llm[1][1]["user"]


def test_notes_list_pitfalls_and_open_questions(tiny_estate, tmp_path):
    """translation_notes.md lists applied pitfalls, open questions and unverified references."""
    folder, manifest = tiny_estate
    assert legacy_coefficients(manifest, folder)
    write_notes(tmp_path / "notes.md", manifest, SPEC_REPLY, ["R_CUT_INTERVALS"], "Rebuilt.", ["bad ref"])
    text = (tmp_path / "notes.md").read_text()
    assert "R_CUT_INTERVALS" in text and "Who set the 506 cutoff?" in text and "bad ref" in text
