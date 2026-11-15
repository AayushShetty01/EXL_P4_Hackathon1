"""Four level parity comparison between legacy (golden) outputs and the rebuilt Python outputs. No LLM."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from app.config import to_repo_path
from app.schemas import Parity, ParityHashes, ParityLevel

TOLERANCE_PD = 1e-6
TOLERANCE_COEF = 1e-4
TOLERANCE_PSI = 1e-9
MISMATCH_SAMPLE_SIZE = 200


@dataclass
class ParityOutcome:
    """The Parity object plus the record level comparison used by the profiler and the healer."""

    parity: Parity
    comparison: pd.DataFrame


def sha256_of_files(paths: list[Path]) -> str | None:
    """One SHA 256 over the contents of several files in the given order (None when the list is empty)."""
    if not paths:
        return None
    digest = hashlib.sha256()
    for path in paths:
        digest.update(Path(path).read_bytes())
    return digest.hexdigest()


def read_scored(path: Path) -> pd.DataFrame:
    """Read a scored file with the columns ID, pd, score, decision."""
    frame = pd.read_csv(path)
    missing = {"ID", "pd", "score", "decision"} - set(frame.columns)
    if missing:
        raise ValueError(f"{path} lacks the columns {sorted(missing)}")
    return frame[["ID", "pd", "score", "decision"]]


def compare_records(legacy: pd.DataFrame, python: pd.DataFrame, sample: str) -> pd.DataFrame:
    """Outer join legacy and Python scores on ID and flag every kind of difference."""
    merged = legacy.merge(python, on="ID", how="outer", suffixes=("_legacy", "_python"), indicator=True)
    merged.insert(0, "sample", sample)
    merged["missing_side"] = merged.pop("_merge").map({"both": "", "left_only": "python", "right_only": "legacy"})
    merged["pd_abs_diff"] = (merged["pd_legacy"] - merged["pd_python"]).abs()
    merged["score_differs"] = merged["score_legacy"] != merged["score_python"]
    merged["decision_differs"] = merged["decision_legacy"].astype(str).str.strip() != merged["decision_python"].astype(str).str.strip()
    return merged


def psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    """Population stability index over decile bins of the expected (legacy) values."""
    edges = np.unique(np.quantile(expected, np.linspace(0, 1, bins + 1)))
    if len(edges) < 2:
        return 0.0 if np.array_equal(np.unique(expected), np.unique(actual)) else float("inf")
    edges[0], edges[-1] = -np.inf, np.inf
    expected_share = np.histogram(expected, edges)[0] / len(expected)
    actual_share = np.histogram(actual, edges)[0] / len(actual)
    eps = 1e-12
    return float(np.sum((actual_share - expected_share) * np.log((actual_share + eps) / (expected_share + eps))))


def level_coefficients(legacy_path: Path | None, refit: dict | None) -> ParityLevel:
    """L1: refitted Python coefficients against the legacy estimates."""
    if legacy_path is None:
        return ParityLevel(level="L1_coefficients", status="NOT_APPLICABLE", max_abs_diff=None, mismatched_records=None,
                           match_rate=None, psi=None, detail="The legacy model has no exported estimation step")
    legacy = pd.read_csv(legacy_path).set_index("variable")["estimate"].astype(float)
    if not refit:
        return ParityLevel(level="L1_coefficients", status="FAILED", max_abs_diff=None, mismatched_records=None,
                           match_rate=None, psi=None, detail="The rebuilt model has no fit() result to compare")
    refitted = pd.Series(refit, dtype=float)
    missing = sorted(set(legacy.index) - set(refitted.index))
    extra = sorted(set(refitted.index) - set(legacy.index))
    diffs = (legacy - refitted.reindex(legacy.index)).abs()
    max_diff = float(diffs.max()) if diffs.notna().any() else None
    within = int((diffs <= TOLERANCE_COEF).sum())
    passed = not missing and not extra and within == len(legacy)
    detail = f"{within} of {len(legacy)} refitted coefficients within tolerance of the legacy estimates"
    if missing or extra:
        detail += f"; missing {missing}; unexpected {extra}"
    return ParityLevel(level="L1_coefficients", status="PASSED" if passed else "FAILED", max_abs_diff=max_diff,
                       mismatched_records=None, match_rate=None, psi=None, detail=detail)


def level_scores(comparison: pd.DataFrame) -> ParityLevel:
    """L2: record by record PD comparison, no ids missing on either side."""
    missing_ids = int((comparison["missing_side"] != "").sum())
    bad = (comparison["pd_abs_diff"] > TOLERANCE_PD) | comparison["pd_abs_diff"].isna()
    max_diff = float(comparison["pd_abs_diff"].max()) if comparison["pd_abs_diff"].notna().any() else None
    detail = "PD compared record by record on dev and oot"
    if missing_ids:
        detail += f"; {missing_ids} ids present on one side only"
    return ParityLevel(level="L2_record_scores", status="FAILED" if bad.any() else "PASSED", max_abs_diff=max_diff,
                       mismatched_records=int(bad.sum()), match_rate=float(1 - bad.mean()), psi=None, detail=detail)


def level_decisions(comparison: pd.DataFrame) -> ParityLevel:
    """L3: score points and decision identical for every record."""
    bad = comparison["score_differs"] | comparison["decision_differs"]
    score_gap = (comparison["score_legacy"] - comparison["score_python"]).abs()
    return ParityLevel(
        level="L3_decisions", status="FAILED" if bad.any() else "PASSED",
        max_abs_diff=float(score_gap.max()) if score_gap.notna().any() else None,
        mismatched_records=int(bad.sum()), match_rate=float(1 - bad.mean()), psi=None,
        detail=f"Score points differ for {int(comparison['score_differs'].sum())} records, "
               f"decision differs for {int(comparison['decision_differs'].sum())} records",
    )


def level_distribution(comparison: pd.DataFrame) -> ParityLevel:
    """L4: PSI between legacy and Python output distributions over 10 bins (score, or pd when there is no score)."""
    both = comparison[comparison["missing_side"] == ""]
    column = "score" if both["score_legacy"].abs().sum() > 0 else "pd"
    value = psi(both[f"{column}_legacy"].to_numpy(float), both[f"{column}_python"].to_numpy(float))
    return ParityLevel(level="L4_distribution", status="PASSED" if value <= TOLERANCE_PSI else "FAILED",
                       max_abs_diff=None, mismatched_records=None, match_rate=None, psi=value,
                       detail=f"Distribution of {column} compared across 10 bins of the legacy output")


def not_applicable_levels(reason: str) -> list[ParityLevel]:
    """All four levels marked NOT_APPLICABLE with the same reason."""
    names = ["L1_coefficients", "L2_record_scores", "L3_decisions", "L4_distribution"]
    return [ParityLevel(level=n, status="NOT_APPLICABLE", max_abs_diff=None, mismatched_records=None,
                        match_rate=None, psi=None, detail=reason) for n in names]


def write_mismatch_sample(comparison: pd.DataFrame, data: pd.DataFrame, id_col: str, out_dir: Path) -> Path:
    """Write the 200 largest differences with their input columns to mismatches.csv."""
    flagged = comparison[mismatch_mask(comparison)].copy()
    flagged["sort_key"] = flagged["pd_abs_diff"].fillna(np.inf)
    top = flagged.sort_values(["sort_key", "ID"], ascending=[False, True]).head(MISMATCH_SAMPLE_SIZE).drop(columns="sort_key")
    top = top.merge(data.rename(columns={id_col: "ID"}), on="ID", how="left")
    path = out_dir / "mismatches.csv"
    top.to_csv(path, index=False)
    return path


def mismatch_mask(comparison: pd.DataFrame) -> pd.Series:
    """Records that differ at L2 or L3 or are missing on one side."""
    return ((comparison["pd_abs_diff"] > TOLERANCE_PD) | comparison["pd_abs_diff"].isna()
            | comparison["score_differs"] | comparison["decision_differs"])


def run_parity(manifest: dict, model_dir: Path, scored_dev: Path, scored_oot: Path, refit: dict | None,
               python_code: Path, out_dir: Path) -> ParityOutcome:
    """Run the four levels for one model and return the Parity object (certificate paths are filled in later)."""
    golden, data = manifest.get("golden"), manifest.get("data") or {}
    legacy_code = [model_dir / f for f in manifest["code_files"]]
    input_files = [model_dir / data[k] for k in ("dev_path", "oot_path") if data.get(k)]
    hashes = ParityHashes(
        legacy_code_sha256=sha256_of_files(legacy_code),
        python_code_sha256=sha256_of_files([python_code]) if Path(python_code).exists() else None,
        input_data_sha256=sha256_of_files(input_files),
        golden_output_sha256=None,
    )
    if not golden:
        parity = Parity(passed=False, records_compared=0, tolerance_pd=TOLERANCE_PD, tolerance_coef=TOLERANCE_COEF,
                        levels=not_applicable_levels("No legacy outputs exist to compare against"), hashes=hashes,
                        certificate_md_path=None, certificate_json_path=None, mismatch_sample_path=None)
        return ParityOutcome(parity, pd.DataFrame())

    coef_path = model_dir / golden["coefficients_path"] if golden.get("coefficients_path") else None
    golden_files = [model_dir / golden["scored_dev_path"], model_dir / golden["scored_oot_path"]] + ([coef_path] if coef_path else [])
    hashes.golden_output_sha256 = sha256_of_files(golden_files)
    comparison = pd.concat([
        compare_records(read_scored(golden_files[0]), read_scored(scored_dev), "dev"),
        compare_records(read_scored(golden_files[1]), read_scored(scored_oot), "oot"),
    ], ignore_index=True)
    levels = [level_coefficients(coef_path, refit), level_scores(comparison),
              level_decisions(comparison), level_distribution(comparison)]
    passed = all(level.status in {"PASSED", "NOT_APPLICABLE"} for level in levels)
    sample_path = None
    if not passed and mismatch_mask(comparison).any():
        inputs = pd.concat([pd.read_csv(p) for p in input_files], ignore_index=True)
        sample_path = to_repo_path(write_mismatch_sample(comparison, inputs, data["id_col"], out_dir))
    parity = Parity(passed=passed, records_compared=int(len(comparison)), tolerance_pd=TOLERANCE_PD,
                    tolerance_coef=TOLERANCE_COEF, levels=levels, hashes=hashes, certificate_md_path=None,
                    certificate_json_path=None, mismatch_sample_path=sample_path)
    return ParityOutcome(parity, comparison)
