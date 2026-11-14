"""Settings loading and repository root detection."""

import pytest

from app import config
from app.config import find_repository_root, load_settings, parse_bool


def test_repository_root_holds_factory_core_and_contracts() -> None:
    """The detected root contains both factory_core/ and contracts/."""
    root = find_repository_root()
    assert (root / "factory_core").is_dir()
    assert (root / "contracts").is_dir()


@pytest.mark.parametrize(
    ("text", "expected"), [("true", True), ("YES", True), ("1", True), ("false", False), ("", False)]
)
def test_parse_bool(text: str, expected: bool) -> None:
    """Common spellings of true and false are understood."""
    assert parse_bool(text) is expected


def test_load_settings_reads_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Environment values win and paths are made absolute under the repository root."""
    monkeypatch.setattr(config, "load_dotenv", lambda *args, **kwargs: False)
    monkeypatch.setenv("USE_STUBS", "yes")
    monkeypatch.setenv("ARTIFACTS_DIR", "custom_artifacts")
    monkeypatch.setenv("LLM_MODE", "Replay")
    monkeypatch.setenv("LLM_TEMPERATURE", "0.2")
    settings = load_settings()
    assert settings.use_stubs is True
    assert settings.llm_mode == "replay"
    assert settings.llm_temperature == 0.2
    assert settings.artifacts_dir == settings.repository_root / "custom_artifacts"
    assert settings.database_path == settings.artifacts_dir / "factory_core.db"


def test_unknown_llm_mode_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM_MODE must be live or replay."""
    monkeypatch.setattr(config, "load_dotenv", lambda *args, **kwargs: False)
    monkeypatch.setenv("LLM_MODE", "offline")
    with pytest.raises(ValueError, match="LLM_MODE"):
        load_settings()


def test_api_key_never_appears_in_settings_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """Printing or logging the settings does not reveal the LLM key."""
    monkeypatch.setattr(config, "load_dotenv", lambda *args, **kwargs: False)
    monkeypatch.setenv("LLM_API_KEY", "not-a-real-key-123")
    monkeypatch.setenv("LLM_MODE", "live")
    assert "not-a-real-key-123" not in repr(load_settings())
