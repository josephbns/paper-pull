"""Collect independent lanes, with explicit synthetic replay for offline CLI validation."""

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import arxiv

from pubmon.config import Settings
from pubmon.models import Lane, Source, Work
from pubmon.normalize import normalize_ids
from pubmon.sources import arxiv_src, crossref, openalex
from pubmon.sources.common import FetchReport, LaneFailed


@dataclass
class Collection:
    """Successful lane records plus explicit failures; absence never means deletion."""

    works: list[Work] = field(default_factory=list)
    raw: dict = field(default_factory=dict)
    reports: dict[str, FetchReport] = field(default_factory=dict)
    counts: dict = field(default_factory=dict)
    notices: list[dict] = field(default_factory=list)


def _fixture_arxiv(path: Path) -> list[arxiv.Result]:
    items = json.loads((path / "arxiv.json").read_text())
    results = []
    for raw in items:
        results.append(
            arxiv.Result(
                entry_id=raw["entry_id"],
                title=raw["title"],
                published=datetime.fromisoformat(raw["published"]),
                updated=datetime.fromisoformat(raw["updated"]),
                authors=[arxiv.Result.Author(name) for name in raw["authors"]],
                doi=raw.get("doi", ""),
                journal_ref=raw.get("journal_ref", ""),
            )
        )
    return results


def _replay(
    lane: Lane,
    settings: Settings,
    known: list[str],
    report: FetchReport,
    backfill: bool,
    path: Path,
) -> list[Work]:
    if lane in {Lane.PAIR, Lane.CLINIC_QUANTUM}:
        records = json.loads((path / "openalex.json").read_text())["results"]
        if lane == Lane.PAIR:
            records = [raw for raw in records if openalex._has_ibm(raw, settings)]
        return openalex._papers(records, settings, lane, report)
    results = _fixture_arxiv(path)

    def fetch(search: arxiv.Search) -> Iterator[arxiv.Result]:
        if search.id_list:
            return iter(
                item
                for item in results
                if normalize_ids(arxiv_id=item.entry_id)["arxiv_id"] in search.id_list
            )
        key = (lambda item: item.published) if backfill else (lambda item: item.updated)
        return iter(sorted(results, key=key, reverse=True))

    client = SimpleNamespace(results=fetch)
    if lane == Lane.RECHECK:
        return arxiv_src.recheck(settings, known, report=report, watchlist=[], client=client)
    as_of = max(item.updated.date() for item in results) if results else None
    return arxiv_src.fetch_feed(
        settings, backfill=backfill, today=as_of, report=report, watchlist=[], client=client
    )


def collect(
    settings: Settings,
    known: list[str],
    *,
    run_id: str,
    backfill: bool = False,
    fixtures: Path | None = None,
) -> Collection:
    """Keep successful lanes while recording failed lanes independently."""
    collection = Collection()
    jobs = {
        Lane.PAIR: lambda report: openalex.fetch_pair(settings, report=report),
        Lane.CLINIC_QUANTUM: lambda report: openalex.fetch_clinic_quantum(settings, report=report),
        Lane.ARXIV_FEED: lambda report: arxiv_src.fetch_feed(
            settings, report=report, backfill=backfill
        ),
        Lane.RECHECK: lambda report: arxiv_src.recheck(settings, known, report=report),
    }
    for lane, fetch in jobs.items():
        report = FetchReport(run_id=run_id)
        collection.reports[lane] = report
        try:
            works = (
                _replay(lane, settings, known, report, backfill, fixtures)
                if fixtures
                else fetch(report)
            )
            collection.works.extend(works)
            collection.notices.extend(report.notices)
            collection.counts[lane] = {
                "status": "completed",
                "count": len(works),
                "skipped": dict(report.skipped),
            }
        except LaneFailed as exc:
            collection.counts[lane] = {"status": "failed", "error": str(exc), "count": 0}
        _raw_index(collection, lane, report)
    return collection


def _raw_index(collection: Collection, lane: Lane, report: FetchReport) -> None:
    for raw in report.raw_records:
        try:
            if lane in {Lane.PAIR, Lane.CLINIC_QUANTUM}:
                identity = (Source.OPENALEX, normalize_ids(openalex_id=raw["id"])["openalex_id"])
            else:
                identity = (Source.ARXIV, normalize_ids(arxiv_id=raw["entry_id"])["arxiv_id"])
        except (KeyError, ValueError):
            # Malformed failed/skipped responses remain archived, never indexed for matching.
            continue
        collection.raw[identity] = raw


def enrich(doi: str, settings: Settings, report: FetchReport, fixtures: Path | None) -> dict:
    """Use live Crossref or a strict local fixture lookup; replay never falls back to HTTP."""
    if fixtures is None:
        return crossref.enrich(doi, settings, report=report)
    responses = [
        json.loads((fixtures / name).read_text())
        for name in ("crossref.json", "crossref_notice.json")
    ]
    extra = fixtures / "crossref_updates.json"
    if extra.exists():
        responses.extend(json.loads(extra.read_text()))
    match = next(
        (raw for raw in responses if normalize_ids(doi=raw["message"]["DOI"])["doi"] == doi), None
    )
    if match is None:
        return {}
    # The real adapter still parses the fixture and applies its normal retry/error contract.
    from dataclasses import replace

    local = replace(settings, email="synthetic@example.invalid")
    client = SimpleNamespace(works=lambda **kwargs: match)
    return crossref.enrich(doi, local, report=report, client=client)
