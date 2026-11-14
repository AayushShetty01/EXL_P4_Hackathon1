"""File endpoints: text files from the estate and artifacts, binary artifact streaming, blocked paths."""

from fastapi.testclient import TestClient

from app.api_schemas import FileView


def test_estate_file_is_returned_as_a_file_view(estate_client: TestClient) -> None:
    """A legacy code file comes back with path, language, line count and content."""
    response = estate_client.get(
        "/api/files", params={"path": "model_estate/M001_cc_pd_scorecard_sas/code/02_train.sas"}
    )
    assert response.status_code == 200
    view = FileView.model_validate(response.json())
    assert (view.language, view.lines) == ("sas", 4)


def test_answer_keys_are_blocked(estate_client: TestClient) -> None:
    """The evaluation answer keys can never be read through the API."""
    response = estate_client.get("/api/files", params={"path": "model_estate/_answer_keys/M001.json"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN_PATH"
    assert "secret" not in response.text


def test_parent_paths_are_blocked(estate_client: TestClient) -> None:
    """A path with .. is refused before it is resolved."""
    response = estate_client.get("/api/files", params={"path": "artifacts/../.env"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_PATH"


def test_binary_artifact_is_streamed(client: TestClient) -> None:
    """A chart under artifacts/ is streamed with its media type, with or without the artifacts/ prefix."""
    settings = client.app.state.settings
    chart = settings.artifacts_dir / "M001" / "validation" / "charts" / "roc_oot.png"
    chart.parent.mkdir(parents=True)
    chart.write_bytes(b"\x89PNG\r\n\x1a\nchart")
    for path in ("M001/validation/charts/roc_oot.png", "artifacts/M001/validation/charts/roc_oot.png"):
        response = client.get(f"/api/artifacts/{path}")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert response.content == b"\x89PNG\r\n\x1a\nchart"


def test_missing_artifact_is_404(client: TestClient) -> None:
    """An artifact that does not exist gives FILE_NOT_FOUND."""
    response = client.get("/api/artifacts/M001/validation/charts/missing.png")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "FILE_NOT_FOUND"
