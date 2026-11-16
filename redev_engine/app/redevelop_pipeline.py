"""Runs the whole rebuild for POST /redevelop: analyse, translate, write tests, run, check parity, heal, certify."""

import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from app import code_analyzer, code_sandbox, code_translator, mismatch_profiler, mlflow_logger, parity_certificate, self_healer, test_writer
from app.config import REPO_ROOT, get_settings, to_repo_path
from app.llm_client import LLMError
from app.parity_engine import ParityOutcome, run_parity
from app.pitfall_library import list_pitfalls
from app.schemas import ErrorBody, GeneratedFile, Iteration, LLMTraceEntry, Parity, RedevelopRequest, RedevelopResult, UnitTestSummary

FILE_KINDS = {
    "model.py": "model_code", "test_model.py": "unit_tests", "logic_spec.json": "logic_spec",
    "translation_notes.md": "notes", "scored_dev.csv": "scores_dev", "scored_oot.csv": "scores_oot",
    "parity_certificate.md": "certificate_md", "parity_certificate.json": "certificate_json",
    "mismatches.csv": "mismatch_sample", "result.json": "result",
}


class PipelineError(Exception):
    """A failure with an error code for the API response."""

    def __init__(self, code: str, message: str, http_status: int = 400):
        """Store the code, message and HTTP status."""
        super().__init__(message)
        self.code, self.message, self.http_status = code, message, http_status


@dataclass
class Evaluation:
    """Outcome of running the tests, the scoring and the parity check for one version of model.py."""

    tests_passed: int
    tests_failed: int
    test_output: str
    scoring_error: str | None
    outcome: ParityOutcome | None

    def all_good(self, has_golden: bool) -> bool:
        """True when tests pass, scoring ran, and parity passed (when golden outputs exist)."""
        if self.tests_failed or self.scoring_error:
            return False
        return self.outcome is not None and (self.outcome.parity.passed or not has_golden)


def load_manifest(estate_path: str) -> tuple[dict, Path]:
    """Read manifest.json of a model folder that must lie inside the estate folder."""
    estate_dir = get_settings().estate_dir.resolve()
    model_dir = (REPO_ROOT / estate_path).resolve()
    if model_dir != estate_dir and estate_dir not in model_dir.parents:
        raise PipelineError("INVALID_PATH", f"estate_path must be inside {to_repo_path(estate_dir)}")
    if model_dir.name.startswith("_"):
        raise PipelineError("INVALID_PATH", "estate_path must point to a model folder")
    manifest_path = model_dir / "manifest.json"
    if not manifest_path.exists():
        raise PipelineError("NOT_FOUND", f"No manifest.json in {estate_path}", 404)
    return json.loads(manifest_path.read_text(encoding="utf-8")), model_dir


def check_manifest(manifest: dict, model_id: str) -> None:
    """The manifest must match the model id and describe a SAS or R model with data."""
    if manifest.get("model_id") != model_id:
        raise PipelineError("MODEL_MISMATCH", f"manifest model_id is {manifest.get('model_id')}, request says {model_id}")
    if not manifest.get("redevelop") or manifest.get("language") not in {"SAS", "R"} or not manifest.get("data"):
        raise PipelineError("NOT_REDEVELOPABLE", f"Model {model_id} is not marked for redevelopment from SAS or R with data", 422)


def input_columns(manifest: dict, model_dir: Path) -> list[str]:
    """Raw columns that are neither id, target nor protected."""
    data = manifest["data"]
    columns = pd.read_csv(model_dir / data["dev_path"], nrows=0).columns
    excluded = {data["id_col"], data["target_col"], *data.get("protected_cols", [])}
    return [c for c in columns if c not in excluded]


def evaluate(code: str, tests: str, manifest: dict, model_dir: Path, out_dir: Path) -> Evaluation:
    """Run the unit tests and the scoring in the sandbox, then the parity check."""
    try:
        run, passed, failed = code_sandbox.run_tests(code, tests)
        test_output = (run.stdout + "\n" + run.stderr).strip()
    except code_sandbox.UnsafeCodeError as error:
        passed, failed, test_output = 0, 1, f"Rejected by the safety check: {error}"
    data = manifest["data"]
    scoring_error, outcome = None, None
    try:
        run, refit = code_sandbox.run_scoring(code, model_dir / data["dev_path"], model_dir / data["oot_path"], out_dir)
        if run.returncode != 0:
            scoring_error = (run.stderr or run.stdout)[-4000:]
    except code_sandbox.UnsafeCodeError as error:
        scoring_error = f"Rejected by the safety check: {error}"
    if scoring_error is None:
        outcome = run_parity(manifest, model_dir, out_dir / "scored_dev.csv", out_dir / "scored_oot.csv",
                             refit, out_dir / "model.py", out_dir)
    return Evaluation(passed, failed, test_output, scoring_error, outcome)


