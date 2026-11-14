"""Every error answers with the contract body {"error": {"code": ..., "message": ...}}."""

from fastapi.testclient import TestClient

from app.api.api_errors import api_error


def test_api_error_carries_code_and_message() -> None:
    """The helper builds an HTTP exception with the contract detail."""
    error = api_error(404, "NOT_AVAILABLE", "No documentation yet")
    assert (error.status_code, error.detail) == (404, {"code": "NOT_AVAILABLE", "message": "No documentation yet"})


def test_unknown_route_uses_the_error_body(client: TestClient) -> None:
    """A path that does not exist gives 404 NOT_FOUND in the contract shape."""
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {"error": {"code": "NOT_FOUND", "message": "Not Found"}}


def test_invalid_body_is_reported_with_readable_details(client: TestClient) -> None:
    """A request body that breaks the contract gives 422 INVALID_REQUEST naming the field."""
    response = client.post("/api/models/M001/runs", json={"stages": ["discover", "approve_everything"]})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert "body.stages.1" in response.json()["error"]["message"]


def test_wrong_method_uses_the_error_body(client: TestClient) -> None:
    """Using the wrong HTTP method gives 405 METHOD_NOT_ALLOWED in the contract shape."""
    response = client.delete("/api/models")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"
