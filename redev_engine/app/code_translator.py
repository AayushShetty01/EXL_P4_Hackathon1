"""Translates legacy code plus its logic spec into model.py, injects the legacy coefficients and maps source lines."""

import ast
import json
import re
from pathlib import Path

import pandas as pd
from pydantic import BaseModel

from app import llm_client
from app.code_analyzer import numbered_source
from app.config import to_repo_path
from app.pitfall_library import pitfalls_as_text
from app.schemas import LineMapping

SOURCE_COMMENT = re.compile(r"#\s*source:\s*(\S+)\s+L(\d+)(?:\s*(?:to|-)\s*L?(\d+))?\s*(?:[-:|]\s*(.*))?$")

SYSTEM_PROMPT = """You are a senior quantitative developer who rebuilds legacy SAS and R credit models in Python.
The Python model must reproduce the legacy outputs exactly, record by record, including every quirk of the
legacy language (missing values, division, rounding, branch order, factor coding). Reply with JSON only."""

INTERFACE = '''Write one Python file model.py with exactly this interface:

"""Python rebuild of model {model_id}. Legacy sources: {sources}."""
MODEL_ID = "{model_id}"
INPUT_COLUMNS = [...]            # raw columns the model reads
DEPLOYED_COEFFICIENTS = {{}}     # leave exactly this empty dict: the legacy values are inserted later
def prepare(df): ...             # raw DataFrame in, DataFrame of model variables out (keep ID)
def fit(dev_df): ...             # re-estimates the model, returns {{"coefficients": {{name: value}}}}
def score(df, coefficients=None): ...  # DataFrame with columns ID, pd, score, decision

Rules:
- score() uses DEPLOYED_COEFFICIENTS when coefficients is None.
- Coefficient names must be exactly: {coefficient_names}
- pd is the probability of the bad event. score is an integer (0 if the legacy model has no score).
  decision is the string APPROVE or DECLINE.
- fit() must estimate without regularisation (use statsmodels) and model the same event as the legacy code.
- Imports allowed: pandas, numpy, math, statsmodels, scipy, sklearn, typing, dataclasses. Nothing else.
  No file access, no eval or exec, no names or attributes that start with two underscores,
  no main block.
- Above every block put a comment of the form "# source: <legacy file> L<start> to L<end> - <what it does>"
  with the legacy file path exactly as listed and the legacy line numbers it implements.
- Every function has a one line docstring. Never use the protected columns {protected} as inputs.
- The file header and comments describe the model only, nothing about how the file was produced.'''

REPLY_SHAPE = '{"model_code": "full content of model.py", "pitfalls_applied": ["PITFALL_ID"], "notes": "short notes"}'


class TranslationReply(BaseModel):
    """JSON reply of the translator."""

    model_code: str
    pitfalls_applied: list[str] = []
    notes: str = ""


def legacy_coefficients(manifest: dict, model_dir: Path) -> dict[str, float]:
    """Legacy coefficient estimates read from coefficients_legacy.csv (empty when there are none)."""
    golden = manifest.get("golden") or {}
    if not golden.get("coefficients_path"):
        return {}
    table = pd.read_csv(model_dir / golden["coefficients_path"])
    return {str(name): float(value) for name, value in zip(table["variable"], table["estimate"])}


def inject_coefficients(code: str, coefficients: dict[str, float]) -> str:
    """Replace the DEPLOYED_COEFFICIENTS assignment with the legacy values, inserted by code (never taken from the LLM)."""
    tree = ast.parse(code)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]  # 'DEPLOYED_COEFFICIENTS: Dict[str, float] = {}'; the annotation is dropped
        else:
            continue
        if any(getattr(t, "id", None) == "DEPLOYED_COEFFICIENTS" for t in targets):
            lines = code.splitlines()
            body = "".join(f"\n    {name!r}: {value!r}," for name, value in coefficients.items())
            replacement = "DEPLOYED_COEFFICIENTS = {" + body + ("\n}" if coefficients else "}")
            return "\n".join(lines[: node.lineno - 1] + replacement.splitlines() + lines[node.end_lineno:]) + "\n"
    raise ValueError("model.py has no top level DEPLOYED_COEFFICIENTS assignment")


