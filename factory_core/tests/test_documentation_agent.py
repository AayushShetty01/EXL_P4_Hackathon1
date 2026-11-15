"""The documentation agent: ten sections, claims checked by code, markers and groundedness."""

import json
import re

import pytest
from sqlalchemy import Engine
from sqlmodel import Session

from app.agents.documentation_agent import SECTIONS, SectionReply, check_claims, render_markdown, write_documentation
from app.api_schemas import InventoryRecord
from app.audit_trail import AuditRecorder
from app.config import Settings
from app.database import ModelRow
from app.estate_scanner import register_estate
from app.stage_result_schemas import Documentation
from tests.conftest import HERO_FOLDER, ScriptedProvider, load_example, scripted_llm

LOGISTIC = {
    "file": f"{HERO_FOLDER}/code/02_train.sas",
    "start_line": 2,
    "end_line": 2,
    "quote": "proc logistic data=work.dev_woe descending;",
}
CUTOFF = {
    "file": f"{HERO_FOLDER}/code/03_score.sas",
    "start_line": 4,
    "end_line": 4,
    "quote": "if score < 540 then decision = 'DECLINE';",
}


def section_reply(system: str, user: str) -> str:
    """A scripted reply per section: overview has two claims, limitations asks an SME, assumptions is wrong."""
    section_id = re.search(r"Section to write: .+ \((\w+)\)", user).group(1)
    if section_id == "overview":
        return json.dumps(
            {
                "markdown": "The model is a logistic regression.{{claim:1}} Scores below 540 are declined.{{claim:2}}",
                "claims": [
                    {"text": "The model is a logistic regression.", "evidence": [LOGISTIC]},
                    {"text": "Scores below 540 are declined.", "evidence": [CUTOFF]},
                ],
            }
        )
    if section_id == "limitations":
        text = "SME input needed: was the holdout drawn at random?"
        return json.dumps({"markdown": text + "{{claim:1}}", "claims": [{"text": text, "evidence": []}]})
    if section_id == "assumptions":
        wrong = LOGISTIC | {"quote": "proc hpsplit data=work.dev_woe;"}
        return json.dumps(
            {"markdown": "A tree model is used.", "claims": [{"text": "A tree model is used.", "evidence": [wrong]}]}
        )
    return json.dumps(
        {
            "markdown": "Fitted with PROC LOGISTIC.{{claim:1}}",
            "claims": [{"text": "Fitted with PROC LOGISTIC.", "evidence": [LOGISTIC]}],
        }
    )


@pytest.fixture
def hero_model(hero_estate: Settings, session: Session) -> ModelRow:
    """The registered M001 model of the test estate."""
    register_estate(session, hero_estate)
    return session.get(ModelRow, "M001")


@pytest.fixture
def approved_record() -> InventoryRecord:
    """An approved inventory record for M001."""
    return InventoryRecord.model_validate(load_example("inventory_record.M001.json"))


def write(settings: Settings, engine: Engine, model: ModelRow, record: InventoryRecord, provider: ScriptedProvider):
    """Run the documentation agent with a scripted LLM."""
    recorder = AuditRecorder(engine, model_id="M001", run_id="run_M001_001", stage="document")
    return write_documentation(settings, model, record, scripted_llm(settings, provider), recorder)


def test_ten_sections_in_contract_order(hero_estate, engine, hero_model, approved_record) -> None:
    """One LLM call per section, in the order of the contract."""
    provider = ScriptedProvider({"Section to write": section_reply})
    draft = write(hero_estate, engine, hero_model, approved_record, provider)
    assert [section.id for section in draft.sections] == [section_id for section_id, _, _ in SECTIONS]
    assert len(provider.prompts) == 10
    assert draft.generated_by_model == "test-model"


def test_claims_are_numbered_marked_and_checked(hero_estate, engine, hero_model, approved_record) -> None:
    """Claim ids run across sections, markers replace placeholders, and each status comes from the verifier."""
    draft = write(
        hero_estate, engine, hero_model, approved_record, ScriptedProvider({"Section to write": section_reply})
    )
    overview, intended_use = draft.sections[0], draft.sections[1]
    assert overview.markdown == "The model is a logistic regression. [C001] Scores below 540 are declined. [C002]"
    assert [claim.id for claim in intended_use.claims] == ["C003"]
    statuses = {claim.text: claim.status for section in draft.sections for claim in section.claims}
    assert statuses["Scores below 540 are declined."] == "VERIFIED"
    assert statuses["A tree model is used."] == "UNVERIFIED"
    assert statuses["SME input needed: was the holdout drawn at random?"] == "SME_INPUT_NEEDED"
    assert draft.sections[5].markdown == "A tree model is used. [C007]"


def test_groundedness_is_computed_by_code(hero_estate, engine, hero_model, approved_record) -> None:
    """Eleven claims: nine verified, one unverified, one waiting for an SME."""
    draft = write(
        hero_estate, engine, hero_model, approved_record, ScriptedProvider({"Section to write": section_reply})
    )
    assert draft.groundedness.model_dump() == {
        "claims_total": 11,
        "claims_verified": 9,
        "claims_unverified": 1,
        "claims_sme_input_needed": 1,
        "score": 0.818,
    }


def test_prompt_holds_code_dictionary_and_record_but_not_the_old_document(
    hero_estate, engine, hero_model, approved_record
) -> None:
    """The agent works from the code, the data dictionary and the approved record."""
    provider = ScriptedProvider({"Section to write": section_reply})
    write(hero_estate, engine, hero_model, approved_record, provider)
    system, user = provider.prompts[6]
    assert "Section to write: Limitations (limitations)" in user
    assert "random holdout, not a true out of time sample" in user
    assert "data_dictionary.csv" in user
    assert "L0002: PAY_0,Repayment status" in user
    assert "model_document_2021.md" not in user
    assert "Never compute" in system


def test_claim_without_a_placeholder_still_gets_a_marker(hero_estate: Settings) -> None:
    """A claim the agent forgot to mark is marked after its sentence, or appended."""
    reply = SectionReply.model_validate(
        {
            "markdown": "The model is a logistic regression. More text.",
            "claims": [
                {"text": "The model is a logistic regression.", "evidence": [LOGISTIC]},
                {"text": "Another claim.", "evidence": []},
            ],
        }
    )
    markdown, claims = check_claims(hero_estate, HERO_FOLDER, reply, first_number=5)
    assert markdown == "The model is a logistic regression. [C005] More text.\n\nAnother claim. [C006]"
    assert [claim.status for claim in claims] == ["VERIFIED", "SME_INPUT_NEEDED"]


def test_render_markdown_lists_sections_claims_and_drift() -> None:
    """The Markdown document carries every section, a claim table and the drift table."""
    documentation = Documentation.model_validate(load_example("documentation.M001.json"))
    text = render_markdown(documentation, "Credit Card PD Scorecard", "2026-11-15")
    assert text.startswith("# Credit Card PD Scorecard (M001): model document")
    assert "## Methodology" in text
    assert "| C014 | VERIFIED |" in text
    assert "| D001 | HIGH | Decision cutoff |" in text
