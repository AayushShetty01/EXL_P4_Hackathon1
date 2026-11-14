"""Numbered file blocks for the agents' prompts."""

import pytest
from sqlmodel import Session

from app.agents.source_context import dictionary_path, numbered_file, source_paths
from app.config import Settings
from app.database import ModelRow
from app.estate_scanner import FileAccessError, register_estate
from tests.conftest import HERO_FOLDER


def test_numbered_file_has_a_header_and_padded_line_numbers(hero_estate: Settings) -> None:
    """Each line is prefixed with L and a four digit number under a header with the path."""
    block = numbered_file(hero_estate, f"{HERO_FOLDER}/code/02_train.sas")
    assert block.splitlines()[0] == f"=== FILE: {HERO_FOLDER}/code/02_train.sas (4 lines) ==="
    assert block.splitlines()[2] == "L0002: proc logistic data=work.dev_woe descending;"


def test_long_files_are_truncated_with_a_note(hero_estate: Settings) -> None:
    """Only the first lines are sent, and the prompt says so."""
    block = numbered_file(hero_estate, f"{HERO_FOLDER}/code/01_prepare.sas", max_lines=2)
    assert block.endswith("(truncated after 2 of 7 lines)")


def test_answer_keys_cannot_be_put_in_a_prompt(hero_estate: Settings) -> None:
    """The safe reader stops the answer keys before they reach a prompt."""
    with pytest.raises(FileAccessError):
        numbered_file(hero_estate, "model_estate/_answer_keys/M001.json")


def test_paths_come_from_the_registration(hero_estate: Settings, session: Session) -> None:
    """Code, document and data dictionary paths are taken from the registered manifest."""
    register_estate(session, hero_estate)
    registration = session.get(ModelRow, "M001").registration
    assert source_paths(registration, "doc") == [f"{HERO_FOLDER}/docs/model_document_2021.md"]
    assert len(source_paths(registration, "code")) == 3
    assert dictionary_path(registration, HERO_FOLDER) == f"{HERO_FOLDER}/data/data_dictionary.csv"
