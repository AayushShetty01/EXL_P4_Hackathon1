"""Request and response models of redev_engine. They match section 9.1 of the project context exactly."""

from typing import Literal

from pydantic import BaseModel, Field

RedevelopStatus = Literal["PARITY_PASSED", "PARITY_FAILED", "TRANSLATED_NO_GOLDEN", "ERROR"]
LevelStatus = Literal["PASSED", "FAILED", "NOT_APPLICABLE"]


class RedevelopRequest(BaseModel):
    """Body of POST /redevelop."""

    run_id: str
    model_id: str
    estate_path: str
    max_heal_iterations: int = Field(3, ge=0, le=10)
    use_pitfall_library: bool = True


class ParityRequest(BaseModel):
    """Body of POST /parity."""

    model_id: str
    estate_path: str


class Iteration(BaseModel):
    """One translate or heal round with its test and parity outcome."""

    iteration: int
    unit_tests_passed: int
    unit_tests_failed: int
    parity_passed: bool
    max_abs_diff_pd: float | None
    diagnosis: str | None
    fix_applied: str | None


class GeneratedFile(BaseModel):
    """An output file of the rebuild."""

    path: str
    kind: str


class LineMapping(BaseModel):
    """Link between a legacy line range and the Python lines that implement it."""

    legacy_file: str
    legacy_start: int
    legacy_end: int
    python_file: str
    python_start: int
    python_end: int
    note: str


class UnitTestSummary(BaseModel):
    """Counts of the unit tests of the rebuilt model."""

    total: int
    passed: int
    failed: int


class ParityLevel(BaseModel):
    """Result of one of the four parity levels."""

    level: Literal["L1_coefficients", "L2_record_scores", "L3_decisions", "L4_distribution"]
    status: LevelStatus
    max_abs_diff: float | None
    mismatched_records: int | None
    match_rate: float | None
    psi: float | None
    detail: str


class ParityHashes(BaseModel):
    """SHA 256 hashes that make the parity check reproducible."""

    legacy_code_sha256: str | None
    python_code_sha256: str | None
    input_data_sha256: str | None
    golden_output_sha256: str | None


class Parity(BaseModel):
    """The four level parity outcome."""

    passed: bool
    records_compared: int
    tolerance_pd: float
    tolerance_coef: float
    levels: list[ParityLevel]
    hashes: ParityHashes
    certificate_md_path: str | None
    certificate_json_path: str | None
    mismatch_sample_path: str | None


class LLMTraceEntry(BaseModel):
    """Trace of one LLM call, used by factory_core for the audit trail."""

    step: str
    model: str
    prompt_sha256: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    cached: bool


class ErrorBody(BaseModel):
    """Error code and human readable message."""

    code: str
    message: str


class RedevelopResult(BaseModel):
    """Response of POST /redevelop."""

    model_id: str
    run_id: str
    status: RedevelopStatus
    source_language: str
    target_language: str = "Python"
    iterations: list[Iteration] = []
    generated_files: list[GeneratedFile] = []
    line_mapping: list[LineMapping] = []
    unit_tests: UnitTestSummary = UnitTestSummary(total=0, passed=0, failed=0)
    parity: Parity | None = None
    pitfalls_checked: list[str] = []
    mlflow: dict | None = None
    llm_trace: list[LLMTraceEntry] = []
    duration_seconds: float = 0.0
    error: ErrorBody | None = None


class Pitfall(BaseModel):
    """A known trap when translating SAS or R to Python."""

    id: str
    language: Literal["SAS", "R"]
    title: str
    description: str
    python_fix: str
