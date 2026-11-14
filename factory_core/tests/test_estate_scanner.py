"""Estate scanning, registration and the safe file reader."""

import json

import pytest
from sqlmodel import Session

from app.config import Settings
from app.database import ModelRow
from app.estate_scanner import (
    MAX_TEXT_FILE_BYTES,
    EstateScanError,
    FileAccessError,
    read_register,
    read_text_file,
    register_estate,
    resolve_artifact_path,
    scan_estate,
)


def test_scan_finds_the_model_folder_with_register_row(hero_estate: Settings) -> None:
    """The M001 folder is found with its register row and hashed source files."""
    [model] = scan_estate(hero_estate)
    assert model.model_id == "M001"
    assert model.folder == "model_estate/M001_cc_pd_scorecard_sas"
    assert model.register_row.model_owner == "Head of Cards Credit Risk"
    assert model.register_row.exposure_gbp_m == 1850
    assert model.register_row.customer_facing is True
    assert [source.kind for source in model.source_files] == ["code", "code", "code", "doc"]
    assert model.source_files[0].path == "model_estate/M001_cc_pd_scorecard_sas/code/01_prepare.sas"
    assert model.source_files[0].lines == 7
    assert len(model.source_files[0].sha256) == 64


def test_scan_skips_special_folders_and_folders_without_manifest(hero_estate: Settings) -> None:
    """_answer_keys, _tools and folders without manifest.json are not models."""
    (hero_estate.estate_dir / "_tools").mkdir()
    (hero_estate.estate_dir / "_tools" / "manifest.json").write_text("{}")
    (hero_estate.estate_dir / "notes").mkdir()
    assert [model.model_id for model in scan_estate(hero_estate)] == ["M001"]


def test_missing_estate_folder_means_no_models(settings: Settings) -> None:
    """An estate that does not exist yet is simply empty."""
    settings.estate_dir.rmdir()
    assert scan_estate(settings) == []


def test_invalid_manifest_json_is_reported(hero_estate: Settings) -> None:
    """A broken manifest stops the scan with INVALID_MANIFEST and names the folder."""
    (hero_estate.repository_root / "model_estate/M001_cc_pd_scorecard_sas/manifest.json").write_text("{not json")
    with pytest.raises(EstateScanError, match="M001_cc_pd_scorecard_sas") as raised:
        scan_estate(hero_estate)
    assert raised.value.code == "INVALID_MANIFEST"


def test_manifest_folder_must_match_its_location(hero_estate: Settings) -> None:
    """The folder field of a manifest must be the folder it sits in."""
    path = hero_estate.repository_root / "model_estate/M001_cc_pd_scorecard_sas/manifest.json"
    path.write_text(json.dumps(json.loads(path.read_text()) | {"folder": "model_estate/elsewhere"}))
    with pytest.raises(EstateScanError, match="expected"):
        scan_estate(hero_estate)


def test_listed_file_must_exist(hero_estate: Settings) -> None:
    """A code file named in the manifest but missing on disk is an error."""
    (hero_estate.repository_root / "model_estate/M001_cc_pd_scorecard_sas/code/03_score.sas").unlink()
    with pytest.raises(EstateScanError, match="03_score.sas"):
        scan_estate(hero_estate)


def test_register_needs_every_column(hero_estate: Settings) -> None:
    """A register without the contract columns is refused."""
    (hero_estate.estate_dir / "estate_register.csv").write_text("model_id,model_name\nM001,Scorecard\n")
    with pytest.raises(EstateScanError) as raised:
        read_register(hero_estate)
    assert raised.value.code == "INVALID_REGISTER"


def test_register_estate_uses_the_sample_only_when_nothing_is_registered(settings: Settings, session: Session) -> None:
    """An empty estate registers the sample, and reports that no estate models were found."""
    assert register_estate(session, settings) == []
    assert session.get(ModelRow, "M001").source == "sample"


