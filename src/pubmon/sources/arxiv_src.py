"""arXiv feed discovery and known-identifier rechecks using arxiv.py."""

import csv
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import arxiv

from pubmon.config import Settings, WatchAuthor, watch_author
from pubmon.models import Author, Confidence, Lane, Source, Work, WorkType
from pubmon.normalize import normalize_ids, normalize_title
from pubmon.sources.common import FetchReport, LaneFailed, Raw, lane_guard, raw_hash


def read_watchlist(path: Path) -> list[WatchAuthor]:
    """Read explicit owner configuration without guessing names or affiliations."""
    if not path.exists():
        raise LaneFailed(
            Lane.ARXIV_FEED,
            "Copy config/watchlist.example.csv to config/watchlist.csv and review it",
        )
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not {"name", "side", "orcid", "arxiv_name"} <= set(reader.fieldnames or []):
            raise LaneFailed(Lane.ARXIV_FEED, "Watchlist headers are missing")
        authors = []
        for row in reader:
            try:
                authors.append(watch_author(row))
            except ValueError:
                raise LaneFailed(
                    Lane.ARXIV_FEED, "Watchlist requires names and IBM/CC or PARTNER sides"
                ) from None
        return authors


def _client() -> arxiv.Client:
    return arxiv.Client(page_size=100, delay_seconds=3, num_retries=3)


def fetch_feed(
    settings: Settings,
    *,
    backfill: bool = False,
    today: date | None = None,
    report: FetchReport | None = None,
    watchlist: list[WatchAuthor] | None = None,
    client: arxiv.Client | None = None,
) -> list[Work]:
    """Discover recent updates or backfill by submission date, keeping uncertain hits."""
    report = report if report is not None else FetchReport()
    with lane_guard(Lane.ARXIV_FEED, report):
        watchlist = _configured_watchlist(settings) if watchlist is None else watchlist
        cutoff = (today or datetime.now(UTC).date()) - timedelta(days=settings.arxiv_window_days)
        start = date.fromisoformat(settings.start_date)
        # Publication dates are not monotonic when sorted by update time.
        order = (
            arxiv.SortCriterion.SubmittedDate if backfill else arxiv.SortCriterion.LastUpdatedDate
        )
        search = arxiv.Search(
            query=settings.read_arxiv_query(), sort_by=order, sort_order=arxiv.SortOrder.Descending
        )
        works = {}
        for result in (client or _client()).results(search):
            if backfill and result.published.date() < start:
                break
            if not backfill and result.updated.date() < cutoff:
                break
            raw = _raw_result(result)
            report.raw_records.append(raw)
            if result.published.date() < start:
                report.skipped["before_start"] += 1
                continue
            work = _to_work(raw, settings, Lane.ARXIV_FEED, watchlist)
            works[work.source_id] = work
        return list(works.values())


def recheck(
    settings: Settings,
    ids: list[str],
    *,
    report: FetchReport | None = None,
    watchlist: list[WatchAuthor] | None = None,
    client: arxiv.Client | None = None,
) -> list[Work]:
    """Re-fetch every known arXiv ID in batches of 100, independent of the weekly window."""
    report = report if report is not None else FetchReport()
    with lane_guard(Lane.RECHECK, report):
        unique = sorted({normalize_ids(arxiv_id=value)["arxiv_id"] for value in ids})
        if not unique:
            return []
        watchlist = _configured_watchlist(settings) if watchlist is None else watchlist
        client = client or _client()
        works = {}
        for offset in range(0, len(unique), 100):
            batch = unique[offset : offset + 100]
            received = set()
            for result in client.results(arxiv.Search(id_list=batch)):
                raw = _raw_result(result)
                report.raw_records.append(raw)
                work = _to_work(raw, settings, Lane.RECHECK, watchlist)
                received.add(work.source_id)
                if result.published.date() >= date.fromisoformat(settings.start_date):
                    works[work.source_id] = work
                else:
                    report.skipped["before_start"] += 1
            if received != set(batch):
                raise LaneFailed(Lane.RECHECK, "Incomplete known-ID recheck")
        return list(works.values())


def _raw_result(result: arxiv.Result) -> Raw:
    return {
        "entry_id": result.entry_id,
        "updated": result.updated.isoformat(),
        "published": result.published.isoformat(),
        "title": result.title,
        "authors": [author.name for author in result.authors],
        "summary": result.summary,
        "comment": result.comment,
        "journal_ref": result.journal_ref,
        "doi": result.doi,
        "primary_category": result.primary_category,
        "categories": result.categories,
        "links": [
            {
                "href": link.href,
                "title": link.title,
                "rel": link.rel,
                "content_type": link.content_type,
            }
            for link in result.links
        ],
    }


def _to_work(raw: Raw, settings: Settings, lane: Lane, watchlist: list[WatchAuthor]) -> Work:
    names = {normalize_title(name) for name in raw["authors"]}
    matched = [author for author in watchlist if normalize_title(author.arxiv_name) in names]
    common = set(map(normalize_title, settings.common_names))
    ibm = any(author.side == "IBM" for author in matched)
    ambiguous = bool(matched) and all(
        normalize_title(author.name) in common or normalize_title(author.arxiv_name) in common
        for author in matched
    )
    confidence = Confidence.HIGH if ibm else Confidence.REVIEW
    if ambiguous:
        confidence = Confidence.UNCERTAIN
    published = datetime.fromisoformat(raw["published"]).date()
    ids = normalize_ids(doi=raw["doi"], arxiv_id=raw["entry_id"])
    return Work(
        source=Source.ARXIV,
        source_id=ids["arxiv_id"],
        lane=lane,
        title=raw["title"],
        title_norm=normalize_title(raw["title"]),
        pub_date=published.isoformat(),
        year=published.year,
        type=WorkType.PREPRINT,
        journal_ref=raw["journal_ref"] or None,
        authors=[Author(name=name, orcid=None, institution_ids=[]) for name in raw["authors"]],
        ibm_confirmed=ibm,
        matched_names=list(dict.fromkeys(author.name for author in matched)),
        confidence=confidence,
        raw_hash=raw_hash(raw),
        **ids,
    )


def _configured_watchlist(settings: Settings) -> list[WatchAuthor]:
    if settings.watchlist is not None:
        return list(settings.watchlist)
    return read_watchlist(settings.watchlist_file)
