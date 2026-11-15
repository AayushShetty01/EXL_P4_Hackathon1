"""Tests for the parity certificate writer."""

import json

from app.parity_certificate import render_markdown, write_certificate
from app.schemas import Parity, ParityHashes, ParityLevel


def sample_parity(passed=True):
    """A small Parity object."""
    level = ParityLevel(level="L2_record_scores", status="PASSED" if passed else "FAILED", max_abs_diff=3.1e-9,
                        mismatched_records=0, match_rate=1.0, psi=None, detail="PD compared record by record")
    hashes = ParityHashes(legacy_code_sha256="a" * 64, python_code_sha256="b" * 64, input_data_sha256="c" * 64, golden_output_sha256="d" * 64)
    return Parity(passed=passed, records_compared=30000, tolerance_pd=1e-6, tolerance_coef=1e-4, levels=[level],
                  hashes=hashes, certificate_md_path=None, certificate_json_path=None, mismatch_sample_path=None)


def test_certificate_files_are_written_with_paths(tmp_path):
    """Both files are written and their paths are set on the returned Parity."""
    parity = write_certificate("M001", sample_parity(), tmp_path)
    assert parity.certificate_md_path.endswith("parity_certificate.md")
    payload = json.loads((tmp_path / "parity_certificate.json").read_text())
    assert payload["model_id"] == "M001" and payload["records_compared"] == 30000
    assert "convergence" in payload["note"]


def test_markdown_states_verdict_numbers_and_hashes():
    """The markdown shows the verdict, record count, level numbers and hashes."""
    text = render_markdown("M001", "2026-11-15T10:00:00Z", sample_parity(passed=False))
    assert "NOT PASSED" in text and "30000" in text and "3.100e-09" in text and "a" * 64 in text
