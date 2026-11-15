"""The evidence verifier: quotes are checked against the cited files by code."""

import pytest

from app.agents.evidence_verifier import EvidenceReply, find_quote, normalise, verify_evidence
from app.config import Settings
from tests.conftest import HERO_FOLDER

TRAIN = f"{HERO_FOLDER}/code/02_train.sas"


def check(settings: Settings, quote: str, start: int | None = 2, end: int | None = 2, file: str = TRAIN):
    """Verify one quote in the hero model folder."""
    return verify_evidence(
        settings, EvidenceReply(file=file, start_line=start, end_line=end, quote=quote), allowed_folder=HERO_FOLDER
    )


def test_quote_at_the_cited_lines_is_verified(hero_estate: Settings) -> None:
    """An exact quote at the cited line is VERIFIED with unchanged line numbers."""
    result = check(hero_estate, "proc logistic data=work.dev_woe descending;")
    assert (result.status, result.evidence.start_line, result.evidence.end_line) == ("VERIFIED", 2, 2)


def test_case_and_spacing_do_not_matter(hero_estate: Settings) -> None:
    """Whitespace and case are normalised before comparing."""
    assert check(hero_estate, "PROC   Logistic data=work.dev_woe").status == "VERIFIED"


def test_wrong_line_numbers_are_corrected(hero_estate: Settings) -> None:
    """A quote found elsewhere in the file is VERIFIED with corrected line numbers."""
    result = check(hero_estate, "model default_flag = woe_pay0 woe_util;", start=40, end=41)
    assert (result.status, result.evidence.start_line, result.evidence.end_line) == ("VERIFIED", 3, 3)
    assert "corrected" in result.note


def test_quote_across_lines_is_found(hero_estate: Settings) -> None:
    """A quote that spans two lines is matched and both lines are reported."""
    result = check(hero_estate, "descending; model default_flag", start=None, end=None)
    assert (result.status, result.evidence.start_line, result.evidence.end_line) == ("VERIFIED", 2, 3)


def test_invented_quote_is_unverified(hero_estate: Settings) -> None:
    """A quote that is not in the file is UNVERIFIED and never hidden."""
    result = check(hero_estate, "proc hpsplit data=work.dev_woe;")
    assert result.status == "UNVERIFIED"
    assert result.note == "Quote not found in the file."


def test_empty_quote_is_unverified(hero_estate: Settings) -> None:
    """Evidence without a quote cannot be verified."""
    assert check(hero_estate, "   ").status == "UNVERIFIED"


@pytest.mark.parametrize(
    "file",
    ["model_estate/_answer_keys/M001.json", "model_estate/other_model/code.sas", "factory_core/app/main.py"],
)
def test_files_outside_the_model_folder_are_never_evidence(hero_estate: Settings, file: str) -> None:
    """Answer keys, other models and source code of the service cannot verify a claim."""
    assert check(hero_estate, "secret", file=file).status == "UNVERIFIED"


def test_answer_keys_are_blocked_even_without_a_folder_limit(hero_estate: Settings) -> None:
    """The safe reader refuses the answer keys whatever the caller allows."""
    result = verify_evidence(hero_estate, EvidenceReply(file="model_estate/_answer_keys/M001.json", quote="secret"))
    assert result.status == "UNVERIFIED"
    assert "answer keys" in result.note


def test_normalise_and_find_quote_helpers() -> None:
    """Curly quotes become straight quotes; blank lines are skipped when locating a quote."""
    assert normalise("  It’s   HERE ") == "it's here"
    assert find_quote(["first line", "", "second LINE here"], "line second line") == (1, 3)
