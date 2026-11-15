"""Tests for optional MLflow tracking."""

import importlib.util

import pytest

from app.mlflow_logger import log_run
from app.schemas import RedevelopResult

RESULT = RedevelopResult(model_id="M001", run_id="r", status="PARITY_FAILED", source_language="SAS")


def test_nothing_is_logged_without_a_tracking_uri(settings_env, tmp_path):
    """Without MLFLOW_TRACKING_URI the logger does nothing."""
    assert log_run(RESULT, tmp_path) is None


@pytest.mark.skipif(importlib.util.find_spec("mlflow") is not None, reason="mlflow is installed")
def test_missing_package_is_reported_not_raised(settings_env, monkeypatch, tmp_path):
    """A tracking URI without the mlflow package gives an error entry, never an exception."""
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "file:///tmp/none")
    assert "not installed" in log_run(RESULT, tmp_path)["error"]
