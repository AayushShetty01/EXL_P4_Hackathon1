"""Tests for the static safety check and the isolated runner."""

import pandas as pd
import pytest

from app.code_sandbox import UnsafeCodeError, check_code, count_pytest_outcomes, run_isolated, run_scoring, run_tests
from conftest import REFERENCE_MODEL


def test_import_os_is_rejected():
    """A file that imports os fails the static check."""
    assert any("'os'" in v for v in check_code("import os\nos.listdir('.')\n"))


@pytest.mark.parametrize("source", [
    "from subprocess import run\n", "import socket\n", "open('x')\n", "eval('1')\n",
    "x = (1).__class__\n", "import importlib\n", "from . import thing\n",
    "import pandas as pd\npd.read_pickle('x')\n", "import pandas as pd\npd.read_csv('/etc/hosts')\n",
    "import numpy as np\nnp.load('x')\n", "def f(df):\n    df.to_csv('/tmp/x')\n",
])
def test_forbidden_constructs_are_rejected(source):
    """Forbidden imports, calls and dunder access are all reported."""
    assert check_code(source)


def test_reference_model_is_accepted():
    """Ordinary pandas, numpy and statsmodels code passes the check."""
    assert check_code(REFERENCE_MODEL) == []


def test_tests_may_import_pytest_and_model():
    """Test files may import pytest and model, model files may not."""
    source = "import pytest\nimport model\n"
    assert check_code(source)
    assert check_code(source, {"pytest", "model"}) == []


def test_endless_loop_is_stopped_by_timeout():
    """An endless loop is stopped after the time limit."""
    result = run_isolated({"loop.py": "while True:\n    pass\n"}, ["loop.py"], timeout=2)
    assert result.timed_out
    assert "time limit" in result.stderr


def test_environment_is_clean(monkeypatch):
    """Secrets in the parent environment are not visible to the untrusted code."""
    monkeypatch.setenv("LLM_API_KEY", "secret-value")
    result = run_isolated({"env.py": "import os\nprint(os.environ.get('LLM_API_KEY'))\n"}, ["env.py"], timeout=30)
    assert result.stdout.strip() == "None"


def test_run_tests_counts_outcomes():
    """pytest runs in isolation and passed and failed tests are counted."""
    tests = "import model\n\ndef test_ok():\n    assert model.MODEL_ID == 'T001'\n\ndef test_bad():\n    assert False\n"
    _, passed, failed = run_tests(REFERENCE_MODEL, tests)
    assert (passed, failed) == (1, 1)


def test_run_tests_rejects_unsafe_model():
    """The model is checked before any test runs."""
    with pytest.raises(UnsafeCodeError):
        run_tests("import os\n", "def test_x():\n    pass\n")


def test_run_scoring_writes_outputs(tiny_estate, tmp_path):
    """Scoring in the sandbox writes both scored files and returns the refitted coefficients."""
    folder, _ = tiny_estate
    out = tmp_path / "scoring"
    result, refit = run_scoring(REFERENCE_MODEL, folder / "data" / "dev.csv", folder / "data" / "oot.csv", out)
    assert result.returncode == 0, result.stderr
    assert list(pd.read_csv(out / "scored_dev.csv").columns) == ["ID", "pd", "score", "decision"]
    assert set(refit) == {"Intercept", "woe", "x2"}


def test_pytest_summary_parsing():
    """The final summary line is parsed, other lines are ignored."""
    output = "FAILED test_model.py::test_a - 3 failed attempts\n2 failed, 5 passed, 1 error in 0.30s\n"
    assert count_pytest_outcomes(output) == (5, 3)
