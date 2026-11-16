"""Formats model files with numbered lines for the agents' prompts (format L0012: text).

Files are read through the safe reader, so prompts never contain the answer keys or files outside the
estate and artifacts folders. Records and results go into prompts without the fields that change from run
to run, so the same work always gives the same prompt and replay mode can serve the recorded reply.
"""

import json
from typing import Any

from app.config import Settings
from app.estate_scanner import read_text_file

MAX_LINES_PER_FILE = 800
RUN_SPECIFIC_FIELDS = frozenset(
    {"created_at", "updated_at", "revalidation_required", "pipeline_status", "run_id", "duration_seconds"}
)


def prompt_json(payload: dict[str, Any], leave_out: frozenset[str] = frozenset()) -> str:
    """A record or result as prompt JSON, without the fields that change from run to run."""
    kept = {key: value for key, value in payload.items() if key not in RUN_SPECIFIC_FIELDS | leave_out}
    return json.dumps(kept, indent=1, sort_keys=True)


def numbered_file(settings: Settings, path: str, max_lines: int = MAX_LINES_PER_FILE) -> str:
    """One file as a block of numbered lines under a header with its repository path."""
    view = read_text_file(settings, path)
    lines = view.content.splitlines()
    body = "\n".join(f"L{number:04d}: {line}" for number, line in enumerate(lines[:max_lines], start=1))
    note = f"\n(truncated after {max_lines} of {len(lines)} lines)" if len(lines) > max_lines else ""
    return f"=== FILE: {view.path} ({view.lines} lines) ===\n{body}{note}"


def numbered_files(settings: Settings, paths: list[str]) -> str:
    """Several files as numbered blocks, separated by blank lines."""
    return "\n\n".join(numbered_file(settings, path) for path in paths)


def source_paths(registration: dict[str, Any], kind: str) -> list[str]:
    """Repository paths of the registered files of one kind: code or doc."""
    return [source["path"] for source in registration.get("source_files", []) if source["kind"] == kind]


def dictionary_path(registration: dict[str, Any], folder: str) -> str | None:
    """Repository path of the data dictionary named in the manifest, if any."""
    data = (registration.get("manifest") or {}).get("data") or {}
    return f"{folder}/{data['dictionary_path']}" if data.get("dictionary_path") else None