def test_real_models_replace_the_sample(hero_estate: Settings, session: Session) -> None:
    """When the estate gains models, the sample is removed and the real M001 is registered."""
    hero_estate.estate_dir.joinpath("M001_cc_pd_scorecard_sas", "manifest.json").rename(
        hero_estate.estate_dir / "manifest.hidden"
    )
    register_estate(session, hero_estate)
    assert session.get(ModelRow, "M001").source == "sample"
    (hero_estate.estate_dir / "manifest.hidden").rename(
        hero_estate.estate_dir / "M001_cc_pd_scorecard_sas" / "manifest.json"
    )
    assert register_estate(session, hero_estate) == ["M001"]
    model = session.get(ModelRow, "M001")
    assert model.source == "estate"
    assert model.active_run_id is None
    assert model.registration["register_row"]["business_line"] == "Cards"


def test_read_text_file_returns_a_file_view(hero_estate: Settings) -> None:
    """An estate file is returned with language, line count and content."""
    view = read_text_file(hero_estate, "model_estate/M001_cc_pd_scorecard_sas/code/02_train.sas")
    assert view.path == "model_estate/M001_cc_pd_scorecard_sas/code/02_train.sas"
    assert view.language == "sas"
    assert view.lines == 4
    assert "proc logistic" in view.content


@pytest.mark.parametrize(
    ("path", "status", "code"),
    [
        ("model_estate/_answer_keys/M001.json", 403, "FORBIDDEN_PATH"),
        ("model_estate/_ANSWER_KEYS/M001.json", 403, "FORBIDDEN_PATH"),
        ("model_estate/../model_estate/estate_register.csv", 400, "INVALID_PATH"),
        ("/etc/passwd", 400, "INVALID_PATH"),
        ("", 400, "INVALID_PATH"),
        ("factory_core/app/config.py", 403, "FORBIDDEN_PATH"),
        ("model_estate/M001_cc_pd_scorecard_sas/code/missing.sas", 404, "FILE_NOT_FOUND"),
    ],
)
def test_read_text_file_refuses_unsafe_paths(hero_estate: Settings, path: str, status: int, code: str) -> None:
    """Answer keys, parent paths, absolute paths and files outside the two folders are refused."""
    with pytest.raises(FileAccessError) as raised:
        read_text_file(hero_estate, path)
    assert (raised.value.status_code, raised.value.code) == (status, code)


def test_symlink_into_answer_keys_is_refused(hero_estate: Settings) -> None:
    """A link that resolves into _answer_keys is blocked as well."""
    (hero_estate.estate_dir / "keys_link.json").symlink_to(hero_estate.estate_dir / "_answer_keys" / "M001.json")
    with pytest.raises(FileAccessError) as raised:
        read_text_file(hero_estate, "model_estate/keys_link.json")
    assert raised.value.code == "FORBIDDEN_PATH"


def test_text_files_are_capped_at_one_megabyte(hero_estate: Settings) -> None:
    """A file over 1 MB is refused with FILE_TOO_LARGE."""
    hero_estate.artifacts_dir.mkdir(parents=True, exist_ok=True)
    (hero_estate.artifacts_dir / "big.txt").write_text("x" * (MAX_TEXT_FILE_BYTES + 1))
    with pytest.raises(FileAccessError) as raised:
        read_text_file(hero_estate, "artifacts/big.txt")
    assert raised.value.code == "FILE_TOO_LARGE"


def test_binary_files_are_not_returned_as_text(hero_estate: Settings) -> None:
    """A file that is not UTF-8 text is refused with FILE_NOT_TEXT."""
    hero_estate.artifacts_dir.mkdir(parents=True, exist_ok=True)
    (hero_estate.artifacts_dir / "chart.png").write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe")
    with pytest.raises(FileAccessError) as raised:
        read_text_file(hero_estate, "artifacts/chart.png")
    assert raised.value.code == "FILE_NOT_TEXT"


def test_artifact_paths_work_with_or_without_the_artifacts_prefix(settings: Settings) -> None:
    """Both M001/x.png and artifacts/M001/x.png point at the same artifact."""
    target = settings.artifacts_dir / "M001" / "x.png"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"png")
    assert resolve_artifact_path(settings, "M001/x.png") == target.resolve()
    assert resolve_artifact_path(settings, "artifacts/M001/x.png") == target.resolve()
