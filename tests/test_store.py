"""File-backed, offline tests for atomic history updates and identity constraints."""

import json
import sqlite3
from pathlib import Path

import pytest

from pubmon.models import Confidence, EventKind, Lane, Source, WorkStatus, WorkType
from pubmon.store import IdentifierConflict, Store

STAMP = "2026-11-12T18:00:00Z"
LATER = "2026-11-12T19:00:00Z"


def add_work(store: Store, key: str = "paper-1", **changes) -> None:
    values = {
        "title": "Synthetic paper",
        "year": 2024,
        "venue": None,
        "type": WorkType.PREPRINT,
        "status": WorkStatus.PREPRINT,
        "ibm_confirmed": False,
        "best_confidence": Confidence.REVIEW,
        "first_seen": STAMP,
        "last_changed": STAMP,
    }
    values.update(changes)
    store.upsert_work(key, **values)


def add_run(store: Store, run_id: str = "run-1") -> None:
    store.record_run(run_id, started_at=STAMP, finished_at=None, status="running", counts={})


@pytest.fixture
def store(tmp_path: Path):
    with Store(tmp_path / "state/history.db") as instance:
        yield instance


def test_schema_reopen_preserves_rows(tmp_path):
    path = tmp_path / "history.db"
    with Store(path) as history, history.transaction():
        add_work(history)
        history.upsert_identifier("doi", "10.5555/synthetic", "paper-1")
    before = path.read_bytes()
    with Store(path) as history:
        assert history.find_work_key({"doi": "10.5555/synthetic"}) == "paper-1"
        assert history.get_work("paper-1")["title"] == "Synthetic paper"
    assert path.read_bytes() == before
    with sqlite3.connect(path) as conn:
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert tables == {"works", "identifiers", "source_records", "events", "decisions", "runs"}


def test_interrupted_run_safe(tmp_path):
    path = tmp_path / "history.db"
    with Store(path) as history:
        with history.transaction():
            add_work(history)
            add_run(history)
        before = path.read_bytes()
        with pytest.raises(RuntimeError, match="interrupted"), history.transaction():
            add_work(history, title="Uncommitted edit")
            history.upsert_identifier("doi", "10.5555/synthetic", "paper-1")
            history.upsert_source_record(
                Source.ARXIV,
                "2401.99999",
                "paper-1",
                lane=Lane.ARXIV_FEED,
                fetched_at=STAMP,
                raw={"title": "synthetic"},
                raw_hash="hash",
            )
            history.add_event("run-1", "paper-1", EventKind.NEW, created_at=STAMP)
            history.store_decision("paper-1", "rejected", decided_at=STAMP)
            history.record_run(
                "run-1", started_at=STAMP, finished_at=LATER, status="completed", counts={"new": 1}
            )
            raise RuntimeError("interrupted")
        assert path.read_bytes() == before
        assert history.get_work("paper-1")["title"] == "Synthetic paper"
        assert history.get_identifiers("paper-1") == []
        assert history.list_source_records("paper-1") == []
        assert history.list_unexported_events() == []
        assert history.get_decision("paper-1") is None
        assert history.list_runs()[0]["status"] == "running"
        # The same connection remains usable after rollback.
        with history.transaction():
            history.upsert_identifier("doi", "10.5555/after", "paper-1")
    with Store(path) as reopened:
        assert reopened.find_work_key({"doi": "10.5555/after"}) == "paper-1"


def test_duplicate_identifier_keeps_one_row(store):
    with store.transaction():
        add_work(store)
        for _ in range(2):
            store.upsert_identifier("doi", "10.5555/synthetic", "paper-1")
    assert len(store.get_identifiers("paper-1")) == 1
    assert store.find_work_key({"doi": None, "arxiv": "2401.99999"}) is None


def test_identifier_conflict_never_reassigns(store):
    with store.transaction():
        add_work(store)
        add_work(store, "paper-2")
        store.upsert_identifier("doi", "10.5555/synthetic", "paper-1")
    with pytest.raises(IdentifierConflict) as error, store.transaction():
        store.upsert_identifier("doi", "10.5555/synthetic", "paper-2")
    assert error.value.work_keys == ("paper-1", "paper-2")
    assert store.find_work_key({"doi": "10.5555/synthetic"}) == "paper-1"


