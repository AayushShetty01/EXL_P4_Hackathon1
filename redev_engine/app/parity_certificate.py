"""Writes the parity certificate in markdown and JSON from a Parity object."""

import json
from datetime import datetime, timezone
from pathlib import Path

from app.config import to_repo_path
from app.schemas import Parity

CONVERGENCE_NOTE = (
    "Level L1 compares re-estimated coefficients. Small differences are expected because SAS, R and Python "
    "optimisers stop on different convergence rules. Levels L2 to L4 use the deployed legacy coefficients, so "
    "they prove that the scoring implementation is identical."
)


def format_number(value: float | int | None) -> str:
    """Readable number for the markdown table."""
    if value is None:
        return "n/a"
    if isinstance(value, float) and value != 0 and (abs(value) < 1e-3 or abs(value) >= 1e6):
        return f"{value:.3e}"
    return f"{value:.6g}" if isinstance(value, float) else str(value)


def render_markdown(model_id: str, issued_at: str, parity: Parity) -> str:
    """Markdown text of the certificate."""
    verdict = "PASSED" if parity.passed else "NOT PASSED"
    lines = [
        f"# Parity certificate, model {model_id}",
        "",
        f"* Issued: {issued_at}",
        f"* Overall result: **{verdict}** (every applicable level must pass)",
        f"* Records compared: {parity.records_compared}",
        f"* Tolerances: PD {parity.tolerance_pd:g}, coefficients {parity.tolerance_coef:g}, PSI 1e-09",
        "",
        "| Level | Status | Max abs difference | Mismatched records | Match rate | PSI | Detail |",
        "|---|---|---|---|---|---|---|",
    ]
    for level in parity.levels:
        lines.append(
            f"| {level.level} | {level.status} | {format_number(level.max_abs_diff)} | "
            f"{format_number(level.mismatched_records)} | {format_number(level.match_rate)} | "
            f"{format_number(level.psi)} | {level.detail} |"
        )
    lines += ["", "## Reproducibility hashes (SHA 256)", ""]
    lines += [f"* {name}: `{value}`" for name, value in parity.hashes.model_dump().items()]
    if parity.mismatch_sample_path:
        lines += ["", f"Largest mismatches: `{parity.mismatch_sample_path}`"]
    lines += ["", "## Note", "", CONVERGENCE_NOTE, ""]
    return "\n".join(lines)


def write_certificate(model_id: str, parity: Parity, out_dir: Path) -> Parity:
    """Write parity_certificate.md and .json into out_dir and return the Parity with both paths set."""
    out_dir.mkdir(parents=True, exist_ok=True)
    issued_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    md_path, json_path = out_dir / "parity_certificate.md", out_dir / "parity_certificate.json"
    parity = parity.model_copy(update={"certificate_md_path": to_repo_path(md_path),
                                       "certificate_json_path": to_repo_path(json_path)})
    md_path.write_text(render_markdown(model_id, issued_at, parity), encoding="utf-8")
    payload = {"model_id": model_id, "issued_at": issued_at, "note": CONVERGENCE_NOTE, **parity.model_dump()}
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return parity
