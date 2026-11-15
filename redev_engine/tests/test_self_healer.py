"""Tests for the self healer."""

import pandas as pd

from app.self_healer import heal, top_mismatches_csv
from conftest import REFERENCE_MODEL


def test_heal_sends_evidence_and_returns_fix(fake_llm):
    """The prompt carries every piece of evidence and the reply is parsed."""
    fake_llm[0]["heal"] = {"diagnosis": "d", "fix_applied": "f", "model_code": REFERENCE_MODEL}
    manifest = {"model_id": "T001", "language": "SAS"}
    reply, response = heal(manifest, "old code", "1 failed in 0.1s", "ID,pd\n1,0.2\n", {"findings": ["x2 equal to 0"]},
                           [{"level": "L2_record_scores"}], use_pitfalls=True, iteration=2)
    prompt = fake_llm[1][0]["user"]
    assert reply.fix_applied == "f" and response.step == "heal_2"
    for evidence in ("old code", "1 failed", "ID,pd", "x2 equal to 0", "L2_record_scores", "SAS_DIVIDE_BY_ZERO"):
        assert evidence in prompt


def test_top_mismatches_are_limited_to_twenty(tmp_path):
    """Only the 20 largest mismatches are sent."""
    path = tmp_path / "mismatches.csv"
    pd.DataFrame({"ID": range(200)}).to_csv(path, index=False)
    assert len(top_mismatches_csv(path).strip().splitlines()) == 21
    assert top_mismatches_csv(None) == ""