def heal_once(manifest: dict, model_dir: Path, code: str, evaluation: Evaluation, use_pitfalls: bool,
              iteration: int) -> tuple[self_healer.HealReply, object]:
    """Collect the failure evidence and ask the healer for a corrected model.py."""
    profile, mismatch_csv, levels = {}, "", []
    if evaluation.outcome is not None and not evaluation.outcome.comparison.empty:
        data = manifest["data"]
        inputs = pd.concat([pd.read_csv(model_dir / data[k]) for k in ("dev_path", "oot_path")], ignore_index=True)
        profile = mismatch_profiler.profile(evaluation.outcome.comparison, inputs, data["id_col"], input_columns(manifest, model_dir))
        sample = evaluation.outcome.parity.mismatch_sample_path
        mismatch_csv = self_healer.top_mismatches_csv(REPO_ROOT / sample if sample else None)
        levels = [level.model_dump() for level in evaluation.outcome.parity.levels]
    test_output = evaluation.test_output
    if evaluation.scoring_error:
        test_output += f"\n\nScoring dev and oot failed:\n{evaluation.scoring_error}"
    return self_healer.heal(manifest, code, test_output, mismatch_csv, profile, levels, use_pitfalls, iteration)


def max_pd_diff(evaluation: Evaluation) -> float | None:
    """Largest absolute PD difference of the L2 level, when it was computed."""
    if evaluation.outcome is None:
        return None
    return next((level.max_abs_diff for level in evaluation.outcome.parity.levels if level.level == "L2_record_scores"), None)


def attempt_rank(evaluation: Evaluation) -> tuple[bool, bool, int, int]:
    """How good one attempt is, best first: parity passed, scoring ran, parity levels passed, unit tests passed."""
    outcome = evaluation.outcome
    levels_passed = sum(level.status == "PASSED" for level in outcome.parity.levels) if outcome else 0
    return (bool(outcome and outcome.parity.passed), evaluation.scoring_error is None, levels_passed,
            evaluation.tests_passed)


def final_status(evaluation: Evaluation, has_golden: bool) -> str:
    """Honest final status from the last evaluation."""
    if evaluation.scoring_error:
        return "ERROR"
    if not has_golden:
        return "TRANSLATED_NO_GOLDEN"
    return "PARITY_PASSED" if evaluation.outcome.parity.passed else "PARITY_FAILED"


def generated_files(out_dir: Path) -> list[GeneratedFile]:
    """Every known output file that exists in out_dir."""
    return [GeneratedFile(path=to_repo_path(out_dir / name), kind=kind)
            for name, kind in FILE_KINDS.items() if (out_dir / name).exists()]


