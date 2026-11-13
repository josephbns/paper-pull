"""Run public discovery, atomic matching, read-only reconciliation and review exports."""

import json
import logging
import tempfile
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from pubmon import export
from pubmon.config import Settings
from pubmon.log import run_logging
from pubmon.master import read_master
from pubmon.match import resolve_and_store
from pubmon.models import EventKind, Source, Work, WorkType
from pubmon.normalize import normalize_ids
from pubmon.sources import collect as sources
from pubmon.sources.common import FetchReport, LaneFailed, raw_hash
from pubmon.store import Store

logger = logging.getLogger(__name__)


def _enrich(
    works: list[Work],
    store: Store,
    settings: Settings,
    collection: sources.Collection,
    run_id: str,
    fixtures: Path | None,
) -> list[Work]:
    result, seen = list(works), set()
    report = FetchReport(run_id=run_id)
    failures = []
    for work in works:
        if not work.doi or work.doi in seen:
            continue
        seen.add(work.doi)
        cached = store.get_source_record(Source.CROSSREF, work.doi)
        changed = any(_source_changed(store, item) for item in works if item.doi == work.doi)
        if cached and not changed:
            continue
        try:
            fields = sources.enrich(work.doi, settings, report, fixtures)
        except LaneFailed as exc:
            failures.append(str(exc))
            continue
        if fields:
            result.append(_enriched_work(work, fields))
    collection.reports["crossref"] = report
    for raw in report.raw_records:
        collection.raw[(Source.CROSSREF, normalize_ids(doi=raw["DOI"])["doi"])] = raw
    collection.counts["crossref"] = {
        "status": "failed" if failures else "completed",
        "count": len(report.raw_records),
        "skipped": dict(report.skipped),
        "errors": failures,
    }
    return result


def _source_changed(store: Store, work: Work) -> bool:
    prior = store.get_source_record(work.source, work.source_id)
    return prior is None or prior["raw_hash"] != work.raw_hash


def _enriched_work(work: Work, fields: dict) -> Work:
    published = fields.get("pub_date") or work.pub_date
    kind = fields["type"] if fields["type"] != WorkType.OTHER else work.type
    return replace(
        work,
        source=Source.CROSSREF,
        source_id=work.doi,
        pub_date=published,
        year=int(published[:4]),
        type=kind,
        venue=fields.get("venue") or work.venue,
        raw_hash=fields["raw_hash"],
        extra_dois=sorted(set(work.extra_dois + fields["extra_dois"])),
        is_retracted=work.is_retracted or fields["is_retracted"],
    )


def _notices(
    collection: sources.Collection,
    store: Store,
    settings: Settings,
    run_id: str,
    stamp: str,
    fixtures: Path | None,
) -> None:
    seen = set()
    for notice in collection.notices:
        doi = notice["doi"]
        if not doi or doi in seen:
            continue
        seen.add(doi)
        source_id = normalize_ids(openalex_id=notice["raw"]["id"])["openalex_id"]
        old_notice = store.get_source_record(Source.OPENALEX, source_id)
        if old_notice and old_notice["raw_hash"] == raw_hash(notice["raw"]):
            continue
        report = FetchReport(run_id=run_id)
        try:
            fields = sources.enrich(doi, settings, report, fixtures)
        except LaneFailed as exc:
            collection.counts.setdefault("crossref", {})["status"] = "failed"
            logger.warning("Notice enrichment failed: %s", exc)
            continue
        if not fields:
            logger.info("Notice has no resolvable original and was skipped")
            continue
        collection.reports.setdefault("notices", FetchReport(run_id=run_id)).raw_records.extend(
            report.raw_records
        )
        keys = set()
        for update in fields["update_to"]:
            original = normalize_ids(doi=update.get("DOI"))["doi"]
            key = store.find_work_key({"doi": original}) if original else None
            if key is not None:
                keys.add(key)
        if len(keys) != 1:
            logger.info("Notice original is absent or ambiguous; skipped")
            continue
        _apply_notice(
            store, next(iter(keys)), doi, notice["kind"], report.raw_records[0], run_id, stamp
        )
        with store.transaction():
            store.upsert_source_record(
                Source.OPENALEX,
                source_id,
                next(iter(keys)),
                lane="recheck",
                fetched_at=stamp,
                raw=notice["raw"],
                raw_hash=raw_hash(notice["raw"]),
            )


def _apply_notice(
    store: Store, key: str, doi: str, kind: EventKind, raw: dict, run_id: str, stamp: str
) -> None:
    digest = raw_hash(raw)
    prior = store.get_source_record(Source.CROSSREF, doi)
    if prior and prior["raw_hash"] == digest:
        return
    with store.transaction():
        store.add_event(run_id, key, kind, field="notice_doi", new=doi, created_at=stamp)
        store.upsert_source_record(
            Source.CROSSREF, doi, key, lane="recheck", fetched_at=stamp, raw=raw, raw_hash=digest
        )
        store.touch_work(key, stamp)
        if kind == EventKind.RETRACTED:
            state = store.get_work_state(key)
            state["is_retracted"] = True
            store.save_work_state(key, state)


