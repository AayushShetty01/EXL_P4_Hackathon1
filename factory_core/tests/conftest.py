"""Shared fixtures: a temporary repository root per test, its database, an API client and a small estate."""

import dataclasses
import json
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session

from app.config import Settings, find_repository_root
from app.database import create_database_engine
from app.llm_client import LLMClient, ProviderReply
from app.main import create_app

REAL_REPOSITORY_ROOT = find_repository_root()
EXAMPLES_DIR = REAL_REPOSITORY_ROOT / "contracts" / "examples"
HERO_FOLDER = "model_estate/M001_cc_pd_scorecard_sas"
HERO_FILES = {
    "code/01_prepare.sas": (
        "/* 01_prepare.sas: build WoE variables */\n"
        "data work.dev_woe;\n"
        "  set raw.dev;\n"
        "  util = bill_amt1 / limit_bal;\n"
        "  if pay_0 <= 0 then woe_pay0 = -0.62;\n"
        "  else woe_pay0 = 1.35;\n"
        "run;\n"
    ),
    "code/02_train.sas": (
        "/* 02_train.sas */\n"
        "proc logistic data=work.dev_woe descending;\n"
        "  model default_flag = woe_pay0 woe_util;\n"
        "run;\n"
    ),
    "code/03_score.sas": (
        "/* 03_score.sas */\n"
        "data work.scored;\n"
        "  set work.dev_woe;\n"
        "  if score < 540 then decision = 'DECLINE';\n"
        "  else decision = 'APPROVE';\n"
        "run;\n"
    ),
    "docs/model_document_2021.md": (
        "# Credit Card PD Scorecard, model document 2021\n\n"
        "## Purpose\nEstimates the probability that a card customer defaults next month.\n\n"
        "## Decision rule\nApplications scoring below 520 are declined.\n"
    ),
    "data/data_dictionary.csv": (
        "column,description\nPAY_0,Repayment status in the most recent month\nLIMIT_BAL,Credit limit\n"
        "default_flag,Default next month\n"
    ),
    "data/dev.csv": "ID,PAY_0,LIMIT_BAL,BILL_AMT1,PAY_AMT1,SEX,AGE_BAND,default_flag\n1,0,20000,3913,0,2,25-34,1\n",
    "data/oot.csv": "ID,PAY_0,LIMIT_BAL,BILL_AMT1,PAY_AMT1,SEX,AGE_BAND,default_flag\n2,-1,120000,2682,0,2,25-34,0\n",
}
REGISTER_HEADER = (
    "model_id,model_name,business_line,model_owner,exposure_gbp_m,customer_facing,"
    "regulatory_use,last_code_change,doc_last_updated,last_validated,status\n"
)


def load_example(file_name: str) -> dict:
    """Read one contract example file."""
    return json.loads((EXAMPLES_DIR / file_name).read_text(encoding="utf-8"))


class ScriptedProvider:
    """Fake LLM provider: answers with the reply of the first rule whose key appears in the prompt."""

    def __init__(self, rules: dict[str, str | Callable[[str, str], str]]) -> None:
        """Keep the rules in order; a rule value is a reply text or a function of (system, user)."""
        self.rules = rules
        self.prompts: list[tuple[str, str]] = []

    def __call__(self, model: str, system: str, user: str, temperature: float) -> ProviderReply:
        """Answer one call, or fail loudly when no rule matches."""
        self.prompts.append((system, user))
        for key, reply in self.rules.items():
            if key in system or key in user:
                text = reply(system, user) if callable(reply) else reply
                return ProviderReply(text=text, model=model, input_tokens=100, output_tokens=50)
        raise AssertionError(f"No scripted reply for prompt starting {user[:80]!r}")


def live_settings(settings: Settings) -> Settings:
    """Settings in live mode with a test model id and a dummy key."""
    return dataclasses.replace(settings, llm_mode="live", llm_model="test-model", llm_api_key="dummy-key")


