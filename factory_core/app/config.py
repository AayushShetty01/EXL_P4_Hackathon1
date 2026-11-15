"""Settings for factory_core, read from the root .env file and the environment.

Also finds the repository root, so every path in a payload can be made relative to it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Request

SERVICE_NAME = "factory_core"
SERVICE_VERSION = "0.1.0"
DASHBOARD_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")
LLM_MODES = ("live", "replay")


@dataclass(frozen=True)
class Settings:
    """Every setting factory_core uses. Paths are absolute."""

    repository_root: Path
    estate_dir: Path
    artifacts_dir: Path
    contracts_examples_dir: Path
    database_path: Path
    checkpoints_path: Path
    llm_cache_dir: Path
    llm_base_url: str
    llm_api_key: str = field(repr=False)
    llm_model: str
    llm_model_validator: str
    llm_mode: str
    llm_temperature: float
    redev_engine_url: str
    validation_lab_url: str
    use_stubs: bool
    mlflow_tracking_uri: str
    allowed_origins: tuple[str, ...] = DASHBOARD_ORIGINS


def find_repository_root(start: Path | None = None) -> Path:
    """Walk up from this file to the folder that holds both factory_core/ and contracts/."""
    current = (start or Path(__file__)).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "factory_core").is_dir() and (candidate / "contracts").is_dir():
            return candidate
    raise RuntimeError(f"Repository root not found above {current}")


def parse_bool(value: str) -> bool:
    """Read true, 1, yes or on (any case) as True and everything else as False."""
    return value.strip().lower() in {"true", "1", "yes", "on"}


def load_settings() -> Settings:
    """Load the root .env (existing environment variables win) and build the settings."""
    root = find_repository_root()
    load_dotenv(root / ".env", override=False)
    environment = os.environ
    llm_mode = environment.get("LLM_MODE", "live").strip().lower()
    if llm_mode not in LLM_MODES:
        raise ValueError(f"LLM_MODE must be one of {', '.join(LLM_MODES)}, got {llm_mode!r}")
    artifacts_dir = root / environment.get("ARTIFACTS_DIR", "artifacts")
    return Settings(
        repository_root=root,
        estate_dir=root / environment.get("ESTATE_DIR", "model_estate"),
        artifacts_dir=artifacts_dir,
        contracts_examples_dir=root / "contracts" / "examples",
        database_path=artifacts_dir / "factory_core.db",
        checkpoints_path=artifacts_dir / "pipeline_checkpoints.db",
        llm_cache_dir=root / "factory_core" / "llm_cache",
        llm_base_url=environment.get("LLM_BASE_URL", ""),
        llm_api_key=environment.get("LLM_API_KEY", ""),
        llm_model=environment.get("LLM_MODEL", ""),
        llm_model_validator=environment.get("LLM_MODEL_VALIDATOR", ""),
        llm_mode=llm_mode,
        llm_temperature=float(environment.get("LLM_TEMPERATURE", "0") or 0),
        redev_engine_url=environment.get("REDEV_ENGINE_URL", "http://localhost:8001"),
        validation_lab_url=environment.get("VALIDATION_LAB_URL", "http://localhost:8002"),
        use_stubs=parse_bool(environment.get("USE_STUBS", "false")),
        mlflow_tracking_uri=environment.get("MLFLOW_TRACKING_URI", ""),
    )


def request_settings(request: Request) -> Settings:
    """FastAPI dependency that returns the settings the app was created with."""
    return request.app.state.settings
