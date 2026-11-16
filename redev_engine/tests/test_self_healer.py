"""Tests for the self healer."""

import pandas as pd

import sys

from app.config import REPO_ROOT
from app.self_healer import SYSTEM_PROMPT, heal, stable_text, top_mismatches_csv
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


def test_healer_is_told_what_an_l1_failure_means():
    """With L1 failed and L2 to L4 passed the healer is pointed at fit() and its convergence."""
    text = " ".join(SYSTEM_PROMPT.split())
    assert "If L1_coefficients failed while L2 to L4 passed, scoring is right and fit() is wrong" in text
    assert "Newton or IRLS" in text


def test_test_output_is_the_same_in_every_run():
    """Sandbox folders, local paths, run times and addresses are replaced, so the heal prompt can be replayed."""
    first = (f'File "/private/var/folders/g4/T/redev_sandbox_vmbdn4nn/model.py", line 204, in score\n'
             f'  File "{sys.prefix}/lib/python3.11/site-packages/pandas/core/frame.py", line 4102\n'
             f"  File \"{REPO_ROOT}/artifacts/x.py\"\n<object at 0x10f3a2b50>\n15 failed, 54 passed in 0.88s")
    second = (first.replace("redev_sandbox_vmbdn4nn", "redev_sandbox_q81zz0ab").replace("0.88s", "61.23s (0:01:01)")
              .replace("0x10f3a2b50", "0x7f9e44c1d0"))
    assert stable_text(first) == stable_text(second)
    stable = stable_text(first)
    assert '"<sandbox>/model.py"' in stable and "<python>/lib/python3.11" in stable and "<repo>/artifacts" in stable
    assert stable.endswith("15 failed, 54 passed in <time>") and "redev_sandbox" not in stable


def test_heal_prompt_does_not_change_with_run_details(fake_llm):
    """Two runs that differ only in sandbox folder and run time send the same heal prompt."""
    fake_llm[0]["heal"] = {"diagnosis": "d", "fix_applied": "f", "model_code": REFERENCE_MODEL}
    manifest = {"model_id": "T001", "language": "R"}
    for folder, seconds in (("redev_sandbox_aaaa1111", "0.88"), ("redev_sandbox_bbbb2222", "1.07")):
        heal(manifest, "code", f"/tmp/{folder}/model.py: 1 failed in {seconds}s", "", {}, [], use_pitfalls=False, iteration=1)
    assert fake_llm[1][0]["user"] == fake_llm[1][1]["user"]


def test_top_mismatches_are_limited_to_twenty(tmp_path):
    """Only the 20 largest mismatches are sent."""
    path = tmp_path / "mismatches.csv"
    pd.DataFrame({"ID": range(200)}).to_csv(path, index=False)
    assert len(top_mismatches_csv(path).strip().splitlines()) == 21
    assert top_mismatches_csv(None) == ""
