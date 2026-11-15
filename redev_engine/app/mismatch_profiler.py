"""Finds where parity mismatches concentrate, by comparing mismatched and matched records. No LLM."""

import numpy as np
import pandas as pd

from app.parity_engine import mismatch_mask

CONCENTRATION_SHARE = 0.9
MAX_VALUES_IN_FINDING = 3


def value_concentration(column: pd.Series, flagged: pd.Series) -> str | None:
    """Finding when at most three values (missing counts as a value) cover 90 percent of the mismatches but few matches."""
    keys = column.astype(object).where(column.notna(), "missing")
    mismatched, matched = keys[flagged], keys[~flagged]
    counts = mismatched.value_counts()
    top = counts.head(MAX_VALUES_IN_FINDING)
    covered = top.cumsum() / len(mismatched)
    needed = int(np.argmax(covered.to_numpy() >= CONCENTRATION_SHARE)) + 1 if (covered >= CONCENTRATION_SHARE).any() else 0
    if not needed:
        return None
    values = list(top.index[:needed])
    matched_share = matched.isin(values).mean() if len(matched) else 0.0
    mismatched_share = mismatched.isin(values).mean()
    if matched_share > 0.5 * mismatched_share:
        return None
    shown = " or ".join(str(v) for v in values)
    return (f"{int(mismatched.isin(values).sum())} of {len(mismatched)} mismatched records have {column.name} equal to "
            f"{shown}, against {matched_share:.1%} of matched records")


def score_gap_pattern(comparison: pd.DataFrame) -> str | None:
    """Finding when every score difference is exactly one point, the usual sign of a rounding rule difference."""
    differs = comparison[comparison["score_differs"] & (comparison["missing_side"] == "")]
    if differs.empty:
        return None
    gaps = (differs["score_legacy"] - differs["score_python"]).abs()
    if (gaps == 1).all():
        direction = "higher" if (differs["score_legacy"] > differs["score_python"]).all() else "different"
        return (f"All {len(differs)} score differences are exactly 1 point (legacy {direction}) while PD agrees, "
                "which points to a rounding rule difference at exact halves")
    return f"{len(differs)} records have different score points, largest gap {gaps.max():g}"


def profile(comparison: pd.DataFrame, data: pd.DataFrame, id_col: str, input_columns: list[str]) -> dict:
    """Profile the mismatches against the raw inputs and return findings plus counts."""
    flagged_frame = comparison.assign(flagged=mismatch_mask(comparison))
    joined = flagged_frame.merge(data.rename(columns={id_col: "ID"}), on="ID", how="left")
    flagged = joined["flagged"]
    findings = []
    if flagged.any():
        missing_ids = int((joined["missing_side"] != "").sum())
        if missing_ids:
            findings.append(f"{missing_ids} ids are present on one side only")
        for column in input_columns:
            if column in joined.columns:
                finding = value_concentration(joined[column], flagged)
                if finding:
                    findings.append(finding)
        pattern = score_gap_pattern(comparison)
        if pattern:
            findings.append(pattern)
        if not findings:
            findings.append("No single input value explains the mismatches; they are spread across the inputs")
    return {"mismatched_records": int(flagged.sum()), "records_compared": int(len(joined)), "findings": findings}
