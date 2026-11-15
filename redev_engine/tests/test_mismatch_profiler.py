"""Tests for the mismatch profiler."""

import pandas as pd

from app.mismatch_profiler import profile
from conftest import MISSING_BUG_MODEL, REFERENCE_MODEL, ROUNDING_BUG_MODEL
from test_parity_engine import score_with


def run_profile(source, tiny_estate, tmp_path):
    """Score with a model variant and profile the mismatches."""
    folder, manifest = tiny_estate
    outcome = score_with(source, folder, manifest, tmp_path)
    data = pd.concat([pd.read_csv(folder / "data" / f) for f in ("dev.csv", "oot.csv")])
    return profile(outcome.comparison, data, "ID", ["x1", "x2"])


def test_missing_value_bug_points_at_zero_denominator(tiny_estate, tmp_path):
    """Mismatches from the missing value bug concentrate where x2 equals 0."""
    report = run_profile(MISSING_BUG_MODEL, tiny_estate, tmp_path)
    assert report["mismatched_records"] > 0
    assert any("x2 equal to 0" in f for f in report["findings"])


def test_rounding_bug_is_recognised(tiny_estate, tmp_path):
    """Score differences of exactly one point are reported as a rounding pattern."""
    report = run_profile(ROUNDING_BUG_MODEL, tiny_estate, tmp_path)
    assert any("exactly 1 point" in f for f in report["findings"])


def test_no_mismatches_no_findings(tiny_estate, tmp_path):
    """A matching model gives no findings."""
    assert run_profile(REFERENCE_MODEL, tiny_estate, tmp_path) == {"mismatched_records": 0, "records_compared": 450, "findings": []}
