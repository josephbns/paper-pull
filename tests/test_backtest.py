"""Offline recall checks use synthetic master rows and never modify either input."""

import csv
import hashlib
import json
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from pubmon import cli
from pubmon.backtest import compare, run_backtest
from pubmon.master import MasterRow, read_master
from pubmon.store import Store

MASTER = Path(__file__).parent / "fixtures/synthetic_master.xlsx"
STAMP = "2026-11-12T18:00:00Z"


def seed(store, key, identifiers=(), *, published="2025-01-01", authors=()):
    state = {
        "title": "Synthetic paper",
        "pub_date": published,
        "authors": [{"name": name} for name in authors],
    }
    store.upsert_work(
        key,
        title=state["title"],
        year=int(published[:4]),
        venue=None,
        type="article",
        status="published",
        ibm_confirmed=False,
        best_confidence="review",
        first_seen=STAMP,
        last_changed=STAMP,
    )
    for scheme, value in identifiers:
        store.upsert_identifier(scheme, value, key)
    store.save_work_state(key, state)


@pytest.fixture
def history(tmp_path):
    database = tmp_path / "history.db"
    with Store(database) as store, store.transaction():
        seed(store, "pair", [("doi", "10.5555/syn.2025.0001"), ("arxiv", "2501.99901")])
        seed(store, "authors", published="2025-08-21", authors=["Ben Example", "Cara Testcase"])
        seed(store, "hyperlink", [("arxiv", "2502.99905")])
        seed(store, "clinic", [("pmid", "99000011")])
    return database


def load_rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def test_backtest_reports_known_rows_misses_and_exclusions(history, tmp_path):
    result = run_backtest(history, MASTER, tmp_path / "out")
    assert result["eligible_rows"] == 9
    assert result["found_rows"] == 5 and result["missed_rows"] == 4
    assert result["recall"] == pytest.approx(5 / 9)
    assert result["excluded_rows"] == 2
    rows = {row["pub_id"]: row for row in load_rows(result["path"])}
    assert rows["SYN-0001"]["work_keys"] == rows["SYN-0002"]["work_keys"] == "pair"
    assert rows["SYN-0004"]["match_method"] == "authors+date"
    assert rows["SYN-0005"]["found"] == "True"
    assert rows["SYN-0006"]["reason"] == "excluded_type"
    assert rows["SYN-0007"]["reason"] == "excluded_status"
    assert {item["pub_id"] for item in result["misses"]} == {
        "SYN-0003",
        "SYN-0008",
        "SYN-0009",
        "SYN-0010",
    }
    assert all(item["name"] for item in result["misses"])
    assert "POISON-DO-NOT-READ" not in Path(result["path"]).read_text(encoding="utf-8-sig")


def test_backtest_inputs_unchanged_and_reports_not_overwritten(history, tmp_path):
    master_before = hashlib.sha256(MASTER.read_bytes()).hexdigest()
    database_before = history.read_bytes()
    first = run_backtest(history, MASTER, tmp_path / "out")
    original = Path(first["path"]).read_bytes()
    second = run_backtest(history, MASTER, tmp_path / "out")
    assert first["path"] != second["path"]
    assert Path(first["path"]).read_bytes() == original
    assert history.read_bytes() == database_before
    assert hashlib.sha256(MASTER.read_bytes()).hexdigest() == master_before


def test_backtest_since_cutoff_is_inclusive(history, tmp_path):
    result = run_backtest(history, MASTER, tmp_path / "out", since="2025-06-02")
    assert result["eligible_rows"] == result["found_rows"] == 3
    assert result["recall"] == 1.0


def test_backtest_ambiguous_history_is_not_counted_as_found(history, tmp_path):
    with Store(history) as store, store.transaction():
        seed(store, "conflicting")
        store.save_work_state("conflicting", {"doi": "10.5555/syn.2025.0001"})
    result = run_backtest(history, MASTER, tmp_path / "out")
    assert result["ambiguous_rows"] == 1 and result["found_rows"] == 4
    row = next(row for row in load_rows(result["path"]) if row["pub_id"] == "SYN-0001")
    assert row["found"] == "False" and row["reason"] == "ambiguous"
    assert row["work_keys"] == "conflicting; pair"


def test_empty_eligible_scope_does_not_claim_perfect_recall(history, tmp_path):
    result = run_backtest(history, MASTER, tmp_path / "out", since="2099-01-01")
    assert result["eligible_rows"] == 0 and result["recall"] is None
    assert result["misses"] == []


def test_empty_existing_history_reports_zero_recall(tmp_path):
    path = tmp_path / "empty.db"
    with Store(path):
        pass
    result = run_backtest(path, MASTER, tmp_path / "out")
    assert result["recall"] == 0.0 and result["missed_rows"] == 9


def test_missing_date_is_excluded_and_accepted_reviews_are_eligible(history):
    source = read_master(MASTER)[0]
    missing = MasterRow("missing-date", {**source.values, "Date of Publication": None})
    accepted = MasterRow(
        "accepted-review",
        {**source.values, "Type of Paper": "Review Paper", "Pub Status": "Accepted"},
    )
    with Store(history, read_only=True) as store:
        rows, result = compare(store, [missing, accepted], since=date(2023, 1, 1))
    assert rows[0]["reason"] == "missing_date"
    assert result["eligible_rows"] == result["found_rows"] == 1


def test_readonly_history_rejects_writes(history):
    with (
        Store(history, read_only=True) as store,
        pytest.raises(RuntimeError, match="read-only"),
        store.transaction(),
    ):
        pass


def test_backtest_missing_history_and_bad_date_leave_no_outputs(tmp_path):
    with pytest.raises(ValueError, match="run backfill"):
        run_backtest(tmp_path / "missing.db", MASTER, tmp_path / "out")
    assert not (tmp_path / "missing.db").exists() and not (tmp_path / "out").exists()
    with pytest.raises(ValueError):
        run_backtest(tmp_path / "missing.db", MASTER, tmp_path / "out", since="not-a-date")


def test_backtest_reads_legacy_history_without_migrating(tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE works (work_key TEXT PRIMARY KEY, title TEXT)")
        connection.execute("CREATE TABLE identifiers (scheme TEXT, value TEXT, work_key TEXT)")
        connection.execute("INSERT INTO works VALUES ('legacy', 'Synthetic paper')")
        connection.execute(
            "INSERT INTO identifiers VALUES ('doi', '10.5555/syn.2025.0001', 'legacy')"
        )
    before = path.read_bytes()
    result = run_backtest(path, MASTER, tmp_path / "out")
    assert result["found_rows"] == 1
    assert path.read_bytes() == before


def test_backtest_cli_uses_demo_history_without_credentials(project, history, capsys, monkeypatch):
    import shutil

    destination = project.project_dir / "demo/data/pubmon.db"
    destination.parent.mkdir(parents=True)
    shutil.copyfile(history, destination)
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    monkeypatch.delenv("PUBMON_EMAIL", raising=False)
    prefix = [
        "--project-dir",
        str(project.project_dir),
        "--profile",
        "cleveland-clinic",
        "backtest",
        "--master",
        str(MASTER),
    ]
    assert cli.main(prefix + ["--demo", "--since", "2023-01-01"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["found_rows"] == 5 and Path(result["path"]).is_file()
    assert cli.main(prefix) == 1
    assert not (project.project_dir / "data").exists()
