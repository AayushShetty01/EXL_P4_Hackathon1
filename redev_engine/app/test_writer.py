"""Writes test_model.py, pytest tests for the rebuilt model that state the expected legacy behaviour."""

import json

from pydantic import BaseModel

from app import llm_client
from app.code_analyzer import numbered_source

SYSTEM_PROMPT = """You are a model validator who writes unit tests for a Python rebuild of a legacy credit model.
The expected value in every test follows the semantics of the legacy language, not of Python. Reply with JSON only."""

RULES = """Write test_model.py for pytest. Rules:
- Import the model with "import model" and build small DataFrames by hand. Never read files.
- Cover every derived variable and every bin: normal values, bin boundaries, zero denominators and missing values.
- Cover score scaling, rounding at exact halves and the decision cutoff boundary.
- When calling model.score, pass an explicit coefficients dict with the same names that fit() returns.
- Imports allowed: pytest, model, pandas, numpy, math. No file access, no names starting with two underscores.
- Every test has a one line docstring that states the legacy behaviour it checks.
- The file starts with the docstring '\"\"\"Unit tests for the Python rebuild of model {model_id}.\"\"\"'.
Reply with JSON: {{"test_code": "full content of test_model.py"}}"""


class UnitTestReply(BaseModel):
    """JSON reply of the test writer."""

    test_code: str


def write_tests(manifest: dict, model_dir, spec: dict, model_code: str) -> tuple[str, llm_client.LLMResponse]:
    """One LLM call that returns the content of test_model.py."""
    user = (
        f"{RULES.format(model_id=manifest['model_id'])}\n\n"
        f"Legacy source:\n{numbered_source(model_dir, manifest['code_files'])}\n\n"
        f"Logic specification:\n{json.dumps({k: v for k, v in spec.items() if k != 'static_facts'}, indent=1)}\n\n"
        f"model.py:\n{model_code}"
    )
    response = llm_client.complete(SYSTEM_PROMPT, user, json_mode=True, step="write_tests", response_model=UnitTestReply)
    return response.parsed.test_code, response
