"""Check timed scoring isolation, alignment and numeric shock evidence."""
import pandas as pd
import pytest
from app.config import LabError
from app.metrics.sensitivity import _checked_score, _has_unsupported_imports, measure, worker


@pytest.mark.parametrize("path", ["../outside.py", "/etc/passwd", "validation_lab/sample_data/dev.csv"])
def test_worker_rejects_untrusted_paths(repository, path):
    """The child re-validates the module path it receives on stdin."""
    with pytest.raises(LabError):
        worker({"path": path})


def test_shock_measurements(repository):
    """A linear probability scorer changes mean PD by exactly one hundredth."""
    source = '''"""Simple deterministic scorer for sensitivity tests."""
import numpy as np
import pandas as pd
def score(frame):
    """Return model outputs in reverse order to exercise ID alignment."""
    p = frame["x"] * .1
    return pd.DataFrame({"ID": frame["ID"], "pd": p, "decision": np.where(p < .15, "APPROVE", "DECLINE")}).iloc[::-1]
'''
    (repository / "model.py").write_text(source, encoding="utf-8")
    frame = pd.DataFrame({"ID": ["001", "002"], "x": [1., 1.]})
    result, error = measure("model.py", frame, ["x"], "ID", "pd", "decision")
    assert error is None, error
    assert abs(result["shocks"][0]["mean_pd_change"] - .01) < 1e-12
    assert result["shocks"][0]["decision_flip_rate"] == 0


def test_timeout_is_reported(repository, monkeypatch):
    """An endless scoring import produces an unavailable result within the time limit."""
    (repository / "model.py").write_text('"""Endless scorer test."""\nwhile True: pass\n')
    monkeypatch.setenv("SENSITIVITY_TIMEOUT", "2")
    result, error = measure("model.py", pd.DataFrame({"ID": ["1"], "x": [1.]}), ["x"], "ID", "pd", "decision")
    assert result is None and "timeout" in error


def test_network_import_rejected(repository):
    """Do not import a scorer that requests a networking module."""
    (repository / "model.py").write_text('"""Unsupported import test."""\nimport urllib.request\n')
    result, error = measure("model.py", pd.DataFrame({"ID": ["1"]}), [], "ID", "pd", "decision")
    assert result is None and "unsupported imports" in error


def test_measure_rejects_non_python_module(repository):
    """Only Python source files are executed as scorers."""
    with pytest.raises(LabError):
        measure("validation_lab/sample_data/dev.csv", pd.DataFrame(), [], "ID", "pd", "decision")


def test_from_import_outside_stack_is_unsupported():
    """From imports are checked against the permitted stack as well as plain imports."""
    assert _has_unsupported_imports("from os import path\n")
    assert not _has_unsupported_imports("from numpy import exp\nimport pandas as pd\n")


@pytest.mark.parametrize("output, message", [
    ({"ID": ["1"], "pd": [.1]}, "missing fields"),
    ({"ID": ["9"], "pd": [.1], "decision": ["APPROVE"]}, "mismatched IDs"),
    ({"ID": ["1"], "pd": [float("inf")], "decision": ["APPROVE"]}, "invalid probabilities"),
    ({"ID": ["1"], "pd": [.1], "decision": ["MAYBE"]}, "invalid decisions"),
])
def test_checked_score_rejects_bad_scorer_output(output, message):
    """Each malformed scorer output is rejected with its own reason."""
    class Scorer:
        """Stand-in scoring module returning a fixed frame."""
        @staticmethod
        def score(_data):
            """Return the canned output."""
            return pd.DataFrame(output)

    with pytest.raises(ValueError, match=message):
        _checked_score(Scorer, pd.DataFrame({"ID": ["1"]}), pd.Series(["1"]), "ID", "pd", "decision")
