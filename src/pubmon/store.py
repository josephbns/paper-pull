"""SQLite history; all writes require an explicit, atomic transaction."""

import json
import sqlite3
from collections.abc import Iterable, Iterator, Mapping
from contextlib import closing, contextmanager
from pathlib import Path
from types import TracebackType
from typing import Any, Self

from sqlite_utils import Database

from pubmon.models import Confidence, EventKind, Lane, Source, WorkStatus, WorkType

Row = dict[str, Any]
SCHEMES = frozenset({"doi", "arxiv", "pmid", "openalex"})

# Keep schema creation separate from data writes. IF NOT EXISTS never replaces history.
SCHEMA = (
    """CREATE TABLE IF NOT EXISTS work_aliases (
        alias TEXT PRIMARY KEY NOT NULL, work_key TEXT NOT NULL REFERENCES works(work_key))""",
    """CREATE TABLE IF NOT EXISTS works (
        work_key TEXT PRIMARY KEY NOT NULL, title TEXT, year INT, venue TEXT,
        type TEXT, status TEXT, ibm_confirmed INT, best_confidence TEXT,
        first_seen TEXT, last_changed TEXT, state_json TEXT)""",
    """CREATE TABLE IF NOT EXISTS identifiers (
        scheme TEXT NOT NULL, value TEXT NOT NULL,
        work_key TEXT NOT NULL REFERENCES works(work_key),
        PRIMARY KEY (scheme, value))""",
    """CREATE TABLE IF NOT EXISTS source_records (
        source TEXT NOT NULL, source_id TEXT NOT NULL,
        work_key TEXT NOT NULL REFERENCES works(work_key), lane TEXT,
        fetched_at TEXT, raw_json TEXT, raw_hash TEXT, normalized_json TEXT,
        PRIMARY KEY (source, source_id))""",
    """CREATE TABLE IF NOT EXISTS events (
        event_id INTEGER PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(run_id),
        work_key TEXT NOT NULL REFERENCES works(work_key), kind TEXT,
        field TEXT, old TEXT, new TEXT, created_at TEXT, exported_in_run TEXT NULL)""",
    """CREATE TABLE IF NOT EXISTS decisions (
        work_key TEXT NOT NULL REFERENCES works(work_key), decision TEXT,
        decided_at TEXT, note TEXT)""",
    """CREATE TABLE IF NOT EXISTS runs (
        run_id TEXT PRIMARY KEY NOT NULL, started_at TEXT, finished_at TEXT,
        status TEXT, counts_json TEXT)""",
)


class IdentifierConflict(ValueError):
    """An identifier or identifier set points to different paper identities."""

    def __init__(self, work_keys: Iterable[str]) -> None:
        self.work_keys = tuple(sorted(set(work_keys)))
        super().__init__("Identifiers refer to different works; human review is required")


