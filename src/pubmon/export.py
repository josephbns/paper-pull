"""One-row-per-paper review exports with atomic file replacement."""

import csv
import json
import os
import tempfile
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook

from pubmon.diff import MATERIAL_FIELDS
from pubmon.master import MasterRow, match_master
from pubmon.models import EventKind
from pubmon.store import Store

COLUMNS = [
    "candidate_id",
    "work_key",
    "events",
    "lanes",
    "confidence",
    "ibm_confirmed",
    "title",
    "pub_date",
    "status",
    "venue",
    "type",
    "doi",
    "arxiv_id",
    "pmid",
    "openalex_id",
    "versions",
    "first_author",
    "n_authors",
    "matched_names",
    "changes",
    "possible_duplicate_of",
    "master_pub_id",
    "match_method",
    "sources",
    "first_seen",
    "link",
    "decision",
    "reviewer_note",
]
SNAPSHOT_COLUMNS = [
    name for name in COLUMNS if name not in {"events", "changes", "decision", "reviewer_note"}
] + ["latest_decision"]
EVENT_ORDER = ("NEW", "LINKED_PREPRINT", "UPDATED", "CORRECTION", "RETRACTED", "POSSIBLE_DUPLICATE")


def group_by_work(events: list[dict]) -> dict[str, list[dict]]:
    """Keep all audit events while grouping them by real paper identity."""
    grouped = defaultdict(list)
    for event in events:
        grouped[event["work_key"]].append(event)
    return dict(grouped)


def _after(first: str, second: str) -> bool:
    return datetime.fromisoformat(first) > datetime.fromisoformat(second)


def eligible_events(store: Store, key: str, events: list[dict]) -> list[dict]:
    """Suppress rejected candidates until a later material change occurs."""
    decision = store.get_decision(key)
    if not decision or decision["decision"] not in {"rejected", "not_collab"}:
        return events
    recent = [event for event in events if _after(event["created_at"], decision["decided_at"])]
    changed = any(
        (event["kind"] == EventKind.UPDATED and event["field"] in MATERIAL_FIELDS)
        or event["kind"] in {EventKind.CORRECTION, EventKind.RETRACTED}
        for event in recent
    )
    return recent if changed else []


def _versions(records: list[dict]) -> str:
    descriptions = set()
    for record in records:
        if not record["normalized_json"]:
            continue
        work = json.loads(record["normalized_json"])
        identifier = (
            "arXiv:" + work["arxiv_id"]
            if work.get("arxiv_id") and work["type"] == "preprint"
            else work.get("doi") or work["source_id"]
        )
        descriptions.add(
            f"{work['pub_date']} {identifier} ({work['type']}, {work.get('venue') or 'venue unknown'})"
        )
    return " → ".join(sorted(descriptions))


def _duplicates(store: Store, key: str) -> str:
    targets = set()
    for event in store.list_events(key):
        if event["kind"] == EventKind.POSSIBLE_DUPLICATE:
            targets.update(json.loads(event["new"]))
    descriptions = []
    for target in sorted(targets):
        target = store.canonical_key(target)
        if target == key:
            continue
        work = store.get_work(target)
        ids = ", ".join(item["value"] for item in store.get_identifiers(target))
        descriptions.append(f"{target}: {(work or {}).get('title', 'unknown')} [{ids}]")
    return "; ".join(descriptions)


def _preprints(normalized: list[dict]) -> dict[str, str]:
    """Keep preprint details beside the one paper row: arXiv date and other preprint links."""
    arxiv_dates = sorted(work["pub_date"] for work in normalized if work["source"] == "arxiv")
    others = sorted(
        {
            "https://doi.org/" + work["doi"]
            for work in normalized
            if work["type"] == "preprint"
            and work.get("doi")
            and not work.get("arxiv_id")
            and not work["doi"].startswith("10.48550/arxiv")  # arXiv's own DOIs: arXiv column
        }
    )
    return {
        "arxiv_date": arxiv_dates[0] if arxiv_dates else "",
        "other_preprints": "; ".join(others),
    }


