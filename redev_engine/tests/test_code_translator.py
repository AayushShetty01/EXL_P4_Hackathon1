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


def deployed_value(code):
    """Literal value of the plain DEPLOYED_COEFFICIENTS assignment in the code."""
    module = ast.parse(code)
    assign = next(n for n in module.body if isinstance(n, ast.Assign) and n.targets[0].id == "DEPLOYED_COEFFICIENTS")
    return ast.literal_eval(assign.value)


def test_annotated_empty_dict_is_injected_exactly():
    """An annotated empty assignment is replaced by the plain injected one."""
    code = "from typing import Dict\n\nDEPLOYED_COEFFICIENTS: Dict[str, float] = {}\n\nx = 1\n"
    injected = inject_coefficients(code, {"Intercept": 0.1, "woe": 1 / 3})
    assert deployed_value(injected) == {"Intercept": 0.1, "woe": 1 / 3}
    assert "Dict[str, float]" not in injected and "x = 1" in injected


def test_annotated_multiline_dict_is_replaced_completely():
    """An annotated dict over several lines is replaced in full, nothing of the old value is left."""
    code = 'DEPLOYED_COEFFICIENTS: dict[str, float] = {\n    "old_a": 9.0,\n    "old_b": 8.0,\n}\ny = 2\n'
    injected = inject_coefficients(code, {"Intercept": -0.5})
    assert deployed_value(injected) == {"Intercept": -0.5}
    assert "old_" not in injected and injected.endswith("y = 2\n")


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


def test_translate_prompt_requires_a_converging_fit_and_raw_scoring(tiny_estate, fake_llm):
    """The interface says fit() converges with Newton or IRLS and score() takes raw data and calls prepare()."""
    folder, manifest = tiny_estate
    fake_llm[0]["translate"] = {"model_code": REFERENCE_MODEL, "pitfalls_applied": [], "notes": ""}
    translate(manifest, folder, SPEC_REPLY, use_pitfalls=False)
    prompt = fake_llm[1][0]["user"]
    assert "sm.GLM(y, X, family=sm.families.Binomial()).fit()" in prompt and 'method="newton"' in prompt
    assert "Never the default BFGS" in prompt
    assert "score() receives the raw data (the columns of the data file) and calls prepare() itself." in prompt


def test_notes_list_pitfalls_and_open_questions(tiny_estate, tmp_path):
    """translation_notes.md lists applied pitfalls, open questions and unverified references."""
    folder, manifest = tiny_estate
    assert legacy_coefficients(manifest, folder)
    write_notes(tmp_path / "notes.md", manifest, SPEC_REPLY, ["R_CUT_INTERVALS"], "Rebuilt.", ["bad ref"])
    text = (tmp_path / "notes.md").read_text()
    assert "R_CUT_INTERVALS" in text and "Who set the 506 cutoff?" in text and "bad ref" in text
