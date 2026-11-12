"""Settings behavior without API access or real credentials."""

import shutil
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from pubmon.config import load_config

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    for name in ("settings.example.toml", "arxiv_query.txt"):
        shutil.copyfile(ROOT / "config" / name, tmp_path / "config" / name)
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    monkeypatch.delenv("PUBMON_EMAIL", raising=False)
    return tmp_path


def test_example_fallback_and_immutable_settings(project):
    settings = load_config(project)
    assert settings.start_date == "2021-01-01"
    assert settings.ibm_institution_ids == ("I1341412227",)
    assert settings.cc_institution_ids == ("I1316902750",)
    assert settings.auto_link == 95 and settings.review == 85
    assert settings.year_window == (-1, 3)
    assert settings.master_path is None
    with pytest.raises(FrozenInstanceError):
        settings.start_date = "2022-01-01"
    with pytest.raises(TypeError):
        settings.ibm_institution_ids[0] = "I0"


def test_credentials_required_only_for_network(project):
    settings = load_config(project)
    with pytest.raises(ValueError, match="OPENALEX_API_KEY, PUBMON_EMAIL"):
        settings.require_network_credentials()


def test_dotenv_process_precedence_and_no_secret_repr(project, monkeypatch):
    (project / ".env").write_text(
        "OPENALEX_API_KEY=synthetic-file-key\nPUBMON_EMAIL=fake@example.invalid\n"
    )
    monkeypatch.setenv("OPENALEX_API_KEY", "synthetic-process-key")
    settings = load_config(project)
    assert settings.openalex_api_key == "synthetic-process-key"
    assert settings.email == "fake@example.invalid"
    assert "synthetic-process-key" not in repr(settings)
    assert "fake@example.invalid" not in repr(settings)
    settings.require_network_credentials()


def test_local_settings_override_and_relative_paths(project, monkeypatch):
    local = project / "config/settings.toml"
    local.write_text(
        (project / "config/settings.example.toml")
        .read_text()
        .replace('start_date = "2021-01-01"', 'start_date = "2022-01-01"')
    )
    monkeypatch.chdir(project.parent)
    settings = load_config(project)
    assert settings.start_date == "2022-01-01"
    assert settings.query_file == project / "config/arxiv_query.txt"
    assert settings.read_arxiv_query() == (project / "config/arxiv_query.txt").read_text()


@pytest.mark.parametrize(
    "before,after",
    [
        ('"2021-01-01"', '"bad-date"'),
        ("arxiv_window_days = 90", "arxiv_window_days = -1"),
        ("auto_link = 95", "auto_link = 101"),
        ("review = 85", "review = 99"),
        ("year_window = [-1, 3]", "year_window = [3, -1]"),
        ("common_names = []", 'common_names = "wrong"'),
    ],
)
def test_bad_configuration_is_actionable(project, before, after):
    config = project / "config/settings.example.toml"
    config.write_text(config.read_text().replace(before, after))
    with pytest.raises(ValueError, match="Invalid settings"):
        load_config(project)


def test_explicit_missing_file_does_not_fall_back(project):
    with pytest.raises(FileNotFoundError):
        load_config(project, path="missing.toml")