def scripted_llm(settings: Settings, provider: ScriptedProvider, on_call=None) -> LLMClient:
    """An LLM client in live mode that answers from a scripted provider."""
    return LLMClient(live_settings(settings), provider=provider, on_call=on_call)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings that point at an empty temporary repository root and the real contract examples."""
    (tmp_path / "model_estate").mkdir()
    return Settings(
        repository_root=tmp_path,
        estate_dir=tmp_path / "model_estate",
        artifacts_dir=tmp_path / "artifacts",
        contracts_examples_dir=EXAMPLES_DIR,
        database_path=tmp_path / "artifacts" / "factory_core.db",
        checkpoints_path=tmp_path / "artifacts" / "pipeline_checkpoints.db",
        llm_cache_dir=tmp_path / "llm_cache",
        llm_base_url="",
        llm_api_key="",
        llm_model="",
        llm_model_validator="",
        llm_mode="replay",
        llm_temperature=0.0,
        redev_engine_url="http://redev-engine.test",
        validation_lab_url="http://validation-lab.test",
        use_stubs=True,
        mlflow_tracking_uri="",
    )


@pytest.fixture
def engine(settings: Settings) -> Engine:
    """A fresh database for one test."""
    return create_database_engine(settings.database_path)


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    """A database session for one test."""
    with Session(engine) as database_session:
        yield database_session


@pytest.fixture
def hero_estate(settings: Settings) -> Settings:
    """Write the M001 folder of the contract manifest, a register row and an answer key to the estate."""
    manifest = load_example("estate_manifest.M001.json")
    folder = settings.repository_root / manifest["folder"]
    for name, content in HERO_FILES.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(content)
    (folder / "manifest.json").write_text(json.dumps(manifest))
    (settings.estate_dir / "estate_register.csv").write_text(
        REGISTER_HEADER
        + "M001,Credit Card PD Scorecard,Cards,Head of Cards Credit Risk,1850,true,IRB,"
        + "2023-06-20,2021-03-01,2023-02-14,Production\n"
    )
    (settings.estate_dir / "_answer_keys").mkdir()
    (settings.estate_dir / "_answer_keys" / "M001.json").write_text('{"secret": true}')
    return settings


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    """API client on an app whose estate is empty, so the built-in sample model is registered."""
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def estate_client(hero_estate: Settings) -> Iterator[TestClient]:
    """API client on an app whose estate holds the M001 folder."""
    with TestClient(create_app(hero_estate)) as test_client:
        yield test_client


def hero_evidence(file: str, quote: str, line: int) -> dict:
    """Evidence that points at one line of a file in the hero model folder."""
    return {"file": f"{HERO_FOLDER}/{file}", "start_line": line, "end_line": line, "quote": quote}


PIPELINE_DISCOVERY = {
    "model_name": "Card default scorecard",
    "model_type": "credit_pd",
    "purpose": "Estimates the probability that a card customer defaults next month.",
    "algorithm": "Logistic regression scorecard on WoE variables",
    "target_variable": "default_flag",
    "input_variables": [{"name": "PAY_0", "description": "Recent repayment status", "transformation": "WoE bins"}],
    "outputs": ["pd", "score", "decision"],
    "upstream_dependencies": [],
    "downstream_uses": ["Card approve or decline decision"],
    "open_questions": [],
    "evidence": {
        "algorithm": hero_evidence("code/02_train.sas", "proc logistic data=work.dev_woe descending;", 2),
        "target_variable": hero_evidence("code/02_train.sas", "model default_flag = woe_pay0 woe_util;", 3),
        "downstream_uses": hero_evidence("code/03_score.sas", "if score < 540 then decision = 'DECLINE';", 4),
    },
}
PIPELINE_DRIFT = {
    "differences": [
        {
            "topic": "Decision cutoff",
            "severity": "HIGH",
            "legacy_doc_says": "Applications scoring below 520 are declined.",
            "code_says": "The cutoff in the scoring code is 540.",
            "legacy_evidence": hero_evidence("docs/model_document_2021.md", "scoring below 520 are declined", 7),
            "code_evidence": hero_evidence("code/03_score.sas", "if score < 540 then decision = 'DECLINE';", 4),
        }
    ]
}
GROUNDED_NARRATIVE = {
    "executive_summary": "The model is rated AMBER. On the holdout sample the AUC is 0.764 and the Gini is 0.528.",
    "conceptual_soundness": "A logistic regression scorecard is a standard and explainable approach for this use.",
    "findings_commentary": "There is 1 medium finding: the Hosmer Lemeshow p value of 0.0055 is below 0.05. "
    "These thresholds are illustrative defaults, not regulatory limits.",
    "conclusion": "The model can remain in use while calibration is reviewed.",
}


def pipeline_section_reply(system: str, user: str) -> str:
    """One verified claim per documentation section."""
    claim = "The model is fitted with PROC LOGISTIC."
    evidence = hero_evidence("code/02_train.sas", "proc logistic data=work.dev_woe descending;", 2)
    return json.dumps({"markdown": claim + "{{claim:1}}", "claims": [{"text": claim, "evidence": [evidence]}]})


def pipeline_provider() -> ScriptedProvider:
    """Scripted replies for every agent of a full pipeline run on the hero model."""
    return ScriptedProvider(
        {
            "discovery agent": json.dumps(PIPELINE_DISCOVERY),
            "Section to write": pipeline_section_reply,
            "old model document": json.dumps(PIPELINE_DRIFT),
            "independent model validator": json.dumps(GROUNDED_NARRATIVE),
        }
    )


@pytest.fixture
def pipeline_client(hero_estate: Settings) -> Iterator[TestClient]:
    """API client with the estate, a scripted LLM, stubbed services and runs executed inline."""
    app = create_app(live_settings(hero_estate), llm_provider=pipeline_provider(), background=False)
    with TestClient(app) as test_client:
        yield test_client


def decide(
    client: TestClient, run_id: str, stage: str, reviewer: str, decision: str = "approve", role: str = "developer"
):
    """Post one gate decision and return the response."""
    body = {"decision": decision, "reviewer": reviewer, "role": role, "comment": f"{decision} by {reviewer}"}
    return client.post(f"/api/runs/{run_id}/gates/{stage}/decision", json=body)


def stage_statuses(client: TestClient, run_id: str) -> dict[str, str]:
    """Status of every stage of a run."""
    return {stage["stage"]: stage["status"] for stage in client.get(f"/api/runs/{run_id}").json()["stages"]}
