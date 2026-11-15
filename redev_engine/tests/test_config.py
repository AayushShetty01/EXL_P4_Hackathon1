"""Tests for settings and path helpers."""

from app.config import REPO_ROOT, find_repo_root, get_settings, to_repo_path


def test_repo_root_contains_the_estate():
    """The detected root holds model_estate/."""
    assert (find_repo_root() / "model_estate").is_dir() and find_repo_root() == REPO_ROOT


def test_paths_are_relative_with_forward_slashes():
    """Paths inside the repository are relative to its root."""
    assert to_repo_path(REPO_ROOT / "artifacts" / "M001" / "x.csv") == "artifacts/M001/x.csv"


def test_settings_follow_the_environment(monkeypatch):
    """Settings are read from the environment at call time."""
    monkeypatch.setenv("REDEV_STUB", "true")
    monkeypatch.setenv("LLM_MODE", "REPLAY")
    settings = get_settings()
    assert settings.stub_mode and settings.llm_mode == "replay"
