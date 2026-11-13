"""Named QIC profiles: strict checks, the generated arXiv search and the CLI rules."""

import json
import re
import shutil
import tomllib
from pathlib import Path

import pytest

from pubmon import cli
from pubmon.profile import available_profiles, check_keys, load_profile, read_people

ROOT = Path(__file__).resolve().parents[1]
PROFILE = "cleveland-clinic"


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """A synthetic checkout with the shipped profiles and no private .env values."""
    shutil.copytree(ROOT / "profiles", tmp_path / "profiles")
    for name in ("OPENALEX_API_KEY", "PUBMON_EMAIL", "PUBMON_MASTER", "PUBMON_PROFILE"):
        monkeypatch.delenv(name, raising=False)
    return tmp_path


def _clauses(query: str) -> set[str]:
    # Compare clause by clause, ignoring quote style: all:ibm_cleveland == all:"ibm_cleveland".
    return {item.replace('"', "") for item in re.findall(r'\w+:(?:"[^"]+"|[\w-]+)', query)}


def _write(workspace: Path, text: str) -> None:
    (workspace / "profiles/test.toml").write_text(text, encoding="utf-8")


def test_profile_search_keeps_every_clause_of_the_proven_query(workspace):
    settings = load_profile(workspace, PROFILE)
    old = _clauses((ROOT / "config/arxiv_query.txt").read_text())
    new = _clauses(settings.read_arxiv_query())
    assert old <= new
    # The only deliberate additions: Ruihao Li, who was missing from the old feed.
    assert new - old == {"au:Ruihao Li", "au:Rui-Hao Li"}


def test_ibm_people_confirm_papers_but_never_search(workspace):
    settings = load_profile(workspace, PROFILE)
    ibm = {author.arxiv_name for author in settings.watchlist if author.side == "IBM"}
    assert {"Mario Motta", "Thaddeus Pellegrini", "Joseph A. Morrone"} <= ibm
    assert not any(f'au:"{name}"' in settings.read_arxiv_query() for name in ibm)


def test_backup_people_and_topic_settings(workspace):
    settings = load_profile(workspace, PROFILE)
    assert settings.backup_names == ("Sergii Strelchuk",)
    assert "quantum computing" in settings.tag_terms and "quantum" not in settings.tag_terms
    assert settings.topic_categories == ("quant-ph",) and settings.broad_terms == ("quantum",)
    assert "ibm_cleveland" in settings.hardware_terms
    assert settings.profile_name == PROFILE and settings.partner_label == "CCF"


def test_typo_stops_with_the_section_and_allowed_keys(workspace):
    text = (workspace / f"profiles/{PROFILE}.toml").read_text(encoding="utf-8")
    _write(workspace, text.replace("workspace = ", "workspce = ", 1))
    with pytest.raises(ValueError, match=r"Unknown key\(s\) \['workspce'\] in \[qic\]"):
        load_profile(workspace, "test")


def test_master_path_is_never_part_of_a_shared_profile(workspace, monkeypatch):
    text = (workspace / f"profiles/{PROFILE}.toml").read_text(encoding="utf-8")
    _write(workspace, text + '\n[master]\npath = "private.xlsx"\n')
    with pytest.raises(ValueError, match="Unknown key"):
        load_profile(workspace, "test")
    assert load_profile(workspace, PROFILE).master_path is None
    monkeypatch.setenv("PUBMON_MASTER", "private/master.xlsx")
    assert load_profile(workspace, PROFILE).master_path == workspace / "private/master.xlsx"


def test_bad_person_is_named_in_the_error(workspace):
    text = (workspace / f"profiles/{PROFILE}.toml").read_text(encoding="utf-8")
    _write(
        workspace,
        text.replace('name = "Jun Qin"\nside = "partner"', 'name = "Jun Qin"\nside = "x"'),
    )
    with pytest.raises(ValueError, match=r"Jun Qin.*side must be 'ibm' or 'partner'"):
        load_profile(workspace, "test")


def test_missing_profile_lists_the_available_ones(workspace):
    with pytest.raises(ValueError, match="Available: cleveland-clinic"):
        load_profile(workspace, "no-such-qic")
    assert available_profiles(workspace) == [PROFILE]


def test_template_uses_only_allowed_keys():
    raw = tomllib.loads((ROOT / "profiles/TEMPLATE.toml.example").read_text(encoding="utf-8"))
    check_keys(raw)
    assert {person.side for person in read_people(raw["people"])} == {"ibm", "partner"}


def test_cli_requires_a_profile_instead_of_guessing(workspace, caplog):
    assert cli.main(["--project-dir", str(workspace), "status"]) == 1
    assert "Choose a profile with --profile" in caplog.text and PROFILE in caplog.text


def test_profile_can_follow_the_command_or_come_from_the_environment(
    workspace, monkeypatch, capsys
):
    assert cli.main(["--project-dir", str(workspace), "check-profile", "--profile", PROFILE]) == 0
    capsys.readouterr()
    monkeypatch.setenv("PUBMON_PROFILE", PROFILE)
    assert cli.main(["--project-dir", str(workspace), "check-profile"]) == 0
    assert json.loads(capsys.readouterr().out)["profile"] == PROFILE


def test_check_profile_reports_without_calling_apis_or_showing_secrets(workspace, capsys):
    (workspace / ".env").write_text("OPENALEX_API_KEY=synthetic-secret\n")
    assert cli.main(["--project-dir", str(workspace), "--profile", PROFILE, "check-profile"]) == 0
    output = capsys.readouterr().out
    summary = json.loads(output)
    assert summary["api_key_set"] is True and summary["contact_email_set"] is False
    assert summary["ibm_people"] == 32 and summary["backup_tab_people"] == ["Sergii Strelchuk"]
    assert "synthetic-secret" not in output and summary["arxiv_query"].startswith("( au:")
