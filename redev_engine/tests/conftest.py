"""Shared fixtures: isolated settings and a tiny synthetic estate with a known correct rebuild."""

import json
import types

import numpy as np
import pandas as pd
import pytest

REFERENCE_MODEL = '''"""Python rebuild of model T001. Legacy sources: code/model.R."""
import numpy as np
import pandas as pd
import statsmodels.api as sm

MODEL_ID = "T001"
INPUT_COLUMNS = ["x1", "x2"]
DEPLOYED_COEFFICIENTS = {}


# source: code/model.R L2 to L3 - ratio, missing when x2 is zero, missing goes to the low bin
def prepare(df):
    """Model variables from raw columns."""
    ratio = df["x1"] / df["x2"].replace(0, np.nan)
    woe = np.where(ratio.fillna(-np.inf) < 0.5, -0.5, 0.4)
    return pd.DataFrame({"ID": df["ID"], "woe": woe, "x2": df["x2"]})


def sas_round(x):
    """Round half away from zero."""
    return np.sign(x) * np.floor(np.abs(x) + 0.5)


# source: code/model.R L4 to L4 - logistic fit
def fit(dev_df):
    """Re-estimate the coefficients."""
    X = prepare(dev_df)[["woe", "x2"]].astype(float)
    X.insert(0, "Intercept", 1.0)
    result = sm.Logit(dev_df["target"], X).fit(disp=0, method="newton", tol=1e-12, maxiter=100)
    return {"coefficients": {k: float(v) for k, v in result.params.items()}}


# source: code/model.R L5 to L7 - pd, points and decision
def score(df, coefficients=None):
    """Score with the deployed coefficients."""
    c = coefficients or DEPLOYED_COEFFICIENTS
    m = prepare(df)
    xb = c["Intercept"] + c["woe"] * m["woe"] + c["x2"] * m["x2"]
    points = sas_round(500 + 1.5 * m["x2"])
    return pd.DataFrame({"ID": m["ID"], "pd": 1 / (1 + np.exp(-xb)), "score": points.astype(int),
                         "decision": np.where(points < 506, "DECLINE", "APPROVE")})
'''

ROUNDING_BUG_MODEL = REFERENCE_MODEL.replace("points = sas_round(500", "points = np.round(500")
MISSING_BUG_MODEL = REFERENCE_MODEL.replace("ratio.fillna(-np.inf) < 0.5", "ratio < 0.5")

LEGACY_R = """d <- read.csv("data/dev.csv")
d$ratio <- d$x1 / d$x2
d$woe <- ifelse(is.na(d$ratio) | d$ratio < 0.5, -0.5, 0.4)
fit <- glm(target ~ woe + x2, family = binomial, data = d)
p <- predict(fit, type = "response")
pts <- 500 + 1.5 * d$x2
dec <- ifelse(pts < 506, "DECLINE", "APPROVE")
"""


def load_module(source: str) -> types.ModuleType:
    """Load model code as a module (trusted test code only)."""
    module = types.ModuleType("reference_model")
    exec(compile(source, "reference_model.py", "exec"), module.__dict__)
    return module


def make_data(seed: int, n: int, start_id: int) -> pd.DataFrame:
    """Synthetic rows with zero denominators and both sexes."""
    rng = np.random.default_rng(seed)
    x2 = rng.integers(0, 10, n)
    x1 = rng.uniform(0, 8, n).round(2)
    logit = -0.5 + 0.8 * (x1 / np.where(x2 == 0, 1, x2) < 0.5) + 0.1 * x2
    target = rng.binomial(1, 1 / (1 + np.exp(-logit)))
    return pd.DataFrame({"ID": np.arange(start_id, start_id + n), "x1": x1, "x2": x2, "SEX": rng.integers(1, 3, n), "target": target})


@pytest.fixture
def settings_env(tmp_path, monkeypatch):
    """Point estate, artifacts and LLM cache at temporary folders and use replay mode by default."""
    monkeypatch.setenv("ESTATE_DIR", str(tmp_path / "estate"))
    monkeypatch.setenv("ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("REDEV_LLM_CACHE_DIR", str(tmp_path / "llm_cache"))
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_MODE", "replay")
    monkeypatch.setenv("REDEV_STUB", "false")
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "")
    return tmp_path