def run_redevelopment(request: RedevelopRequest, result: RedevelopResult, out_dir: Path) -> None:
    """The main flow; fills the result in place."""
    manifest, model_dir = load_manifest(request.estate_path)
    check_manifest(manifest, request.model_id)
    result.source_language = manifest["language"]
    has_golden = bool(manifest.get("golden"))
    if request.use_pitfall_library:
        result.pitfalls_checked = [p.id for p in list_pitfalls(manifest["language"])]
    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True)

    spec, response = code_analyzer.analyze(manifest, model_dir, out_dir)
    result.llm_trace.append(LLMTraceEntry(**response.trace()))
    reply, response = code_translator.translate(manifest, model_dir, spec, request.use_pitfall_library)
    result.llm_trace.append(LLMTraceEntry(**response.trace()))
    coefficients = code_translator.legacy_coefficients(manifest, model_dir)
    code = code_translator.inject_coefficients(reply.model_code, coefficients)
    (out_dir / "model.py").write_text(code, encoding="utf-8")
    tests, response = test_writer.write_tests(manifest, model_dir, spec, code)
    result.llm_trace.append(LLMTraceEntry(**response.trace()))
    (out_dir / "test_model.py").write_text(tests, encoding="utf-8")

    best_code, best_rank, best_number = code, None, 1
    for number in range(1, request.max_heal_iterations + 2):
        evaluation = evaluate(code, tests, manifest, model_dir, out_dir)
        iteration = Iteration(iteration=number, unit_tests_passed=evaluation.tests_passed,
                              unit_tests_failed=evaluation.tests_failed,
                              parity_passed=bool(evaluation.outcome and evaluation.outcome.parity.passed),
                              max_abs_diff_pd=max_pd_diff(evaluation), diagnosis=None, fix_applied=None)
        result.iterations.append(iteration)
        if best_rank is None or attempt_rank(evaluation) >= best_rank:
            best_code, best_rank, best_number = code, attempt_rank(evaluation), number
        if evaluation.all_good(has_golden) or number > request.max_heal_iterations:
            break
        healed, response = heal_once(manifest, model_dir, code, evaluation, request.use_pitfall_library, number)
        result.llm_trace.append(LLMTraceEntry(**response.trace()))
        iteration.diagnosis, iteration.fix_applied = healed.diagnosis, healed.fix_applied
        healed_code = code_translator.inject_coefficients(healed.model_code, coefficients)
        if healed_code == code:
            break  # the healer changed nothing, so another evaluation and LLM call would repeat this one
        code = healed_code
        (out_dir / "model.py").write_text(code, encoding="utf-8")

    heal_note = ""
    if best_code != code:
        # A later repair made the model worse: keep the best attempt and run it again (no LLM call) so the
        # scores, the parity files and model.py in out_dir all belong to the version that is returned.
        heal_note = (f"Attempt {best_number} of {len(result.iterations)} was kept because later repairs did not "
                     "improve on it (ranked by parity, then scoring, parity levels and unit tests passed).")
        code = best_code
        (out_dir / "model.py").write_text(code, encoding="utf-8")
        evaluation = evaluate(code, tests, manifest, model_dir, out_dir)

    result.status = final_status(evaluation, has_golden)
    result.unit_tests = UnitTestSummary(total=evaluation.tests_passed + evaluation.tests_failed,
                                        passed=evaluation.tests_passed, failed=evaluation.tests_failed)
    if evaluation.scoring_error:
        result.error = ErrorBody(code="SCORING_FAILED", message=evaluation.scoring_error[-1000:])
    if evaluation.outcome is not None:
        parity = evaluation.outcome.parity
        result.parity = parity_certificate.write_certificate(manifest["model_id"], parity, out_dir) if has_golden else parity
    mapping, problems = code_translator.build_line_mapping(code, out_dir / "model.py", manifest, model_dir)
    result.line_mapping = mapping
    code_translator.write_notes(out_dir / "translation_notes.md", manifest, spec, reply.pitfalls_applied, reply.notes, problems,
                                heal_note)


def redevelop(request: RedevelopRequest) -> RedevelopResult:
    """Run the full rebuild and always return a RedevelopResult (status ERROR on failure); write result.json."""
    started = time.perf_counter()
    out_dir = get_settings().artifacts_dir / request.model_id / "redevelop"
    result = RedevelopResult(model_id=request.model_id, run_id=request.run_id, status="ERROR", source_language="unknown")
    try:
        run_redevelopment(request, result, out_dir)
    except PipelineError:
        raise
    except LLMError as error:
        result.status, result.error = "ERROR", ErrorBody(code="LLM_ERROR", message=str(error))
    except Exception as error:  # noqa: BLE001 - any failure is reported honestly in the result
        result.status, result.error = "ERROR", ErrorBody(code="INTERNAL_ERROR", message=f"{type(error).__name__}: {error}")
    result.duration_seconds = round(time.perf_counter() - started, 1)
    if out_dir.exists():
        result.mlflow = mlflow_logger.log_run(result, out_dir)
        (out_dir / "result.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
        result.generated_files = generated_files(out_dir)
        (out_dir / "result.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return result


def parity_only(model_id: str, estate_path: str) -> Parity:
    """Re-run only the deterministic parity check on an existing rebuilt model.py."""
    manifest, model_dir = load_manifest(estate_path)
    check_manifest(manifest, model_id)
    out_dir = get_settings().artifacts_dir / model_id / "redevelop"
    model_path = out_dir / "model.py"
    if not model_path.exists():
        raise PipelineError("NOT_AVAILABLE", f"No rebuilt model at {to_repo_path(model_path)}", 404)
    data = manifest["data"]
    run, refit = code_sandbox.run_scoring(model_path.read_text(encoding="utf-8"),
                                          model_dir / data["dev_path"], model_dir / data["oot_path"], out_dir)
    if run.returncode != 0:
        raise PipelineError("SCORING_FAILED", (run.stderr or run.stdout)[-1000:], 422)
    (out_dir / "mismatches.csv").unlink(missing_ok=True)
    outcome = run_parity(manifest, model_dir, out_dir / "scored_dev.csv", out_dir / "scored_oot.csv", refit, model_path, out_dir)
    if not manifest.get("golden"):
        return outcome.parity
    return parity_certificate.write_certificate(model_id, outcome.parity, out_dir)
