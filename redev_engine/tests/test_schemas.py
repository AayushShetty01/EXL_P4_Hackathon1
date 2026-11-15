"""Tests that the schemas accept the contract example of section 9.1."""

from app.schemas import RedevelopRequest, RedevelopResult

EXAMPLE = {
    "model_id": "M001", "run_id": "run_M001_001", "status": "PARITY_PASSED", "source_language": "SAS", "target_language": "Python",
    "iterations": [{"iteration": 1, "unit_tests_passed": 12, "unit_tests_failed": 2, "parity_passed": False,
                    "max_abs_diff_pd": 0.4127, "diagnosis": "text", "fix_applied": "text"}],
    "generated_files": [{"path": "artifacts/M001/redevelop/model.py", "kind": "model_code"}],
    "line_mapping": [{"legacy_file": "model_estate/M001_cc_pd_scorecard_sas/code/01_prepare.sas", "legacy_start": 22, "legacy_end": 31,
                      "python_file": "artifacts/M001/redevelop/model.py", "python_start": 40, "python_end": 52, "note": "WoE"}],
    "unit_tests": {"total": 14, "passed": 14, "failed": 0},
    "parity": {"passed": True, "records_compared": 30000, "tolerance_pd": 1e-6, "tolerance_coef": 1e-4,
               "levels": [{"level": "L1_coefficients", "status": "PASSED", "max_abs_diff": 2.2e-6, "mismatched_records": None,
                           "match_rate": None, "psi": None, "detail": "9 of 9"}],
               "hashes": {"legacy_code_sha256": "9f2c", "python_code_sha256": "41ab", "input_data_sha256": "c07e", "golden_output_sha256": "5d90"},
               "certificate_md_path": "a.md", "certificate_json_path": "a.json", "mismatch_sample_path": None},
    "pitfalls_checked": ["SAS_MISSING_COMPARE"], "mlflow": None,
    "llm_trace": [{"step": "analyze", "model": "provider/model-id", "prompt_sha256": "ab12", "input_tokens": 5210,
                   "output_tokens": 1830, "latency_ms": 9100, "cached": False}],
    "duration_seconds": 96.4, "error": None,
}


def test_contract_example_round_trips():
    """The contract example validates and serialises back to the same content."""
    assert RedevelopResult.model_validate(EXAMPLE).model_dump(mode="json") == EXAMPLE


def test_request_defaults():
    """max_heal_iterations defaults to 3 and the pitfall library is on."""
    request = RedevelopRequest(run_id="r", model_id="M001", estate_path="model_estate/M001_cc_pd_scorecard_sas")
    assert request.max_heal_iterations == 3 and request.use_pitfall_library