def paper_row(store: Store, key: str, run_id: str, master: list[MasterRow], lanes: dict) -> dict:
    """Build one paper row, independently of how many events or source records it has."""
    state = store.get_work_state(key) or store.get_work(key)
    records = store.list_source_records(key)
    normalized = [json.loads(row["normalized_json"]) for row in records if row["normalized_json"]]
    matched = match_master(state, master, store.get_identifiers(key))
    authors = state.get("authors") or []
    names = sorted({name for work in normalized for name in work.get("matched_names", [])})
    duplicate = _duplicates(store, key)
    row = {name: state.get(name) if state.get(name) is not None else "" for name in COLUMNS}
    row.update(
        candidate_id=f"{run_id}-{key[:8]}",
        work_key=key,
        lanes="; ".join(sorted(lanes.get(key, set()))),
        confidence=state.get("confidence", "uncertain"),
        ibm_confirmed=bool(state.get("ibm_confirmed")),
        versions=_versions(records),
        first_author=authors[0]["name"] if authors else "",
        n_authors=len(authors),
        matched_names="; ".join(names),
        possible_duplicate_of=duplicate,
        master_pub_id="; ".join(matched.pub_ids),
        match_method=matched.method,
        sources="; ".join(sorted({record["source"] for record in records})),
        first_seen=store.get_work(key)["first_seen"],
        decision="",
        reviewer_note="",
        all_authors="; ".join(author["name"] for author in authors),
        review_events="; ".join(sorted({event["kind"] for event in store.list_events(key)})),
        **_preprints(normalized),
    )
    row["arxiv_id"] = "arXiv:" + str(row["arxiv_id"]) if row["arxiv_id"] else ""
    row["link"] = (
        "https://doi.org/" + row["doi"]
        if row["doi"]
        else ("https://arxiv.org/abs/" + str(state["arxiv_id"]) if state.get("arxiv_id") else "")
    )
    if not row["link"]:
        if row["pmid"]:
            row["link"] = "https://pubmed.ncbi.nlm.nih.gov/" + str(row["pmid"]) + "/"
        elif row["openalex_id"]:
            row["link"] = "https://openalex.org/" + str(row["openalex_id"])
    return row


def candidate_rows(
    store: Store, run_id: str, master: list[MasterRow], lanes: dict
) -> tuple[list[dict], list[int]]:
    """Return one row per eligible paper and exactly the events represented in those rows."""
    rows, event_ids = [], []
    for key, pending in sorted(group_by_work(store.list_unexported_events()).items()):
        events = eligible_events(store, key, pending)
        if not events:
            continue
        row = paper_row(store, key, run_id, master, lanes)
        kinds = {event["kind"] for event in events}
        row["events"] = "; ".join(kind for kind in EVENT_ORDER if kind in kinds)
        row["changes"] = "; ".join(
            f"{event['field']}: {event['old'] or '(none)'} → {event['new'] or '(none)'}"
            for event in events
            if event["kind"] == EventKind.UPDATED
        )
        rows.append(row)
        event_ids.extend(event["event_id"] for event in events)
    return rows, event_ids


def snapshot_rows(store: Store, run_id: str, master: list[MasterRow], lanes: dict) -> list[dict]:
    """Include every canonical paper once, including accepted and rejected papers."""
    rows = []
    for work in store.list_works():
        row = paper_row(store, work["work_key"], run_id, master, lanes)
        row["latest_decision"] = (store.get_decision(work["work_key"]) or {}).get("decision", "")
        rows.append(row)
    return rows


def _atomic(path: Path, writer: Callable[[Path], None]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError("Refusing to overwrite an existing review file")
    descriptor, name = tempfile.mkstemp(dir=path.parent, suffix=path.suffix)
    os.close(descriptor)
    temporary = Path(name)
    try:
        writer(temporary)
        with temporary.open("rb+") as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_candidates(rows: list[dict], path: Path) -> None:
    """Write BOM CSV atomically; a failed rename leaves events pending for retry."""
    write_table(rows, path, COLUMNS)


def write_snapshot(rows: list[dict], path: Path) -> None:
    """Write a separate full-paper snapshot without altering a reviewed candidate file."""
    write_table(rows, path, SNAPSHOT_COLUMNS)


def write_xlsx(rows: list[dict], path: Path) -> None:
    """Create a new review workbook with literal strings and text-formatted identifier cells."""

    def write(temporary: Path) -> None:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Candidates"
        sheet.append(COLUMNS)
        for row in rows:
            sheet.append([row.get(name, "") for name in COLUMNS])
        for cells in sheet.iter_rows():
            for cell in cells:
                if isinstance(cell.value, str):
                    cell.data_type = "s"
                if COLUMNS[cell.column - 1] in {"doi", "arxiv_id", "pmid", "openalex_id"}:
                    cell.number_format = "@"
        workbook.save(temporary)
        workbook.close()

    _atomic(path, write)


def write_table(rows: list[dict], path: Path, columns: list[str]) -> None:
    """Write a named-column BOM CSV atomically without replacing an existing report."""
    _atomic(path, lambda temporary: _write_csv(temporary, rows, columns))
