"""Application setup: health, dashboard origin, routes and startup registration."""

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import load_example

PUBLIC_ROUTES = {
    "/api/models",
    "/api/estate/scan",
    "/api/models/{model_id}",
    "/api/models/{model_id}/runs",
    "/api/runs/{run_id}",
    "/api/runs/{run_id}/gates/{stage}/decision",
    "/api/models/{model_id}/documentation",
    "/api/models/{model_id}/redevelopment",
    "/api/models/{model_id}/validation",
    "/api/models/{model_id}/monitoring",
    "/api/models/{model_id}/compliance",
    "/api/audit",
    "/api/metrics/factory",
    "/api/files",
    "/api/artifacts/{path}",
}


def test_health_follows_the_shared_convention(client: TestClient) -> None:
    """GET /health answers with status, service name and version."""
    assert client.get("/health").json() == {"status": "ok", "service": "factory_core", "version": "0.1.0"}


def test_every_public_endpoint_of_the_contract_exists(client: TestClient) -> None:
    """Every path of section 9.3 is registered."""
    assert PUBLIC_ROUTES <= set(client.app.openapi()["paths"])


def test_dashboard_origin_is_allowed(client: TestClient) -> None:
    """The dashboard at localhost:5173 may call the API from the browser."""
    response = client.options(
        "/api/models", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"}
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_other_origins_are_not_allowed(client: TestClient) -> None:
    """Other web pages get no CORS permission."""
    response = client.get("/api/models", headers={"Origin": "http://elsewhere.test"})
    assert "access-control-allow-origin" not in response.headers


def test_startup_registers_the_sample_when_the_estate_is_empty(client: TestClient) -> None:
    """With no estate models the API still lists one model, the labelled sample."""
    [model] = client.get("/api/models").json()["models"]
    assert model["model_id"] == "M001"
    assert model["model_name"].endswith("(sample from contract examples)")


def test_startup_registers_estate_models(estate_client: TestClient) -> None:
    """With an estate on disk the real models are registered at startup."""
    [model] = estate_client.get("/api/models").json()["models"]
    assert model["model_name"] == "Credit Card PD Scorecard"


def test_startup_survives_a_broken_manifest(hero_estate) -> None:
    """A broken manifest is logged; the API still starts and serves the sample."""
    (hero_estate.repository_root / "model_estate/M001_cc_pd_scorecard_sas/manifest.json").write_text("{broken")
    with TestClient(create_app(hero_estate)) as broken_client:
        models = broken_client.get("/api/models").json()["models"]
    assert [model["model_id"] for model in models] == [load_example("inventory_record.M001.json")["model_id"]]
