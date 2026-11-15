"""Tests for the HTTP API."""

import json

import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture
def client(settings_env):
    """Test client with isolated settings."""
    return TestClient(main.app)


def test_health(client):
    """GET /health returns the shared shape."""
    assert client.get("/health").json() == {"status": "ok", "service": "redev_engine", "version": "0.1.0"}


def test_pitfalls(client):
    """GET /pitfalls lists the library with all fields."""
    pitfalls = client.get("/pitfalls").json()["pitfalls"]
    assert len(pitfalls) >= 18 and set(pitfalls[0]) == {"id", "language", "title", "description", "python_fix"}


def test_stub_mode_returns_example_with_request_ids(client, monkeypatch, tmp_path):
    """With REDEV_STUB=true the contract example comes back with the ids of the request."""
    from test_schemas import EXAMPLE

    example = tmp_path / "redevelop_result.M001.json"
    example.write_text(json.dumps(EXAMPLE))
    monkeypatch.setattr(main, "STUB_EXAMPLE", example)
    monkeypatch.setenv("REDEV_STUB", "true")
    body = client.post("/redevelop", json={"run_id": "run_M002_007", "model_id": "M002", "estate_path": "x"}).json()
    assert body["run_id"] == "run_M002_007" and body["model_id"] == "M002"
    assert body["generated_files"][0]["path"] == "artifacts/M002/redevelop/model.py"


def test_errors_use_the_shared_format(client):
    """Bad paths and bad bodies return {'error': {'code', 'message'}}."""
    response = client.post("/redevelop", json={"run_id": "r", "model_id": "M001", "estate_path": "../outside"})
    assert response.status_code == 400 and response.json()["error"]["code"] == "INVALID_PATH"
    response = client.post("/redevelop", json={"model_id": "M001"})
    assert response.status_code == 422 and response.json()["error"]["code"] == "INVALID_REQUEST"


def test_parity_without_rebuilt_model_is_not_available(client, tiny_estate):
    """POST /parity before any rebuild returns 404 NOT_AVAILABLE."""
    folder, _ = tiny_estate
    response = client.post("/parity", json={"model_id": "T001", "estate_path": str(folder)})
    assert response.status_code == 404 and response.json()["error"]["code"] == "NOT_AVAILABLE"


def test_parity_reruns_on_existing_model(client, tiny_estate, settings_env):
    """POST /parity scores the existing model.py and returns a passing Parity with a certificate."""
    from conftest import REFERENCE_MODEL
    from app.code_translator import inject_coefficients, legacy_coefficients

    folder, manifest = tiny_estate
    out = settings_env / "artifacts" / "T001" / "redevelop"
    out.mkdir(parents=True)
    (out / "model.py").write_text(inject_coefficients(REFERENCE_MODEL, legacy_coefficients(manifest, folder)))
    body = client.post("/parity", json={"model_id": "T001", "estate_path": str(folder)}).json()
    assert body["passed"] and body["certificate_md_path"].endswith("parity_certificate.md")