def test_multiple_identifiers_resolve_or_report_conflict(store):
    with store.transaction():
        add_work(store)
        add_work(store, "paper-2")
        store.upsert_identifier("doi", "10.5555/synthetic", "paper-1")
        store.upsert_identifier("arxiv", "2401.99999", "paper-2")
    assert store.find_work_key({"pmid": None, "doi": "10.5555/synthetic"}) == "paper-1"
    with pytest.raises(IdentifierConflict):
        store.find_work_key({"doi": "10.5555/synthetic", "arxiv": "2401.99999"})


@pytest.mark.parametrize("scheme,value", [("invalid", "1"), ("doi", ""), ("pmid", 123)])
def test_invalid_identifier_rejected(store, scheme, value):
    with pytest.raises(ValueError), store.transaction():
        store.upsert_identifier(scheme, value, "paper-1")


def test_foreign_keys_prevent_orphan_records(store):
    with pytest.raises(sqlite3.IntegrityError), store.transaction():
        store.upsert_identifier("doi", "10.5555/orphan", "missing")
    assert store.find_work_key({"doi": "10.5555/orphan"}) is None


def test_writes_require_explicit_transaction(store):
    with pytest.raises(RuntimeError, match="Writes require"):
        add_work(store)
    assert store.list_works() == []


def test_nested_transaction_rolls_back_outer(store):
    with pytest.raises(RuntimeError, match="Nested transactions"), store.transaction():
        add_work(store)
        with store.transaction():
            pass
    assert store.list_works() == []


def test_base_exception_also_rolls_back(store):
    with pytest.raises(KeyboardInterrupt), store.transaction():
        add_work(store)
        raise KeyboardInterrupt
    assert store.list_works() == []


def test_work_update_keeps_first_seen(store):
    with store.transaction():
        add_work(store)
        add_work(
            store,
            title="Journal paper",
            status=WorkStatus.PUBLISHED,
            type=WorkType.ARTICLE,
            first_seen=LATER,
            last_changed=LATER,
        )
    work = store.get_work("paper-1")
    assert work["first_seen"] == STAMP
    assert work["last_changed"] == LATER
    assert work["status"] == "published"
    assert len(store.list_works()) == 1
    assert store.get_work("unknown") is None


def test_source_record_upsert_keeps_latest_response(store):
    with store.transaction():
        add_work(store)
        for stamp, title in [(STAMP, "original"), (LATER, "updated")]:
            store.upsert_source_record(
                Source.ARXIV,
                "2401.99999",
                "paper-1",
                lane=Lane.RECHECK,
                fetched_at=stamp,
                raw={"title": title},
                raw_hash=title,
            )
    records = store.list_source_records("paper-1")
    assert len(records) == 1
    assert json.loads(records[0]["raw_json"]) == {"title": "updated"}
    assert records[0]["raw_hash"] == "updated"
    assert records[0]["fetched_at"] == LATER


def test_events_marked_exported_stay_out_of_queue(store):
    with store.transaction():
        add_work(store)
        add_run(store)
        new = store.add_event("run-1", "paper-1", EventKind.NEW, created_at=STAMP)
        update = store.add_event(
            "run-1",
            "paper-1",
            EventKind.UPDATED,
            field="title",
            old="old title",
            new="new title",
            created_at=LATER,
        )
    assert [row["event_id"] for row in store.list_unexported_events()] == [new, update]
    with store.transaction():
        store.mark_events_exported([new], "run-1")
    remaining = store.list_unexported_events()
    assert [row["event_id"] for row in remaining] == [update]
    assert remaining[0]["old"] == "old title"
    with pytest.raises(RuntimeError), store.transaction():
        store.mark_events_exported([update], "run-1")
        raise RuntimeError
    assert len(store.list_unexported_events()) == 1
    with store.transaction():
        store.mark_events_exported([new, update], "run-1")
    assert store.list_unexported_events() == []


def test_runs_update_and_recent_limit(store):
    with store.transaction():
        for number in range(12):
            add_run(store, f"run-{number:02}")
        store.record_run(
            "run-11",
            started_at=LATER,
            finished_at=LATER,
            status="partial",
            counts={"pair": {"status": "failed"}},
        )
    runs = store.list_runs()
    assert len(runs) == 10
    assert runs[0]["run_id"] == "run-11"
    assert runs[0]["started_at"] == STAMP
    assert runs[0]["finished_at"] == LATER
    assert json.loads(runs[0]["counts_json"]) == {"pair": {"status": "failed"}}
    assert len(store.list_runs(limit=20)) == 12
    with pytest.raises(ValueError):
        store.list_runs(limit=-1)


