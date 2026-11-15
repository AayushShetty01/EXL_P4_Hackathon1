"""Export the real response of every GET endpoint as static files for the dashboard's snapshot mode.

Run from the factory_core folder: python -m scripts.export_snapshot [--output PATH]
The layout follows section 9.4 of docs/PROJECT_CONTEXT.md. The default output is artifacts/snapshot/;
copy that folder into factory_console/public/snapshot/. A missing file means NOT_AVAILABLE.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.config import Settings, load_settings
from app.database import RunRow
from app.main import create_app

RESULT_ENDPOINTS = ("documentation", "redevelopment", "validation", "monitoring", "compliance")
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".svg", ".html", ".docx", ".pdf"}
REFERENCE_PREFIXES = ("model_estate/", "artifacts/")


def write_json(folder: Path, relative: str, payload: Any) -> None:
    """Write one snapshot file."""
    target = folder / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def referenced_paths(payload: Any) -> set[str]:
    """Every repository path mentioned in a response, such as evidence files, charts and reports."""
    found: set[str] = set()
    if isinstance(payload, dict):
        for value in payload.values():
            found |= referenced_paths(value)
    elif isinstance(payload, list):
        for value in payload:
            found |= referenced_paths(value)
    elif isinstance(payload, str) and payload.startswith(REFERENCE_PREFIXES) and "_answer_keys" not in payload:
        found.add(payload)
    return found


def clear_output(settings: Settings, output: Path) -> None:
    """Remove an earlier snapshot; only a folder inside artifacts/ may ever be cleared."""
    if not output.exists():
        return
    if not output.resolve().is_relative_to(settings.artifacts_dir.resolve()):
        raise SystemExit(f"Refusing to clear {output}: the snapshot output must be inside {settings.artifacts_dir}")
    shutil.rmtree(output)


class SnapshotWriter:
    """Saves API responses and the files they mention into one snapshot folder."""

    def __init__(self, settings: Settings, client: TestClient, output: Path) -> None:
        """Keep the app client, the output folder and the counters."""
        self.settings = settings
        self.client = client
        self.output = output
        self.counts = {"endpoints": 0, "files": 0, "artifacts": 0, "skipped": 0}
        self.references: set[str] = set()

    def save(self, relative: str, url: str, **params: Any) -> None:
        """Save one GET response when it succeeds; a failed one stays missing."""
        response = self.client.get(url, params=params)
        if response.status_code == 200:
            write_json(self.output, relative, response.json())
            self.references.update(referenced_paths(response.json()))
            self.counts["endpoints"] += 1

    def save_endpoints(self) -> None:
        """Save the factory wide endpoints, every model's endpoints and every run."""
        self.save("models.json", "/api/models")
        self.save("metrics.json", "/api/metrics/factory")
        self.save("audit.json", "/api/audit", limit=5000)
        for model in self.client.get("/api/models").json()["models"]:
            model_id = model["model_id"]
            self.save(f"models/{model_id}.json", f"/api/models/{model_id}")
            for endpoint in RESULT_ENDPOINTS:
                self.save(f"models/{model_id}/{endpoint}.json", f"/api/models/{model_id}/{endpoint}")
        with Session(self.client.app.state.engine) as session:
            run_ids = [run.run_id for run in session.exec(select(RunRow))]
        for run_id in run_ids:
            self.save(f"runs/{run_id}.json", f"/api/runs/{run_id}")

    def save_reference(self, path: str) -> None:
        """Copy a binary artifact, or save a text file in the file view shape."""
        if Path(path).suffix.lower() in BINARY_SUFFIXES:
            source = self.settings.repository_root / path
            if not source.is_file():
                self.counts["skipped"] += 1
                return
            target = self.output / "artifacts" / path.removeprefix("artifacts/")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            self.counts["artifacts"] += 1
            return
        response = self.client.get("/api/files", params={"path": path})
        if response.status_code != 200:
            self.counts["skipped"] += 1
            return
        write_json(self.output, f"files/{path.replace('/', '__')}.json", response.json())
        self.counts["files"] += 1


def export(settings: Settings, output: Path) -> dict[str, int]:
    """Write the whole snapshot and return how many files of each kind were written."""
    clear_output(settings, output)
    with TestClient(create_app(settings, recover_runs=False)) as client:
        writer = SnapshotWriter(settings, client, output)
        writer.save_endpoints()
        for path in sorted(writer.references):
            writer.save_reference(path)
    return writer.counts


def main(argv: list[str] | None = None) -> int:
    """Read the arguments and export the snapshot."""
    settings = load_settings()
    parser = argparse.ArgumentParser(description="Export every GET response for the dashboard's snapshot mode.")
    parser.add_argument("--output", type=Path, default=settings.artifacts_dir / "snapshot")
    arguments = parser.parse_args(argv)
    counts = export(settings, arguments.output)
    print(
        f"Snapshot written to {arguments.output}: {counts['endpoints']} endpoint responses, {counts['files']} files, "
        f"{counts['artifacts']} artifacts, {counts['skipped']} references not available."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