@pytest.fixture
def tiny_estate(settings_env):
    """A model folder T001 with code, data, golden outputs from the reference model, and its manifest."""
    folder = settings_env / "estate" / "T001_tiny_r"
    for sub in ("code", "data", "golden"):
        (folder / sub).mkdir(parents=True)
    (folder / "code" / "model.R").write_text(LEGACY_R)
    dev, oot = make_data(1, 300, 1), make_data(2, 150, 1001)
    dev.to_csv(folder / "data" / "dev.csv", index=False)
    oot.to_csv(folder / "data" / "oot.csv", index=False)
    pd.DataFrame({"column": ["ID", "x1", "x2", "SEX", "target"],
                  "description": ["id", "amount", "count", "sex", "target"],
                  "role": ["id", "input", "input", "protected", "target"]}).to_csv(folder / "data" / "data_dictionary.csv", index=False)
    reference = load_module(REFERENCE_MODEL)
    coefficients = reference.fit(dev)["coefficients"]
    pd.DataFrame({"variable": list(coefficients), "estimate": list(coefficients.values())}).to_csv(
        folder / "golden" / "coefficients_legacy.csv", index=False, float_format="%.17g")
    for name, frame in (("dev", dev), ("oot", oot)):
        reference.score(frame, coefficients).to_csv(folder / "golden" / f"scored_{name}_legacy.csv", index=False, float_format="%.17g")
    manifest = {
        "model_id": "T001", "folder": str(folder), "language": "R", "code_files": ["code/model.R"], "doc_files": [],
        "data": {"dev_path": "data/dev.csv", "oot_path": "data/oot.csv", "dictionary_path": "data/data_dictionary.csv",
                 "id_col": "ID", "target_col": "target", "protected_cols": ["SEX"]},
        "golden": {"scored_dev_path": "golden/scored_dev_legacy.csv", "scored_oot_path": "golden/scored_oot_legacy.csv",
                   "coefficients_path": "golden/coefficients_legacy.csv", "produced_by": "test", "produced_on": "2026-11-15"},
        "redevelop": True,
    }
    (folder / "manifest.json").write_text(json.dumps(manifest))
    return folder, manifest


PASSING_TESTS = '''"""Unit tests for the Python rebuild of model T001."""
import pandas as pd

import model


def test_zero_denominator_goes_to_low_bin():
    """A zero x2 gives a missing ratio, which falls in the low bin as in the legacy code."""
    frame = pd.DataFrame({"ID": [1], "x1": [1.0], "x2": [0]})
    assert model.prepare(frame)["woe"].iloc[0] == -0.5


def test_half_points_round_away_from_zero():
    """504.5 points round to 505, as the legacy rounding does."""
    frame = pd.DataFrame({"ID": [1], "x1": [1.0], "x2": [3]})
    assert model.score(frame, {"Intercept": 0.0, "woe": 0.0, "x2": 0.0})["score"].iloc[0] == 505
'''

SPEC_REPLY = {"inputs": ["x1", "x2"], "derived_variables": [{"name": "ratio", "expression": "x1 / x2",
              "missing_rule": "missing when x2 is 0", "source": {"file": "code/model.R", "start_line": 2, "end_line": 2}}],
              "open_questions": ["Who set the 506 cutoff?"]}


@pytest.fixture
def fake_llm(monkeypatch):
    """Replace llm_client.complete with scripted replies keyed by step; returns the list of calls made."""
    from app import llm_client

    calls, script = [], {}

    def complete(system, user, *, json_mode=False, step="", model=None, response_model=None):
        """Return the next scripted reply for this step."""
        calls.append({"step": step, "user": user})
        key = next(k for k in script if step.startswith(k))
        reply = script[key].pop(0) if isinstance(script[key], list) else script[key]
        text = json.dumps(reply)
        response = llm_client.LLMResponse(text, "test-model", 10, 20, 5, False, "ab" * 32, step)
        response.parsed = response_model.model_validate(reply) if response_model else None
        return response

    monkeypatch.setattr(llm_client, "complete", complete)
    return script, calls
