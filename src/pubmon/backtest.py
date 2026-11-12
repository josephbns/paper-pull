"""Compare existing public history with approved master fields without changing either input."""

from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path

from pubmon.export import write_table
from pubmon.master import MasterRow, match_master, publication_date, read_master
from pubmon.store import Store

TYPES = {"peer reviewed journal", "open publication", "review paper"}
STATUSES = {"published", "accepted"}
COLUMNS = [
    "pub_id",
    "name",
    "type",
    "status",
    "pub_date",
    "eligible",
    "found",
    "match_method",
    "work_keys",
    "reason",
]


def _exclusion(row: MasterRow, since: date) -> str:
    values = row.values
    if str(values["Type of Paper"] or "").strip().casefold() not in TYPES:
        return "excluded_type"
    if str(values["Pub Status"] or "").strip().casefold() not in STATUSES:
        return "excluded_status"
    published = publication_date(values["Date of Publication"])
    if published is None:
        return "missing_date"
    return "before_since" if published < since else ""


def _matches(store: Store, rows: list[MasterRow]) -> dict[str, list[tuple[str, str]]]:
    matches = defaultdict(list)
    for work in store.list_works():
        key = work["work_key"]
        state = store.get_work_state(key) or work
        result = match_master(state, rows, store.get_identifiers(key))
        for pub_id in result.pub_ids:
            matches[pub_id].append((key, result.method))
    return matches


def compare(store: Store, rows: list[MasterRow], since: date) -> tuple[list[dict], dict]:
    """Report row-level recall; uncertain multiple-work matches do not count as found."""
    eligible = [row for row in rows if not _exclusion(row, since)]
    matches = _matches(store, eligible)
    report = []
    for row in rows:
        excluded = _exclusion(row, since)
        candidates = sorted(set(matches.get(row.pub_id, [])))
        found = not excluded and len(candidates) == 1
        reason = excluded or ("matched" if found else "ambiguous" if candidates else "not_found")
        published = publication_date(row.values["Date of Publication"])
        report.append(
            {
                "pub_id": row.pub_id,
                "name": row.values["Name"] or "",
                "type": row.values["Type of Paper"] or "",
                "status": row.values["Pub Status"] or "",
                "pub_date": published.isoformat() if published else "",
                "eligible": not bool(excluded),
                "found": found if not excluded else "",
                "match_method": candidates[0][1] if found else "",
                "work_keys": "; ".join(key for key, _ in candidates),
                "reason": reason,
            }
        )
    total = len(eligible)
    found = sum(row["found"] is True for row in report)
    misses = [
        {"pub_id": row["pub_id"], "name": row["name"], "reason": row["reason"]}
        for row in report
        if row["eligible"] and not row["found"]
    ]
    summary = {
        "since": since.isoformat(),
        "eligible_rows": total,
        "found_rows": found,
        "missed_rows": len(misses),
        "excluded_rows": len(rows) - total,
        "ambiguous_rows": sum(row["reason"] == "ambiguous" for row in report),
        "recall": found / total if total else None,
        "misses": misses,
    }
    return report, summary


def run_backtest(database: Path, master: Path, out: Path, *, since: str = "2023-01-01") -> dict:
    """Read history/master and write a new back-test report; make no API requests."""
    start = date.fromisoformat(since)
    if not database.is_file():
        raise ValueError("No history database exists; run backfill before back-testing")
    rows = read_master(master)
    with Store(database, read_only=True) as store:
        report, summary = compare(store, rows, start)
    now = datetime.now(UTC)
    path = out / f"backtest_{now.date().isoformat()}.csv"
    if path.exists():
        path = out / f"backtest_{now.date().isoformat()}_{now.strftime('%H%M%S%f')}.csv"
    write_table(report, path, COLUMNS)
    return {**summary, "path": str(path)}
