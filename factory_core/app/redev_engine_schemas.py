"""Contract shapes exchanged with redev_engine, section 9.1 of docs/PROJECT_CONTEXT.md."""

from __future__ import annotations

from typing import Any

from app.schemas import ContractModel, ParityLevelStatus, RedevelopStatus, ServiceModel


class RedevelopRequest(ContractModel):
    """Body of POST /redevelop."""

    run_id: str
    model_id: str
    estate_path: str
    max_heal_iterations: int = 3
    use_pitfall_library: bool = True


class RedevelopIteration(ServiceModel):
    """One translate, test and parity attempt of the self healing loop."""

    iteration: int
    unit_tests_passed: int
    unit_tests_failed: int
    parity_passed: bool
    max_abs_diff_pd: float | None = None
    diagnosis: str | None = None
    fix_applied: str | None = None


class GeneratedFile(ServiceModel):
    """A file written by the rebuild."""

    path: str
    kind: str


class LineMapping(ServiceModel):
    """Legacy lines and the Python lines that implement them."""

    legacy_file: str
    legacy_start: int
    legacy_end: int
    python_file: str
    python_start: int
    python_end: int
    note: str | None = None


class UnitTestCounts(ServiceModel):
    """Unit test totals for the rebuilt model."""

    total: int
    passed: int
    failed: int


class ParityLevel(ServiceModel):
    """One of the four parity levels."""

    level: str
    status: ParityLevelStatus
    max_abs_diff: float | None = None
    mismatched_records: int | None = None
    match_rate: float | None = None
    psi: float | None = None
    detail: str | None = None


class ParityHashes(ServiceModel):
    """Hashes that make the parity check repeatable."""

    legacy_code_sha256: str | None = None
    python_code_sha256: str | None = None
    input_data_sha256: str | None = None
    golden_output_sha256: str | None = None


class Parity(ServiceModel):
    """The parity certificate summary."""

    passed: bool
    records_compared: int
    tolerance_pd: float
    tolerance_coef: float
    levels: list[ParityLevel]
    hashes: ParityHashes
    certificate_md_path: str | None = None
    certificate_json_path: str | None = None
    mismatch_sample_path: str | None = None


class LlmTraceEntry(ServiceModel):
    """Trace fields of one LLM call, written to the audit trail."""

    step: str
    model: str
    prompt_sha256: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    cached: bool


class RedevelopResult(ServiceModel):
    """Response of POST /redevelop, also served by GET /api/models/{model_id}/redevelopment."""

    model_id: str
    run_id: str
    status: RedevelopStatus
    source_language: str  # A language, or "unknown" when the rebuild failed before the manifest was read.
    target_language: str
    iterations: list[RedevelopIteration] = []
    generated_files: list[GeneratedFile] = []
    line_mapping: list[LineMapping] = []
    unit_tests: UnitTestCounts | None = None
    parity: Parity | None = None
    pitfalls_checked: list[str] = []
    mlflow: dict[str, Any] | None = None
    llm_trace: list[LlmTraceEntry] = []
    duration_seconds: float | None = None
    error: str | dict[str, Any] | None = None
