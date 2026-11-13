"""Command behavior is tested offline through the adapter boundary."""

from pubmon import cli
from pubmon.sources.common import LaneFailed

PROFILE_ARGS = ["--profile", "cleveland-clinic"]


def test_resolve_institutions_prints_candidates_without_changing_config(
    source_settings,
    monkeypatch,
    capsys,
):
    calls = []

    def lookup(settings, names):
        calls.append(names)
        return [
            {
                "id": "https://openalex.org/I999",
                "display_name": "Synthetic Institution",
                "ror": "https://ror.org/synthetic",
                "country_code": "US",
                "works_count": 12,
                "lineage": ["https://openalex.org/I999"],
            }
        ]

    monkeypatch.setattr(cli, "lookup_institutions", lookup)
    path = source_settings.project_dir / "config/settings.example.toml"
    before = path.read_bytes()
    assert (
        cli.main(
            [
                "--project-dir",
                str(source_settings.project_dir),
                "--profile",
                "cleveland-clinic",
                "resolve-institutions",
                "Cleveland Clinic",
                "IBM",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "Synthetic Institution" in output and "ROR" in output and "lineage" in output
    assert calls == [["Cleveland Clinic", "IBM"]]
    assert path.read_bytes() == before


def test_resolve_institutions_failure_returns_nonzero(source_settings, monkeypatch, caplog):
    def fail(*args):
        raise LaneFailed("institutions", "HTTP 503")

    monkeypatch.setattr(cli, "lookup_institutions", fail)
    assert (
        cli.main(
            [
                *PROFILE_ARGS,
                "--project-dir",
                str(source_settings.project_dir),
                "resolve-institutions",
                "IBM",
            ]
        )
        == 1
    )
    assert "run_id=" in caplog.text and "HTTP 503" in caplog.text


def test_help_lists_only_available_commands(capsys):
    assert cli.main([]) == 0
    assert "resolve-institutions" in capsys.readouterr().out


def test_missing_openalex_credentials_fail_without_fetch(monkeypatch, caplog, tmp_path):
    import shutil
    from pathlib import Path

    (tmp_path / "config").mkdir()
    source = Path(__file__).resolve().parents[1] / "config/settings.example.toml"
    shutil.copyfile(source, tmp_path / "config/settings.example.toml")
    shutil.copytree(source.parents[1] / "profiles", tmp_path / "profiles")
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    monkeypatch.delenv("PUBMON_EMAIL", raising=False)
    assert (
        cli.main([*PROFILE_ARGS, "--project-dir", str(tmp_path), "resolve-institutions", "IBM"])
        == 1
    )
    assert "Missing environment variables" in caplog.text


def test_institution_lookup_defaults_to_profile_names(source_settings, monkeypatch):
    calls = []

    def lookup(settings, names):
        calls.append(names)
        return []

    monkeypatch.setattr(cli, "lookup_institutions", lookup)
    assert (
        cli.main(
            [
                *PROFILE_ARGS,
                "--project-dir",
                str(source_settings.project_dir),
                "resolve-institutions",
            ]
        )
        == 0
    )
    assert calls == [[source_settings.partner_name, source_settings.ibm_name]]
