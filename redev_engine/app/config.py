"""Settings for redev_engine, read from the root .env file, plus repository root detection."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

SERVICE_NAME = "redev_engine"
VERSION = "0.1.0"
SERVICE_DIR = Path(__file__).resolve().parents[1]


def find_repo_root(start: Path = SERVICE_DIR) -> Path:
    """Walk up from the service folder until a folder that contains model_estate/ is found."""
    for folder in [start, *start.parents]:
        if (folder / "model_estate").is_dir():
            return folder
    raise RuntimeError(f"No model_estate/ folder found above {start}")


REPO_ROOT = find_repo_root()
load_dotenv(REPO_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    """All run time settings of the service."""

    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_mode: str
    llm_temperature: float
    estate_dir: Path
    artifacts_dir: Path
    llm_cache_dir: Path
    stub_mode: bool
    mlflow_tracking_uri: str


def get_settings() -> Settings:
    """Read the settings from the environment each time, so tests can change them."""
    return Settings(
        llm_base_url=os.getenv("LLM_BASE_URL", ""),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_model=os.getenv("LLM_MODEL", ""),
        llm_mode=os.getenv("LLM_MODE", "live").lower(),
        llm_temperature=float(os.getenv("LLM_TEMPERATURE", "0") or 0),
        estate_dir=REPO_ROOT / os.getenv("ESTATE_DIR", "model_estate"),
        artifacts_dir=REPO_ROOT / os.getenv("ARTIFACTS_DIR", "artifacts"),
        llm_cache_dir=Path(os.getenv("REDEV_LLM_CACHE_DIR", str(SERVICE_DIR / "llm_cache"))),
        stub_mode=os.getenv("REDEV_STUB", "false").lower() == "true",
        mlflow_tracking_uri=os.getenv("MLFLOW_TRACKING_URI", ""),
    )


def to_repo_path(path: Path) -> str:
    """Path relative to the repository root with forward slashes (absolute if outside the repository)."""
    path = Path(path).resolve()
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()
