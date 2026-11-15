"""Tests for the full redevelopment flow with a scripted LLM and the tiny synthetic estate."""

import json

import pytest

from app.redevelop_pipeline import PipelineError, load_manifest, redevelop
from app.schemas import RedevelopRequest
from conftest import PASSING_TESTS, REFERENCE_MODEL, ROUNDING_BUG_MODEL, SPEC_REPLY


def request_for(folder, heal=3):
    """A redevelop request for the tiny model."""
    return RedevelopRequest(run_id="run_T001_001", model_id="T001", estate_path=str(folder), max_heal_iterations=heal)


def script_replies(script, first_model, healed_model=REFERENCE_MODEL):
    """Script analyze, translate, write_tests and heal replies."""
    script.update({
        "analyze": SPEC_REPLY,
        "translate": {"model_code": first_model, "pitfalls_applied": ["R_CUT_INTERVALS"], "notes": "Rebuilt ratio, bin, fit and score."},
        "write_tests": {"test_code": PASSING_TESTS},
        "heal": {"diagnosis": "All score mismatches are halves rounded to even.", "fix_applied": "Round half away from zero.",
                 "model_code": healed_model},
    })


def test_heal_loop_reaches_parity(tiny_estate, fake_llm):
    """A rounding bug fails iteration 1, the healer fixes it and iteration 2 passes every level."""
    folder, _ = tiny_estate
    script, calls = fake_llm
    script_replies(script, ROUNDING_BUG_MODEL)
    result = redevelop(request_for(folder))
    assert result.status == "PARITY_PASSED", result.error
    assert [it.parity_passed for it in result.iterations] == [False, True]
    assert result.iterations[0].unit_tests_failed == 1 and result.iterations[0].diagnosis
    assert result.unit_tests.passed == 2 and result.unit_tests.failed == 0
    assert result.parity.passed and result.parity.certificate_md_path.endswith("parity_certificate.md")
    assert [c["step"] for c in calls] == ["analyze", "translate", "write_tests", "heal_1"]
    heal_prompt = calls[-1]["user"]
    assert "exactly 1 point" in heal_prompt and "score_legacy" in heal_prompt
    kinds = {f.kind for f in result.generated_files}
    assert {"model_code", "unit_tests", "logic_spec", "notes", "scores_dev", "scores_oot", "certificate_md"} <= kinds
    assert len(result.line_mapping) == 3 and len(result.llm_trace) == 4


def test_legacy_coefficients_are_injected_by_code(tiny_estate, fake_llm, settings_env):
    """model.py holds the legacy estimates from coefficients_legacy.csv, not values from the LLM."""
    folder, _ = tiny_estate
    script_replies(fake_llm[0], REFERENCE_MODEL)
    redevelop(request_for(folder))
    code = (settings_env / "artifacts" / "T001" / "redevelop" / "model.py").read_text()
    assert "DEPLOYED_COEFFICIENTS = {\n    'Intercept': " in code


def test_failure_is_reported_honestly(tiny_estate, fake_llm, settings_env):
    """When healing never fixes the model the status is PARITY_FAILED and result.json says so."""
    folder, _ = tiny_estate
    script_replies(fake_llm[0], ROUNDING_BUG_MODEL, healed_model=ROUNDING_BUG_MODEL)
    result = redevelop(request_for(folder, heal=2))
    assert result.status == "PARITY_FAILED"
    assert len(result.iterations) == 3 and not result.parity.passed
    assert result.parity.mismatch_sample_path
    stored = json.loads((settings_env / "artifacts" / "T001" / "redevelop" / "result.json").read_text())
    assert stored["status"] == "PARITY_FAILED"


def test_no_golden_gives_translated_no_golden(tiny_estate, fake_llm):
    """Without legacy outputs the honest status is TRANSLATED_NO_GOLDEN."""
    folder, manifest = tiny_estate
    (folder / "manifest.json").write_text(json.dumps({**manifest, "golden": None}))
    script_replies(fake_llm[0], REFERENCE_MODEL)
    result = redevelop(request_for(folder))
    assert result.status == "TRANSLATED_NO_GOLDEN"
    assert result.parity.certificate_md_path is None


def test_unsafe_model_ends_in_error(tiny_estate, fake_llm):
    """A model that keeps importing os is never run and the status is ERROR."""
    folder, _ = tiny_estate
    unsafe = "import os\n" + REFERENCE_MODEL
    script_replies(fake_llm[0], unsafe, healed_model=unsafe)
    result = redevelop(request_for(folder, heal=1))
    assert result.status == "ERROR" and result.error.code == "SCORING_FAILED"
    assert "not allowed" in result.error.message


def test_replay_without_cache_is_an_llm_error(tiny_estate):
    """In replay mode a missing cache entry gives status ERROR with code LLM_ERROR."""
    folder, _ = tiny_estate
    result = redevelop(request_for(folder))
    assert result.status == "ERROR" and result.error.code == "LLM_ERROR"


def test_paths_outside_the_estate_are_rejected(settings_env):
    """estate_path may not leave the estate folder."""
    with pytest.raises(PipelineError) as error:
        load_manifest("../../etc")
    assert error.value.code == "INVALID_PATH"