class Store:
    """Persist public paper history and local review decisions in one SQLite file."""

    def __init__(self, path: Path | str = "data/pubmon.db") -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = Database(path)
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.execute("PRAGMA journal_mode = DELETE")
        self._db.execute("PRAGMA synchronous = FULL")
        with self.transaction():
            for statement in SCHEMA:
                self._db.execute(statement)
            self._migrate_snapshots()

    def _migrate_snapshots(self) -> None:
        # Additive migration keeps databases created before matching was implemented.
        for table, column in (("works", "state_json"), ("source_records", "normalized_json")):
            if column not in self._db[table].columns_dict:
                self._write(f'ALTER TABLE "{table}" ADD COLUMN "{column}" TEXT')

    def __enter__(self) -> Self:
        """Keep a connection open for a group of operations."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the connection, discarding any uncommitted changes."""
        self.close()

    def close(self) -> None:
        """Release the database connection without committing pending writes."""
        self._db.conn.close()

    @contextmanager
    def transaction(self) -> Iterator["Store"]:
        """Commit all enclosed writes together; roll back on any exception."""
        if self._db.conn.in_transaction:
            raise RuntimeError("Nested transactions are not supported")
        self._db.execute("BEGIN IMMEDIATE")
        try:
            yield self
            self._db.execute("COMMIT")
        except BaseException:
            if self._db.conn.in_transaction:
                self._db.execute("ROLLBACK")
            raise

    def _write(self, sql: str, parameters: tuple = ()) -> Any:
        if not self._db.conn.in_transaction:
            raise RuntimeError("Writes require 'with store.transaction():'")
        return self._db.execute(sql, parameters)

    def _rows(self, sql: str, parameters: tuple = ()) -> list[Row]:
        return list(self._db.query(sql, parameters))

    def upsert_work(
        self,
        work_key: str,
        *,
        title: str,
        year: int,
        venue: str | None,
        type: WorkType,
        status: WorkStatus,
        ibm_confirmed: bool,
        best_confidence: Confidence,
        first_seen: str,
        last_changed: str,
    ) -> None:
        """Create or update a paper summary while preserving its first-seen date."""
        self._write(
            """INSERT INTO works (work_key, title, year, venue, type, status, ibm_confirmed,
                best_confidence, first_seen, last_changed) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(work_key) DO UPDATE SET
            title=excluded.title, year=excluded.year, venue=excluded.venue,
            type=excluded.type, status=excluded.status,
            ibm_confirmed=excluded.ibm_confirmed, best_confidence=excluded.best_confidence,
            last_changed=excluded.last_changed""",
            (
                work_key,
                title,
                year,
                venue,
                WorkType(type),
                WorkStatus(status),
                int(ibm_confirmed),
                Confidence(best_confidence),
                first_seen,
                last_changed,
            ),
        )

    def get_work(self, work_key: str) -> Row | None:
        """Return a paper summary or None if the identity is unknown."""
        work_key = self.canonical_key(work_key)
        rows = self._rows("SELECT * FROM works WHERE work_key = ?", (work_key,))
        return rows[0] if rows else None

    def list_works(self) -> list[Row]:
        """Return all paper summaries in stable identity order."""
        return self._rows("SELECT * FROM works ORDER BY work_key")

    def find_work_key(self, identifiers: Mapping[str, str | None]) -> str | None:
        """Resolve known identifiers, raising rather than silently merging conflicts."""
        matches = set()
        for scheme, value in identifiers.items():
            self._validate_identifier(scheme, value)
            if value is not None:
                rows = self._rows(
                    "SELECT work_key FROM identifiers WHERE scheme = ? AND value = ?",
                    (scheme, value),
                )
                matches.update(row["work_key"] for row in rows)
        if len(matches) > 1:
            raise IdentifierConflict(matches)
        return next(iter(matches), None)

    @staticmethod
    def _validate_identifier(scheme: str, value: str | None) -> None:
        if scheme not in SCHEMES:
            raise ValueError("Unknown identifier scheme")
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError("Identifiers must be nonempty strings or None")

    def upsert_identifier(self, scheme: str, value: str, work_key: str) -> None:
        """Insert an identifier once; never transfer it to another paper implicitly."""
        self._validate_identifier(scheme, value)
        if value is None:
            raise ValueError("An identifier value is required")
        existing = self.find_work_key({scheme: value})
        if existing is not None and existing != work_key:
            raise IdentifierConflict((existing, work_key))
        self._write(
            "INSERT INTO identifiers VALUES (?, ?, ?) ON CONFLICT(scheme, value) DO NOTHING",
            (scheme, value, work_key),
        )

    def get_identifiers(self, work_key: str) -> list[Row]:
        """Return all identifiers attached to one paper."""
        return self._rows(
            "SELECT * FROM identifiers WHERE work_key = ? ORDER BY scheme, value", (work_key,)
        )

    def upsert_source_record(
        self,
        source: Source,
        source_id: str,
        work_key: str,
        *,
        lane: Lane,
        fetched_at: str,
        raw: Row,
        raw_hash: str,
        normalized: Row | None = None,
    ) -> None:
        """Retain the latest raw response for a provider's source identity."""
        existing = self._rows(
            "SELECT work_key FROM source_records WHERE source = ? AND source_id = ?",
            (Source(source), source_id),
        )
        if existing and existing[0]["work_key"] != work_key:
            raise IdentifierConflict((existing[0]["work_key"], work_key))
        self._write(
            """INSERT INTO source_records (source, source_id, work_key, lane, fetched_at,
                raw_json, raw_hash, normalized_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source, source_id) DO UPDATE SET
            work_key=excluded.work_key, lane=excluded.lane, fetched_at=excluded.fetched_at,
            raw_json=excluded.raw_json, raw_hash=excluded.raw_hash,
            normalized_json=excluded.normalized_json""",
            (
                Source(source),
                source_id,
                work_key,
                Lane(lane),
                fetched_at,
                json.dumps(raw, ensure_ascii=False, sort_keys=True),
                raw_hash,
                json.dumps(normalized, ensure_ascii=False, sort_keys=True) if normalized else None,
            ),
        )

    def list_source_records(self, work_key: str) -> list[Row]:
        """Return the latest source responses for one paper."""
        return self._rows(
            "SELECT * FROM source_records WHERE work_key = ? ORDER BY source, source_id",
            (work_key,),
        )

    def add_event(
        self,
        run_id: str,
        work_key: str,
        kind: EventKind,
        *,
        field: str | None = None,
        old: str | None = None,
        new: str | None = None,
        created_at: str,
    ) -> int:
        """Append one audit event and return its stable integer identity."""
        cursor = self._write(
            """INSERT INTO events (run_id, work_key, kind, field, old, new, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (run_id, work_key, EventKind(kind), field, old, new, created_at),
        )
        return cursor.lastrowid

    def list_unexported_events(self) -> list[Row]:
        """Return pending audit events in insertion order, including older runs."""
        return self._rows("SELECT * FROM events WHERE exported_in_run IS NULL ORDER BY event_id")

    def mark_events_exported(self, event_ids: Iterable[int], run_id: str) -> None:
        """Mark only the supplied events, preserving any previous export marker."""
        for event_id in event_ids:
            self._write(
                """UPDATE events SET exported_in_run = ?
                WHERE event_id = ? AND exported_in_run IS NULL""",
                (run_id, event_id),
            )

    def record_run(
        self,
        run_id: str,
        *,
        started_at: str,
        finished_at: str | None,
        status: str,
        counts: Row,
    ) -> None:
        """Create or finish a run, preserving its original start time."""
        if status not in {"running", "completed", "partial", "failed"}:
            raise ValueError("Unknown run status")
        self._write(
            """INSERT INTO runs VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET finished_at=excluded.finished_at,
            status=excluded.status, counts_json=excluded.counts_json""",
            (run_id, started_at, finished_at, status, json.dumps(counts, sort_keys=True)),
        )

    def list_runs(self, limit: int = 10) -> list[Row]:
        """Return the newest runs, with deterministic ordering for equal timestamps."""
        if type(limit) is not int or limit < 1:
            raise ValueError("Run limit must be a positive integer")
        return self._rows(
            "SELECT * FROM runs ORDER BY started_at DESC, run_id DESC LIMIT ?", (limit,)
        )

    def store_decision(
        self,
        work_key: str,
        decision: str,
        *,
        decided_at: str,
        note: str = "",
    ) -> None:
        """Append a changed review decision; identical re-imports do not add history."""
        if decision not in {"accepted", "rejected", "not_collab"}:
            if not decision.startswith("merge:"):
                raise ValueError("Unknown review decision")
            target = decision.removeprefix("merge:")
            if target == work_key or self.get_work(target) is None:
                raise ValueError("Merge target must be another existing work")
        current = self.get_decision(work_key)
        if current and (current["decision"], current["note"]) == (decision, note):
            return
        self._write(
            "INSERT INTO decisions VALUES (?, ?, ?, ?)",
            (work_key, decision, decided_at, note),
        )

    def get_decision(self, work_key: str) -> Row | None:
        """Return the most recently imported decision for a paper."""
        rows = self._rows(
            "SELECT * FROM decisions WHERE work_key = ? ORDER BY rowid DESC LIMIT 1",
            (work_key,),
        )
        return rows[0] if rows else None

    def get_source_record(self, source: Source, source_id: str) -> Row | None:
        """Find a provider identity even when the record has no external identifiers."""
        rows = self._rows(
            "SELECT * FROM source_records WHERE source = ? AND source_id = ?",
            (Source(source), source_id),
        )
        return rows[0] if rows else None

    def get_work_state(self, work_key: str) -> Row | None:
        """Read the canonical matching snapshot, or None for pre-migration records."""
        row = self.get_work(work_key)
        return json.loads(row["state_json"]) if row and row["state_json"] else None

    def save_work_state(self, work_key: str, state: Row) -> None:
        """Persist the canonical snapshot in the same transaction as its audit events."""
        cursor = self._write(
            "UPDATE works SET state_json = ? WHERE work_key = ?",
            (json.dumps(state, ensure_ascii=False, sort_keys=True), work_key),
        )
        if cursor.rowcount != 1:
            raise ValueError("Cannot save a snapshot for an unknown work")

    def list_events(self, work_key: str) -> list[Row]:
        """Read a paper's complete audit trail, including previously exported events."""
        return self._rows("SELECT * FROM events WHERE work_key = ? ORDER BY event_id", (work_key,))

    def canonical_key(self, key: str) -> str:
        """Resolve an old reviewed key after an explicitly approved merge."""
        seen = set()
        while key not in seen:
            seen.add(key)
            rows = self._rows("SELECT work_key FROM work_aliases WHERE alias = ?", (key,))
            if not rows:
                return key
            key = rows[0]["work_key"]
        raise ValueError("Cycle in work aliases")

    def known_arxiv_ids(self) -> list[str]:
        """Return all known preprints for weekly metadata refresh."""
        return [
            row["value"]
            for row in self._rows(
                "SELECT value FROM identifiers WHERE scheme = 'arxiv' ORDER BY value"
            )
        ]

    def merge_works(self, source: str, target: str) -> None:
        """Apply only an explicit reviewer merge, preserving references and audit history."""
        source, target = self.canonical_key(source), self.canonical_key(target)
        if source == target:
            return
        if self.get_work(source) is None or self.get_work(target) is None:
            raise ValueError("Both merge identities must exist")
        first = min(self.get_work(source)["first_seen"], self.get_work(target)["first_seen"])
        self._write("UPDATE works SET first_seen = ? WHERE work_key = ?", (first, target))
        for table in ("identifiers", "source_records", "events", "decisions", "work_aliases"):
            self._write(f'UPDATE "{table}" SET work_key = ? WHERE work_key = ?', (target, source))
        self._write("INSERT INTO work_aliases VALUES (?, ?)", (source, target))
        self._write("DELETE FROM works WHERE work_key = ?", (source,))

    def touch_work(self, key: str, stamp: str) -> None:
        """Record a material correction/retraction without replacing publication metadata."""
        self._write("UPDATE works SET last_changed = ? WHERE work_key = ?", (stamp, key))

    def backup_to(self, path: Path) -> None:
        """Create a consistent SQLite backup without copying a potentially active journal."""
        with closing(sqlite3.connect(path)) as destination:
            self._db.conn.backup(destination)

    @staticmethod
    def copy_database(source: Path, target: Path) -> None:
        """Clone existing history read-only for dry runs; never initialize the original."""
        if source.exists():
            uri = source.resolve().as_uri() + "?mode=ro"
            with (
                closing(sqlite3.connect(uri, uri=True)) as original,
                closing(sqlite3.connect(target)) as destination,
            ):
                original.backup(destination)