def build_line_mapping(code: str, python_file: Path, manifest: dict, model_dir: Path) -> tuple[list[LineMapping], list[str]]:
    """Parse the '# source:' comments, verify the cited legacy lines exist and return the mapping plus problems."""
    lengths = {name: len((model_dir / name).read_text(encoding="utf-8").splitlines()) for name in manifest["code_files"]}
    lines = code.splitlines()
    marks = [(i + 1, SOURCE_COMMENT.search(line.strip())) for i, line in enumerate(lines)]
    marks = [(n, m) for n, m in marks if m]
    mapping, problems = [], []
    for index, (line_number, match) in enumerate(marks):
        legacy_name, start = match.group(1), int(match.group(2))
        end = int(match.group(3) or start)
        if legacy_name not in lengths or not 1 <= start <= end <= lengths[legacy_name]:
            problems.append(f"model.py line {line_number}: cited {legacy_name} L{start} to L{end} does not exist")
            continue
        block_end = marks[index + 1][0] - 1 if index + 1 < len(marks) else len(lines)
        while block_end > line_number and not lines[block_end - 1].strip():
            block_end -= 1
        mapping.append(LineMapping(
            legacy_file=f"{manifest['folder']}/{legacy_name}", legacy_start=start, legacy_end=end,
            python_file=to_repo_path(python_file), python_start=line_number, python_end=block_end,
            note=(match.group(4) or "").strip(),
        ))
    return mapping, problems


def data_columns(manifest: dict, model_dir: Path) -> str:
    """The data dictionary as text (column names and roles only, no data rows)."""
    data = manifest.get("data") or {}
    if not data.get("dictionary_path"):
        return "No data dictionary."
    return (model_dir / data["dictionary_path"]).read_text(encoding="utf-8")


def translate(manifest: dict, model_dir: Path, spec: dict, use_pitfalls: bool) -> tuple[TranslationReply, llm_client.LLMResponse]:
    """One LLM call that returns model.py (before coefficient injection)."""
    coefficients = legacy_coefficients(manifest, model_dir)
    names = list(coefficients) or "as named in the legacy estimation output (no legacy file available)"
    interface = INTERFACE.format(
        model_id=manifest["model_id"], sources=", ".join(manifest["code_files"]), coefficient_names=names,
        protected=(manifest.get("data") or {}).get("protected_cols", []),
    )
    pitfalls = pitfalls_as_text(manifest["language"]) if use_pitfalls else "Not provided."
    user = (
        f"{interface}\n\nLegacy source:\n{numbered_source(model_dir, manifest['code_files'])}\n\n"
        f"Logic specification:\n{json.dumps({k: v for k, v in spec.items() if k != 'static_facts'}, indent=1)}\n\n"
        f"Data dictionary:\n{data_columns(manifest, model_dir)}\n\n"
        f"Known translation pitfalls:\n{pitfalls}\n\nReply with JSON of this shape:\n{REPLY_SHAPE}"
    )
    response = llm_client.complete(SYSTEM_PROMPT, user, json_mode=True, step="translate", response_model=TranslationReply)
    return response.parsed, response


def write_notes(path: Path, manifest: dict, spec: dict, pitfalls_applied: list[str], notes: str, problems: list[str]) -> None:
    """Write translation_notes.md: what was translated, which pitfalls applied, open questions."""
    lines = [
        f"# Translation notes, model {manifest['model_id']}",
        "",
        f"Legacy {manifest['language']} sources: " + ", ".join(f"`{manifest['folder']}/{f}`" for f in manifest["code_files"]),
        "",
        "## What was translated",
        "",
        notes or "See model.py and logic_spec.json.",
        "",
        "## Pitfalls applied",
        "",
        *([f"* {p}" for p in pitfalls_applied] or ["* None reported"]),
        "",
        "## Open questions",
        "",
        *([f"* {q}" for q in spec.get("open_questions", [])] or ["* None"]),
    ]
    if problems:
        lines += ["", "## Source references that could not be verified", "", *[f"* {p}" for p in problems]]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
