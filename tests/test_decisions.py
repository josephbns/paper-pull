"""Explicit reviewer merges preserve paper history and are safe to re-import."""

import csv

from test_pipeline import FIXTURES, records

from pubmon import export, pipeline
from pubmon.decisions import import_decisions
from pubmon.store import Store


def reviewed(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["work_key", "decision", "reviewer_note"])
        writer.writeheader()
        writer.writerows(rows)


def test_review_merge_is_atomic_and_reimport_is_idempotent(project, tmp_path):
    result = pipeline.run(project, no_master=True, fixtures=FIXTURES)
    rows = records(result["paths"]["candidates"])
    target = next(row["work_key"] for row in rows if row["doi"] == "10.5555/synthetic-1")
    source = next(row["work_key"] for row in rows if row["doi"] == "10.5555/synthetic-2")
    path = tmp_path / "review.csv"
    reviewed(
        path,
        [
            {
                "work_key": source,
                "decision": "merge:" + target,
                "reviewer_note": "Synthetic approval",
            }
        ],
    )
    database = project.project_dir / "demo/data/pubmon.db"
    with Store(database) as store:
        source_events = len(store.list_events(source))
        target_events = len(store.list_events(target))
        assert (
            import_decisions(path, store, decided_at="2026-11-12T18:00:00+00:00")["imported"] == 1
        )
        assert len(store.list_works()) == 2
        assert store.canonical_key(source) == target
        assert store.find_work_key({"doi": "10.5555/synthetic-2"}) == target
        assert len(store.list_events(target)) == source_events + target_events
        before = database.read_bytes()
        import_decisions(path, store, decided_at="2026-11-12T19:00:00+00:00")
        assert database.read_bytes() == before
        assert len(export.snapshot_rows(store, "snapshot", [], {})) == 2
    again = pipeline.run(project, no_master=True, fixtures=FIXTURES)
    assert again["papers"] == 2


def test_invalid_review_rows_do_not_change_history(project, tmp_path):
    result = pipeline.run(project, no_master=True, fixtures=FIXTURES)
    key = records(result["paths"]["candidates"])[0]["work_key"]
    path = tmp_path / "bad.csv"
    reviewed(
        path,
        [
            {"work_key": key, "decision": "merge:unknown", "reviewer_note": ""},
            {"work_key": key, "decision": "typo", "reviewer_note": ""},
        ],
    )
    database = project.project_dir / "demo/data/pubmon.db"
    with Store(database) as store:
        before = database.read_bytes()
        assert import_decisions(path, store, decided_at="2026-11-12T18:00:00+00:00")["invalid"] == 2
        assert database.read_bytes() == before


def test_pending_rejected_events_remain_suppressed_until_later_material_change(project):
    result = pipeline.run(project, no_master=True, fixtures=FIXTURES)
    key = records(result["paths"]["candidates"])[0]["work_key"]
    with Store(project.project_dir / "demo/data/pubmon.db") as store:
        run_id = result["run_id"]
        with store.transaction():
            store.add_event(run_id, key, "NEW", created_at="2026-01-01T00:00:00+00:00")
            store.store_decision(key, "rejected", decided_at="2026-02-01T00:00:00+00:00")
        assert export.candidate_rows(store, run_id, [], {})[0] == []
        with store.transaction():
            store.add_event(
                run_id,
                key,
                "UPDATED",
                field="venue",
                old="old",
                new="new",
                created_at="2026-03-01T00:00:00+00:00",
            )
        rows = export.candidate_rows(store, run_id, [], {})[0]
        assert len(rows) == 1 and rows[0]["events"] == "UPDATED"
