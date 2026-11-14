"""The validator agent: independent instructions, grounded numbers, one rewrite, visible failures."""

import json

from sqlalchemy import Engine

from app.agents.validator_agent import write_narrative
from app.api_schemas import InventoryRecord
from app.audit_trail import AuditRecorder
from app.config import Settings
from app.llm_client import LLMClient
from app.validation_lab_schemas import ValidationResult
from tests.conftest import GROUNDED_NARRATIVE, ScriptedProvider, live_settings, load_example, scripted_llm

INVENTED = GROUNDED_NARRATIVE | {"executive_summary": "The AUC is 0.91, which is excellent."}


def run(settings: Settings, engine: Engine, provider: ScriptedProvider, validator_model: str = ""):
    """Write the narrative for the example validation result."""
    return write_narrative(
        scripted_llm(settings, provider),
        AuditRecorder(engine, model_id="M001", run_id="run_M001_001", stage="validate"),
        result=ValidationResult.model_validate(load_example("validation_result.M001.json")),
        record=InventoryRecord.model_validate(load_example("inventory_record.M001.json")),
        limitations="The holdout is a random holdout, not a true out of time sample.",
        parity=None,
        validator_model=validator_model,
    )


def test_grounded_narrative_is_accepted_in_one_call(settings: Settings, engine: Engine) -> None:
    """When every number is in the results, there is no rewrite and nothing is unverified."""
    provider = ScriptedProvider({"independent model validator": json.dumps(GROUNDED_NARRATIVE)})
    outcome = run(settings, engine, provider)
    assert len(provider.prompts) == 1
    assert outcome.narrative.unverified_numbers == []
    assert outcome.number_grounding.score == 1.0


def test_invented_number_triggers_one_rewrite(settings: Settings, engine: Engine) -> None:
    """A number that is not in the results is named in a rewrite request; the corrected text is used."""
    replies = iter([json.dumps(INVENTED), json.dumps(GROUNDED_NARRATIVE)])
    provider = ScriptedProvider({"independent model validator": lambda system, user: next(replies)})
    outcome = run(settings, engine, provider)
    assert len(provider.prompts) == 2
    assert "not in the results: 0.91" in provider.prompts[1][1]
    assert outcome.narrative.executive_summary == GROUNDED_NARRATIVE["executive_summary"]


def test_numbers_that_stay_wrong_remain_visible(settings: Settings, engine: Engine) -> None:
    """After the one rewrite, numbers that still fail are listed as unverified, never hidden."""
    provider = ScriptedProvider({"independent model validator": json.dumps(INVENTED)})
    outcome = run(settings, engine, provider)
    assert outcome.narrative.unverified_numbers == ["0.91"]
    assert outcome.number_grounding.numbers_verified < outcome.number_grounding.numbers_in_narrative


def test_validator_sees_results_but_not_chart_data_or_other_agents(settings: Settings, engine: Engine) -> None:
    """The prompt carries the results, record, limitations and parity, but no series or traces."""
    provider = ScriptedProvider({"independent model validator": json.dumps(GROUNDED_NARRATIVE)})
    run(settings, engine, provider)
    system, user = provider.prompts[0]
    assert "you did not build this model" in system.lower()
    assert '"hosmer_lemeshow_p": 0.0055' in user
    assert "random holdout" in user
    assert '"roc_oot"' not in user and "llm_trace" not in user


def test_separate_validator_model_is_used_when_set(settings: Settings, engine: Engine) -> None:
    """LLM_MODEL_VALIDATOR gives the validator a different model from the developer agents."""
    seen: list[str] = []
    provider = ScriptedProvider({"independent model validator": json.dumps(GROUNDED_NARRATIVE)})

    def recording_provider(model: str, system: str, user: str, temperature: float):
        """Record the model id, then answer from the script."""
        seen.append(model)
        return provider(model, system, user, temperature)

    outcome = write_narrative(
        LLMClient(live_settings(settings), provider=recording_provider),
        AuditRecorder(engine),
        result=ValidationResult.model_validate(load_example("validation_result.M001.json")),
        record=InventoryRecord.model_validate(load_example("inventory_record.M001.json")),
        limitations=None,
        parity=None,
        validator_model="independent-model",
    )
    assert seen == ["independent-model"]
    assert outcome.validator_model == "independent-model"
