"""Tests for the unit test writer."""

from app.test_writer import write_tests
from conftest import PASSING_TESTS, REFERENCE_MODEL, SPEC_REPLY


def test_write_tests_returns_code_and_sends_rules(tiny_estate, fake_llm):
    """The reply is the test file and the prompt includes rules, legacy source and model.py."""
    folder, manifest = tiny_estate
    fake_llm[0]["write_tests"] = {"test_code": PASSING_TESTS}
    code, response = write_tests(manifest, folder, SPEC_REPLY, REFERENCE_MODEL)
    prompt = fake_llm[1][0]["user"]
    assert code == PASSING_TESTS and response.step == "write_tests"
    assert "zero denominators" in prompt and "=== code/model.R ===" in prompt and "def prepare(df):" in prompt
