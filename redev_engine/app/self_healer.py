"""Diagnose and repair step: one LLM call that explains a parity or test failure and returns a corrected model.py."""

import json

import pandas as pd
from pydantic import BaseModel

from app import llm_client
from app.pitfall_library import pitfalls_as_text

SYSTEM_PROMPT = """You are a senior quantitative developer fixing a Python rebuild of a legacy credit model.
The legacy outputs are the ground truth. Use the evidence (failing tests, largest mismatches, mismatch profile)
to find the root cause, then return the full corrected model.py. Keep the interface, the '# source:' comments
and DEPLOYED_COEFFICIENTS exactly as they are. If a unit test contradicts the legacy outputs, say so in the
diagnosis and keep the model faithful to the legacy outputs. Reply with JSON only."""

REPLY_SHAPE = ('{"diagnosis": "what is wrong and why, citing the evidence", '
               '"fix_applied": "the fix in one sentence", "model_code": "full corrected model.py"}')
MAX_TEST_OUTPUT_CHARS = 6000
MISMATCH_ROWS = 20


class HealReply(BaseModel):
    """JSON reply of the healer."""

    diagnosis: str
    fix_applied: str
    model_code: str


def heal(manifest: dict, model_code: str, test_output: str, mismatch_csv: str, profile: dict,
         levels: list[dict], use_pitfalls: bool, iteration: int) -> tuple[HealReply, llm_client.LLMResponse]:
    """One LLM call with the failure evidence; returns the diagnosis, the fix and the corrected file."""
    pitfalls = pitfalls_as_text(manifest["language"]) if use_pitfalls else "Not provided."
    user = (
        f"Model {manifest['model_id']}, legacy language {manifest['language']}.\n\n"
        f"Parity levels:\n{json.dumps(levels, indent=1)}\n\n"
        f"Mismatch profile:\n{json.dumps(profile, indent=1)}\n\n"
        f"Largest mismatches (legacy against Python, with inputs):\n{mismatch_csv or 'None'}\n\n"
        f"Unit test output:\n{test_output[-MAX_TEST_OUTPUT_CHARS:] or 'None'}\n\n"
        f"Current model.py:\n{model_code}\n\n"
        f"Known translation pitfalls:\n{pitfalls}\n\nReply with JSON of this shape:\n{REPLY_SHAPE}"
    )
    response = llm_client.complete(SYSTEM_PROMPT, user, json_mode=True, step=f"heal_{iteration}", response_model=HealReply)
    return response.parsed, response


def top_mismatches_csv(mismatch_path) -> str:
    """The 20 largest mismatches as CSV text, read from mismatches.csv."""
    if not mismatch_path:
        return ""
    return pd.read_csv(mismatch_path).head(MISMATCH_ROWS).to_csv(index=False)