def _archives(collection: sources.Collection, root: Path, run_id: str) -> None:
    path = root / "data/raw" / run_id
    path.mkdir(parents=True, exist_ok=True)
    for lane, report in collection.reports.items():
        (path / f"{lane}.json").write_text(
            json.dumps(report.raw_records, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def _available(out: Path, stem: str, day: str, run_id: str, suffix: str) -> Path:
    path = out / f"{stem}_{day}{suffix}"
    return path if not path.exists() else out / f"{stem}_{day}_{run_id}{suffix}"


def _export(
    store: Store, root: Path, run_id: str, master: list, lanes: dict, xlsx: bool, dry_run: bool
) -> dict:
    rows, event_ids = export.candidate_rows(store, run_id, master, lanes)
    snapshot = export.snapshot_rows(store, run_id, master, lanes)
    paths = {}
    if not dry_run:
        day = datetime.now(UTC).date().isoformat()
        candidate = _available(root / "out", "candidates", day, run_id, ".csv")
        export.write_candidates(rows, candidate)
        export.write_snapshot(snapshot, _available(root / "out", "works", day, run_id, ".csv"))
        if xlsx:
            export.write_xlsx(rows, candidate.with_suffix(".xlsx"))
        # A failure before all renames leaves every affected event pending for retry.
        with store.transaction():
            store.mark_events_exported(event_ids, run_id)
        paths["candidates"] = str(candidate)
    return {
        "candidates": len(rows),
        "papers": len(snapshot),
        "paths": paths,
        "events": dict(Counter(kind for row in rows for kind in row["events"].split("; "))),
    }


def run(
    settings: Settings,
    *,
    master_path: Path | None = None,
    no_master: bool = False,
    dry_run: bool = False,
    backfill: bool = False,
    xlsx: bool = False,
    fixtures: Path | None = None,
) -> dict:
    """Execute a run; dry-run uses a temporary database and writes no candidate files."""
    if not fixtures:
        settings.require_network_credentials()
    master_path = master_path or settings.master_path
    if not no_master and master_path is None:
        raise ValueError("Configure a master path, pass --master, or select --no-master")
    master = [] if no_master else read_master(master_path)
    root = settings.workspace_dir or settings.project_dir
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    state_root = root / "demo" if fixtures else root
    database = state_root / "data/pubmon.db"
    with tempfile.TemporaryDirectory(prefix="pubmon-") as temporary:
        working = Path(temporary) if dry_run else state_root
        if dry_run:
            local_db = working / "pubmon.db"
            Store.copy_database(database, local_db)
        else:
            local_db = database
        with Store(local_db) as store, run_logging(working / "data/logs" / f"{run_id}.log", run_id):
            if not dry_run:
                store.backup_to(database.with_suffix(".db.bak"))
            return _execute(
                store, settings, master, run_id, working, dry_run, backfill, xlsx, fixtures
            )


def _execute(
    store: Store,
    settings: Settings,
    master: list,
    run_id: str,
    working: Path,
    dry_run: bool,
    backfill: bool,
    xlsx: bool,
    fixtures: Path | None,
) -> dict:
    stamp = datetime.now(UTC).isoformat()
    with store.transaction():
        store.record_run(run_id, started_at=stamp, finished_at=None, status="running", counts={})
    counts = {}
    try:
        collection = sources.collect(
            settings, store.known_arxiv_ids(), run_id=run_id, backfill=backfill, fixtures=fixtures
        )
        works = _enrich(collection.works, store, settings, collection, run_id, fixtures)
        _archives(collection, working, run_id)
        counts = collection.counts
        result = resolve_and_store(
            works, store, settings, run_id=run_id, created_at=stamp, raw_records=collection.raw
        )
        _notices(collection, store, settings, run_id, stamp, fixtures)
        _archives(collection, working, run_id)
        lanes = defaultdict(set)
        for work, match in zip(works, result, strict=True):
            lanes[match.work_key].add(str(work.lane))
        output = _export(
            store,
            working,
            run_id,
            master,
            lanes,
            xlsx,
            dry_run,
        )
        status = (
            "partial"
            if any(item["status"] == "failed" for item in counts.values())
            else "completed"
        )
        _finish(store, run_id, stamp, status, {"lanes": counts, **output})
        logger.info("%s: %s", status, json.dumps({"lanes": counts, **output}))
        return {
            "run_id": run_id,
            "status": status,
            "dry_run": dry_run,
            "fixture_replay": fixtures is not None,
            "collaboration": settings.collaboration_name,
            "partner": settings.partner_label,
            **output,
        }
    except Exception:
        _finish(store, run_id, stamp, "failed", {"lanes": counts})
        raise


def _finish(store: Store, run_id: str, stamp: str, status: str, counts: dict) -> None:
    with store.transaction():
        store.record_run(
            run_id,
            started_at=stamp,
            finished_at=datetime.now(UTC).isoformat(),
            status=status,
            counts=counts,
        )
