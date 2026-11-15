"""Tests for the four level parity engine with small synthetic data."""

import pandas as pd

from app.parity_engine import psi, run_parity
from conftest import MISSING_BUG_MODEL, REFERENCE_MODEL, ROUNDING_BUG_MODEL, load_module


def score_with(source, folder, manifest, tmp_path, coefficients=None, drop_ids=0):
    """Score dev and oot with a model variant, write the files and run parity."""
    model = load_module(source)
    legacy = pd.read_csv(folder / "golden" / "coefficients_legacy.csv")
    deployed = coefficients or dict(zip(legacy["variable"], legacy["estimate"]))
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    for name in ("dev", "oot"):
        scored = model.score(pd.read_csv(folder / "data" / f"{name}.csv"), deployed)
        scored.iloc[drop_ids:].to_csv(out / f"scored_{name}.csv", index=False, float_format="%.17g")
    refit = model.fit(pd.read_csv(folder / "data" / "dev.csv"))["coefficients"]
    (out / "model.py").write_text(source)
    return run_parity(manifest, folder, out / "scored_dev.csv", out / "scored_oot.csv", refit, out / "model.py", out)


def statuses(outcome):
    """Map of level name to status."""
    return {level.level: level.status for level in outcome.parity.levels}


def test_identical_model_passes_all_levels(tiny_estate, tmp_path):
    """The reference rebuild matches the legacy outputs on all four levels."""
    folder, manifest = tiny_estate
    outcome = score_with(REFERENCE_MODEL, folder, manifest, tmp_path)
    assert outcome.parity.passed
    assert set(statuses(outcome).values()) == {"PASSED"}
    assert outcome.parity.records_compared == 450
    assert outcome.parity.mismatch_sample_path is None
    assert outcome.parity.hashes.golden_output_sha256 and outcome.parity.hashes.python_code_sha256


def test_flipped_sign_fails_l2(tiny_estate, tmp_path):
    """A model with one coefficient sign flipped fails record level PD parity."""
    folder, manifest = tiny_estate
    legacy = pd.read_csv(folder / "golden" / "coefficients_legacy.csv")
    flipped = dict(zip(legacy["variable"], legacy["estimate"]))
    flipped["woe"] = -flipped["woe"]
    outcome = score_with(REFERENCE_MODEL, folder, manifest, tmp_path, coefficients=flipped)
    assert statuses(outcome)["L2_record_scores"] == "FAILED"
    assert not outcome.parity.passed
    assert (tmp_path / "out" / "mismatches.csv").exists()


def test_different_rounding_rule_fails_l3(tiny_estate, tmp_path):
    """Rounding halves to even instead of away from zero keeps PD equal but changes score points."""
    folder, manifest = tiny_estate
    outcome = score_with(ROUNDING_BUG_MODEL, folder, manifest, tmp_path)
    assert statuses(outcome)["L2_record_scores"] == "PASSED"
    assert statuses(outcome)["L3_decisions"] == "FAILED"
    mismatches = pd.read_csv(tmp_path / "out" / "mismatches.csv")
    assert {"x1", "x2", "score_legacy", "score_python"} <= set(mismatches.columns)


def test_missing_ids_fail_l2(tiny_estate, tmp_path):
    """Records missing from the Python output fail L2 even when the rest matches."""
    folder, manifest = tiny_estate
    outcome = score_with(REFERENCE_MODEL, folder, manifest, tmp_path, drop_ids=3)
    level = next(lv for lv in outcome.parity.levels if lv.level == "L2_record_scores")
    assert level.status == "FAILED"
    assert "one side only" in level.detail


def test_missing_value_bug_fails_l2(tiny_estate, tmp_path):
    """Treating a missing ratio like pandas (comparison false) changes PD for zero denominators."""
    folder, manifest = tiny_estate
    assert statuses(score_with(MISSING_BUG_MODEL, folder, manifest, tmp_path))["L2_record_scores"] == "FAILED"


def test_refit_outside_tolerance_fails_l1(tiny_estate, tmp_path):
    """L1 fails when a refitted coefficient is off by more than the tolerance."""
    folder, manifest = tiny_estate
    outcome = score_with(REFERENCE_MODEL.replace('float(v) for k, v', 'float(v) + 1e-3 for k, v'), folder, manifest, tmp_path)
    assert statuses(outcome)["L1_coefficients"] == "FAILED"


def test_no_golden_is_not_applicable(tiny_estate, tmp_path):
    """Without legacy outputs every level is NOT_APPLICABLE and parity is not passed."""
    folder, manifest = tiny_estate
    outcome = score_with(REFERENCE_MODEL, folder, {**manifest, "golden": None}, tmp_path)
    assert set(statuses(outcome).values()) == {"NOT_APPLICABLE"}
    assert not outcome.parity.passed


def test_psi_is_zero_for_identical_and_positive_for_shifted():
    """PSI is exactly zero for identical samples and positive after a shift."""
    values = pd.Series(range(1000), dtype=float).to_numpy()
    assert psi(values, values) == 0.0
    assert psi(values, values + 300) > 0.1