def test_decisions_latest_and_idempotent_reimport(tmp_path):
    path = tmp_path / "history.db"
    with Store(path) as history:
        with history.transaction():
            add_work(history)
            history.store_decision("paper-1", "rejected", decided_at=STAMP, note="synthetic")
        before = path.read_bytes()
        with history.transaction():
            history.store_decision("paper-1", "rejected", decided_at=LATER, note="synthetic")
        assert path.read_bytes() == before
        assert history.get_decision("paper-1")["decided_at"] == STAMP
        with history.transaction():
            history.store_decision("paper-1", "accepted", decided_at=LATER)
        assert history.get_decision("paper-1")["decision"] == "accepted"
        assert history.get_decision("unknown") is None


@pytest.mark.parametrize("decision", ["typo", "merge:", "merge:paper-1", "merge:unknown"])
def test_invalid_decision_does_not_change_history(store, decision):
    with store.transaction():
        add_work(store)
    with pytest.raises(ValueError), store.transaction():
        store.store_decision("paper-1", decision, decided_at=STAMP)
    assert store.get_decision("paper-1") is None


def test_merge_decision_records_intent_without_implicit_merging(store):
    with store.transaction():
        add_work(store)
        add_work(store, "paper-2")
        store.store_decision("paper-1", "merge:paper-2", decided_at=STAMP)
    assert store.get_decision("paper-1")["decision"] == "merge:paper-2"
    assert len(store.list_works()) == 2  # Applying approved merges belongs to milestone 5.


def test_sql_values_are_bound_parameters(store):
    strange_title = "A title'; DROP TABLE works; --"
    with store.transaction():
        add_work(store, title=strange_title)
        store.store_decision("paper-1", "not_collab", decided_at=STAMP, note="O'Brien")
    assert store.get_work("paper-1")["title"] == strange_title
    assert store.get_decision("paper-1")["note"] == "O'Brien"


def test_source_identity_cannot_silently_move_between_papers(store):
    with store.transaction():
        add_work(store)
        add_work(store, "paper-2")
        store.upsert_source_record(
            Source.ARXIV,
            "2401.99999",
            "paper-1",
            lane=Lane.ARXIV_FEED,
            fetched_at=STAMP,
            raw={"title": "original"},
            raw_hash="hash",
        )
    with pytest.raises(IdentifierConflict), store.transaction():
        store.upsert_source_record(
            Source.ARXIV,
            "2401.99999",
            "paper-2",
            lane=Lane.RECHECK,
            fetched_at=LATER,
            raw={"title": "changed"},
            raw_hash="new",
        )
    assert len(store.list_source_records("paper-1")) == 1
    assert store.list_source_records("paper-2") == []


def test_legacy_database_migrates_without_losing_history(tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.execute("""CREATE TABLE works (
            work_key TEXT PRIMARY KEY NOT NULL, title TEXT, year INT, venue TEXT, type TEXT,
            status TEXT, ibm_confirmed INT, best_confidence TEXT, first_seen TEXT, last_changed TEXT)
        """)
        connection.execute("""CREATE TABLE source_records (
            source TEXT NOT NULL, source_id TEXT NOT NULL, work_key TEXT NOT NULL,
            lane TEXT, fetched_at TEXT, raw_json TEXT, raw_hash TEXT,
            PRIMARY KEY(source, source_id))""")
        connection.execute(
            "INSERT INTO works VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "legacy",
                "Synthetic legacy paper",
                2024,
                None,
                "preprint",
                "preprint",
                0,
                "review",
                STAMP,
                STAMP,
            ),
        )
        connection.execute(
            "INSERT INTO source_records VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("openalex", "W9991", "legacy", "pair", STAMP, '{"synthetic":true}', "old-hash"),
        )
    with Store(path) as history:
        assert history.get_work("legacy")["title"] == "Synthetic legacy paper"
        assert history.get_work_state("legacy") is None
        record = history.get_source_record(Source.OPENALEX, "W9991")
        assert record["raw_hash"] == "old-hash" and record["normalized_json"] is None
        with history.transaction():
            history.save_work_state("legacy", {"title": "Synthetic canonical state"})
        assert history.get_work_state("legacy") == {"title": "Synthetic canonical state"}
    with Store(path) as history:
        assert len(history.list_works()) == 1
        assert history.get_work_state("legacy") is not None
