"""The discovery agent: static signals, LLM fields with verified evidence, register facts and tiering."""

import json
from datetime import date

import pytest
from sqlalchemy import Engine
from sqlmodel import Session

from app.agents.discovery_agent import run_discovery, static_signals
from app.agents.source_context import source_paths
from app.audit_trail import AuditRecorder, list_events
from app.config import Settings
from app.database import ModelRow
from app.estate_scanner import register_estate
from app.llm_client import LLMClient, LLMReplayMissError
from tests.conftest import HERO_FOLDER, ScriptedProvider, scripted_llm

PENDING = dict.fromkeys(("discover", "document", "redevelop", "validate", "monitor"), "PENDING")


def evidence(file: str, quote: str, start: int = 1, end: int = 1) -> dict:
    """One evidence object as the agent returns it."""
    return {"file": f"{HERO_FOLDER}/{file}", "start_line": start, "end_line": end, "quote": quote}


DISCOVERY_REPLY = {
    "model_name": "Card default scorecard",
    "model_type": "credit_pd",
    "purpose": "Estimates the probability that a card customer defaults next month.",
    "algorithm": "Logistic regression on WoE variables",
    "target_variable": "default_flag",
    "input_variables": [{"name": "PAY_0", "description": "Recent repayment status", "transformation": "WoE bins"}],
    "outputs": ["pd", "score", "decision"],
    "upstream_dependencies": [],
    "downstream_uses": ["Card approve or decline decision"],
    "open_questions": ["Who approved the decision cutoff?"],
    "evidence": {
        "algorithm": evidence("code/02_train.sas", "proc logistic data=work.dev_woe descending;", 2, 2),
        "target_variable": evidence("code/02_train.sas", "model default_flag = woe_pay0 woe_util;", 9, 9),
        "purpose": evidence("docs/model_document_2021.md", "Estimates the probability that a card customer defaults"),
        "input_variables": evidence("code/01_prepare.sas", "if pay_0 <= 0 then woe_pay0 = -0.62;", 5, 5),
        "outputs": evidence("code/03_score.sas", "if score < 540 then decision = 'DECLINE';", 4, 4),
        "downstream_uses": evidence("code/03_score.sas", "else decision = 'APPROVE';", 5, 5),
        "model_type": evidence("code/02_train.sas", "this sentence is not in the file"),
        "model_name": {
            "file": "model_estate/_answer_keys/M001.json",
            "start_line": 1,
            "end_line": 1,
            "quote": "secret",
        },
    },
}


@pytest.fixture
def hero_model(hero_estate: Settings, session: Session) -> ModelRow:
    """The registered M001 model of the test estate."""
    register_estate(session, hero_estate)
    return session.get(ModelRow, "M001")


def discover(settings: Settings, engine: Engine, model: ModelRow, llm: LLMClient):
    """Run discovery for the hero model on a fixed date."""
    recorder = AuditRecorder(engine, model_id="M001", run_id="run_M001_001", stage="discover")
    return run_discovery(
        settings, model, llm, recorder, pipeline_status=PENDING, previous_record=None, today=date(2026, 11, 15)
    )


def test_static_signals_find_sas_procedures_and_model_statements(hero_estate: Settings, hero_model: ModelRow) -> None:
    """Regular expressions find the SAS procedure and the model statement without any LLM."""
    signals = static_signals(hero_estate, source_paths(hero_model.registration, "code"))
    assert signals["detected_languages"] == ["SAS"]
    assert "logistic" in signals["procedures"]
    assert signals["model_statements"] == ["default_flag = woe_pay0 woe_util"]


def test_discovery_builds_a_verified_inventory_record(hero_estate: Settings, engine: Engine, hero_model) -> None:
    """Fields come from the agent, facts from the register, the tier from the policy, evidence checked by code."""
    provider = ScriptedProvider({"discovery agent": json.dumps(DISCOVERY_REPLY)})
    outcome = discover(hero_estate, engine, hero_model, scripted_llm(hero_estate, provider))
    record = outcome.record
    assert record.model_name == "Credit Card PD Scorecard"
    assert record.model_owner == "Head of Cards Credit Risk"
    assert (record.tiering.tier, record.tiering.materiality_score, record.tiering.complexity_score) == ("Tier 1", 3, 1)
    assert record.next_validation_due == "2024-02-14"
    assert record.doc_status == "OUTDATED"
    statuses = {name: item.status for name, item in record.field_evidence.items()}
    assert statuses["algorithm"] == "VERIFIED"
    assert record.field_evidence["target_variable"].start_line == 3
    assert statuses["model_type"] == "UNVERIFIED"
    assert statuses["model_name"] == "UNVERIFIED"
    assert "Who approved the decision cutoff?" in record.open_questions
    assert (
        outcome.summary == "Inventory record created. Tier 1. 6 of 8 field evidence quotes verified. 1 open questions."
    )


def test_prompt_holds_numbered_code_and_never_the_answer_keys(
    hero_estate: Settings, engine: Engine, hero_model
) -> None:
    """The agent sees numbered lines of the model files and nothing from _answer_keys."""
    provider = ScriptedProvider({"discovery agent": json.dumps(DISCOVERY_REPLY)})
    discover(hero_estate, engine, hero_model, scripted_llm(hero_estate, provider))
    [(system, user)] = provider.prompts
    assert "L0002: proc logistic data=work.dev_woe descending;" in user
    assert "Never state owners, dates, exposure amounts" in system
    assert "secret" not in user
    assert "_answer_keys" not in user


def test_every_step_is_audited(hero_estate: Settings, engine: Engine, hero_model) -> None:
    """The LLM call and each deterministic check write an audit event for the discover stage."""
    provider = ScriptedProvider({"discovery agent": json.dumps(DISCOVERY_REPLY)})
    recorder = AuditRecorder(engine, model_id="M001", run_id="run_M001_001", stage="discover")
    llm = scripted_llm(
        hero_estate, provider, on_call=lambda response: recorder.llm_call("discovery_agent", response.trace())
    )
    discover(hero_estate, engine, hero_model, llm)
    with Session(engine) as session:
        actions = [(event.action, event.actor) for event in list_events(session)]
    assert actions == [
        ("tool_call", "static_signals"),
        ("llm_call", "discovery_agent"),
        ("tool_call", "evidence_verifier"),
        ("tool_call", "tiering_policy"),
    ]


def test_unknown_model_type_becomes_other(hero_estate: Settings, engine: Engine, hero_model) -> None:
    """A model type outside the contract list is stored as other."""
    reply = DISCOVERY_REPLY | {"model_type": "behavioural"}
    outcome = discover(
        hero_estate, engine, hero_model, scripted_llm(hero_estate, ScriptedProvider({"discovery": json.dumps(reply)}))
    )
    assert outcome.record.model_type == "other"


def test_replay_without_a_recording_fails_clearly(hero_estate: Settings, engine: Engine, hero_model) -> None:
    """In replay mode with an empty cache, discovery stops with a message about recording."""
    replay_client = LLMClient(hero_estate)
    with pytest.raises(LLMReplayMissError, match="LLM_MODE=live"):
        discover(hero_estate, engine, hero_model, replay_client)
