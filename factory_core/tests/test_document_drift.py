"""Document drift: differences between the old document and the code, both sides checked by code."""

import json

from sqlalchemy import Engine
from sqlmodel import Session

from app.agents.document_drift import find_drift
from app.audit_trail import AuditRecorder
from app.config import Settings
from app.database import ModelRow
from app.estate_scanner import register_estate
from app.stage_result_schemas import Claim, DocumentSection, Evidence
from tests.conftest import HERO_FOLDER, ScriptedProvider, scripted_llm

OLD_DOCUMENT = f"{HERO_FOLDER}/docs/model_document_2021.md"
SCORE_CODE = f"{HERO_FOLDER}/code/03_score.sas"
CUTOFF_EVIDENCE = {
    "file": SCORE_CODE,
    "start_line": 4,
    "end_line": 4,
    "quote": "if score < 540 then decision = 'DECLINE';",
}
SECTIONS = [
    DocumentSection(
        id="model_specification",
        title="Model specification",
        markdown="Scores below 540 are declined. [C001]",
        claims=[
            Claim(
                id="C001",
                text="Scores below 540 are declined.",
                status="VERIFIED",
                evidence=[Evidence(**CUTOFF_EVIDENCE)],
            ),
            Claim(id="C002", text="SME input needed: who set the cutoff?", status="SME_INPUT_NEEDED", evidence=[]),
        ],
    )
]
DRIFT_REPLY = {
    "differences": [
        {
            "topic": "Decision cutoff",
            "severity": "HIGH",
            "legacy_doc_says": "Applications scoring below 520 are declined.",
            "code_says": "The cutoff in the scoring code is 540.",
            "legacy_evidence": {
                "file": OLD_DOCUMENT,
                "start_line": 7,
                "end_line": 7,
                "quote": "scoring below 520 are declined",
            },
            "code_evidence": CUTOFF_EVIDENCE,
        },
        {
            "topic": "Variables",
            "severity": "MEDIUM",
            "legacy_doc_says": "The model uses twelve variables.",
            "code_says": "The model uses two WoE variables.",
            "legacy_evidence": {"file": OLD_DOCUMENT, "start_line": 3, "end_line": 3, "quote": "uses twelve variables"},
            "code_evidence": CUTOFF_EVIDENCE,
        },
        {
            "topic": "Purpose",
            "severity": "LOW",
            "legacy_doc_says": "Default next month.",
            "code_says": "Default next month.",
            "legacy_evidence": {"file": OLD_DOCUMENT, "start_line": 4, "end_line": 4, "quote": "defaults next month"},
            "code_evidence": {"file": OLD_DOCUMENT, "start_line": 4, "end_line": 4, "quote": "defaults next month"},
        },
    ]
}


def hero_model(settings: Settings, session: Session) -> ModelRow:
    """Register the test estate and return M001."""
    register_estate(session, settings)
    return session.get(ModelRow, "M001")


def test_both_sides_must_verify(hero_estate: Settings, engine: Engine, session: Session) -> None:
    """The seeded cutoff difference is VERIFIED; an invented quote or a document cited as code is not."""
    provider = ScriptedProvider({"old model document": json.dumps(DRIFT_REPLY)})
    recorder = AuditRecorder(engine, model_id="M001", run_id="run_M001_001", stage="document")
    items = find_drift(
        hero_estate, hero_model(hero_estate, session), SECTIONS, scripted_llm(hero_estate, provider), recorder
    )
    assert [(item.id, item.topic, item.status) for item in items] == [
        ("D001", "Decision cutoff", "VERIFIED"),
        ("D002", "Variables", "UNVERIFIED"),
        ("D003", "Purpose", "UNVERIFIED"),
    ]
    assert items[0].legacy_evidence.start_line == 7
    assert items[2].code_evidence is None


def test_prompt_holds_the_old_document_and_only_verified_claims(
    hero_estate: Settings, engine: Engine, session: Session
) -> None:
    """The agent sees the numbered old document and the verified claims with their evidence."""
    provider = ScriptedProvider({"old model document": json.dumps({"differences": []})})
    recorder = AuditRecorder(engine)
    items = find_drift(
        hero_estate, hero_model(hero_estate, session), SECTIONS, scripted_llm(hero_estate, provider), recorder
    )
    [(_, user)] = provider.prompts
    assert items == []
    assert "L0007: Applications scoring below 520 are declined." in user
    assert "Scores below 540 are declined." in user
    assert "who set the cutoff" not in user


def test_model_without_an_old_document_has_no_drift(hero_estate: Settings, engine: Engine, session: Session) -> None:
    """With no document there is nothing to compare, and no LLM call is made."""
    model = hero_model(hero_estate, session)
    model.registration = {
        **model.registration,
        "source_files": [f for f in model.registration["source_files"] if f["kind"] == "code"],
    }
    provider = ScriptedProvider({})
    assert find_drift(hero_estate, model, SECTIONS, scripted_llm(hero_estate, provider), AuditRecorder(engine)) == []
    assert provider.prompts == []
