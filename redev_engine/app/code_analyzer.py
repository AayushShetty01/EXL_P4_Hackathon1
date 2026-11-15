"""Turns legacy code into logic_spec.json: a simple static parse plus one LLM call, with every item tied to source lines."""

import json
import re
from pathlib import Path

from pydantic import BaseModel

from app import llm_client

STATIC_PATTERNS = {
    "SAS": {
        "estimation": r"\bproc\s+(logistic|reg|glm|genmod)\b",
        "event_option": r"\b(descending|event\s*=)",
        "rounding": r"\b(round|int|floor|ceil)\s*\(",
        "division": r"[\w)]\s*/\s*[\w(]",
        "missing_aware_function": r"\b(sum|mean|max|min)\s*\(",
        "missing_test": r"=\s*\.\s|missing\s*\(",
        "condition": r"^\s*(else\s+)?if\b",
        "decision": r"\bdecision\s*=",
    },
    "R": {
        "estimation": r"\b(glm|lm)\s*\(",
        "prediction": r"\bpredict\s*\(",
        "binning": r"\bcut\s*\(",
        "factor_levels": r"\bfactor\s*\(",
        "rounding": r"\b(round|floor|ceiling|trunc)\s*\(",
        "decision": r"\bifelse\s*\(",
    },
    "Python": {
        "estimation": r"\.fit\s*\(",
        "prediction": r"\.predict(_proba)?\s*\(",
        "threshold": r"\bTHRESHOLD\b|>\s*0\.\d+",
    },
}

SYSTEM_PROMPT = """You are a model risk analyst who reverse engineers legacy credit risk code.
Read the legacy source and describe its exact logic as JSON. Describe what the code does, not what a
document says. Every item must cite the file and the line range it comes from, using the line numbers shown.
Write expressions in the legacy language semantics and state the missing value behaviour of each derived
variable. Put anything you cannot determine from the code into open_questions. Reply with JSON only."""

SPEC_SHAPE = """{
  "inputs": ["raw column names read by the model"],
  "derived_variables": [{"name": "", "expression": "", "missing_rule": "", "source": {"file": "", "start_line": 0, "end_line": 0}}],
  "bins": [{"variable": "", "input": "", "rules": [{"condition": "", "value": ""}], "source": {"file": "", "start_line": 0, "end_line": 0}}],
  "estimation": {"method": "", "options": "", "target": "", "event_modelled": "", "predictors": [""], "source": {"file": "", "start_line": 0, "end_line": 0}},
  "scoring_formula": {"expression": "", "source": {"file": "", "start_line": 0, "end_line": 0}},
  "score_scaling": {"expression": "", "source": {"file": "", "start_line": 0, "end_line": 0}},
  "rounding_rule": {"expression": "", "source": {"file": "", "start_line": 0, "end_line": 0}},
  "cutoff": {"expression": "", "source": {"file": "", "start_line": 0, "end_line": 0}},
  "open_questions": [""]
}"""


class SourceRef(BaseModel):
    """File and line range in the legacy code."""

    file: str
    start_line: int
    end_line: int


class SpecItem(BaseModel):
    """A formula or rule with its source."""

    expression: str
    source: SourceRef | None = None


class DerivedVariable(BaseModel):
    """A variable computed from raw inputs."""

    name: str
    expression: str
    missing_rule: str | None = None
    source: SourceRef | None = None


class BinRuleItem(BaseModel):
    """One ordered condition of a binning rule."""

    condition: str
    value: str


class BinRule(BaseModel):
    """Ordered binning conditions for one model variable."""

    variable: str
    input: str | None = None
    rules: list[BinRuleItem]
    source: SourceRef | None = None


class Estimation(BaseModel):
    """How the model parameters are estimated."""

    method: str
    options: str | None = None
    target: str | None = None
    event_modelled: str | None = None
    predictors: list[str] = []
    source: SourceRef | None = None


class LogicSpec(BaseModel):
    """The logic of a legacy model as a structured specification."""

    inputs: list[str] = []
    derived_variables: list[DerivedVariable] = []
    bins: list[BinRule] = []
    estimation: Estimation | None = None
    scoring_formula: SpecItem | None = None
    score_scaling: SpecItem | None = None
    rounding_rule: SpecItem | None = None
    cutoff: SpecItem | None = None
    open_questions: list[str] = []


def numbered_source(model_dir: Path, code_files: list[str]) -> str:
    """All legacy code files with a header per file and numbered lines."""
    blocks = []
    for name in code_files:
        lines = (model_dir / name).read_text(encoding="utf-8").splitlines()
        blocks.append(f"=== {name} ===\n" + "\n".join(f"{i:4d}| {line}" for i, line in enumerate(lines, 1)))
    return "\n\n".join(blocks)


def static_facts(language: str, model_dir: Path, code_files: list[str]) -> list[dict]:
    """Lines that match simple patterns of interest (estimation, rounding, division, cutoffs)."""
    patterns = STATIC_PATTERNS.get(language, {})
    facts = []
    for name in code_files:
        for number, line in enumerate((model_dir / name).read_text(encoding="utf-8").splitlines(), 1):
            for kind, pattern in patterns.items():
                if re.search(pattern, line, flags=re.IGNORECASE):
                    facts.append({"file": name, "line": number, "kind": kind, "text": line.strip()})
    return facts


def verify_sources(spec: dict, model_dir: Path, code_files: list[str]) -> int:
    """Mark every cited source with source_verified (file listed and lines exist); return the number not verified."""
    lengths = {name: len((model_dir / name).read_text(encoding="utf-8").splitlines()) for name in code_files}
    unverified = 0

    def visit(node: object) -> None:
        """Walk the spec and check each 'source' object."""
        nonlocal unverified
        if isinstance(node, dict):
            source = node.get("source")
            if isinstance(source, dict):
                length = lengths.get(source.get("file", ""))
                ok = bool(length) and 1 <= source.get("start_line", 0) <= source.get("end_line", 0) <= length
                source["source_verified"] = ok
                unverified += not ok
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(spec)
    return unverified


def analyze(manifest: dict, model_dir: Path, out_dir: Path) -> tuple[dict, llm_client.LLMResponse]:
    """Build logic_spec.json for one model and save it in out_dir."""
    language, code_files = manifest["language"], manifest["code_files"]
    facts = static_facts(language, model_dir, code_files)
    user = (
        f"Model {manifest['model_id']}, language {language}.\n\n"
        f"Legacy source:\n{numbered_source(model_dir, code_files)}\n\n"
        f"Lines found by a static scan (hints, may be incomplete):\n{json.dumps(facts, indent=1)}\n\n"
        f"Reply with JSON of this shape:\n{SPEC_SHAPE}"
    )
    response = llm_client.complete(SYSTEM_PROMPT, user, json_mode=True, step="analyze", response_model=LogicSpec)
    spec = {"model_id": manifest["model_id"], "language": language, **response.parsed.model_dump(), "static_facts": facts}
    spec["unverified_sources"] = verify_sources(spec, model_dir, code_files)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "logic_spec.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
    return spec, response
