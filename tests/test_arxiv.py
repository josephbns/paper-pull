"""Offline arxiv.Result fixtures cover dates, names, ambiguity and batching."""

from dataclasses import replace
from datetime import date, datetime
from types import SimpleNamespace

import arxiv
import pytest

from pubmon.models import Confidence, Lane
from pubmon.sources import arxiv_src
from pubmon.sources.arxiv_src import WatchAuthor
from pubmon.sources.common import FetchReport, LaneFailed

WATCHLIST = [
    WatchAuthor("Synthetic IBM Author", "IBM", "Synthetic IBM Author"),
    WatchAuthor("Synthetic Clinic Author", "CC", "Synthetic Clinic Author"),
]


def results(api_fixture):
    return [
        arxiv.Result(
            entry_id=raw["entry_id"],
            published=datetime.fromisoformat(raw["published"]),
            updated=datetime.fromisoformat(raw["updated"]),
            title=raw["title"],
            authors=[arxiv.Result.Author(name) for name in raw["authors"]],
            doi=raw["doi"],
            journal_ref=raw["journal_ref"],
        )
        for raw in api_fixture("arxiv.json")
    ]


def test_feed_uses_verbatim_query_and_update_cutoff(source_settings, api_fixture):
    calls = []

    def fetch(search):
        calls.append(search)
        return iter(results(api_fixture))

    report = FetchReport()
    works = arxiv_src.fetch_feed(
        source_settings,
        today=date(2026, 11, 12),
        report=report,
        watchlist=WATCHLIST,
        client=SimpleNamespace(results=fetch),
    )
    assert len(works) == 1
    assert works[0].arxiv_id == "2401.99999"
    assert works[0].ibm_confirmed and works[0].confidence == Confidence.HIGH
    assert works[0].matched_names == ["Synthetic IBM Author", "Synthetic Clinic Author"]
    assert works[0].journal_ref == "Synthetic Quantum Journal 2026"
    assert len(report.raw_records) == 2
    assert report.skipped["before_start"] == 1
    assert calls[0].query == source_settings.read_arxiv_query()
    assert calls[0].sort_by == arxiv.SortCriterion.LastUpdatedDate


def test_start_date_enforced(source_settings, api_fixture):
    items = sorted(results(api_fixture), key=lambda item: item.published, reverse=True)
    queries = []

    def fetch(search):
        queries.append(search)
        return iter(items)

    works = arxiv_src.fetch_feed(
        source_settings, backfill=True, watchlist=WATCHLIST, client=SimpleNamespace(results=fetch)
    )
    assert len(works) == 2
    assert all(work.pub_date >= source_settings.start_date for work in works)
    assert queries[0].sort_by == arxiv.SortCriterion.SubmittedDate


def test_clinic_only_and_no_watchlist_hits_are_retained(source_settings, api_fixture):
    item = results(api_fixture)[0]
    item.authors = [arxiv.Result.Author("Synthetic Clinic Author")]
    client = SimpleNamespace(results=lambda _: iter([item]))
    work = arxiv_src.fetch_feed(
        source_settings, today=date(2026, 11, 12), watchlist=WATCHLIST, client=client
    )[0]
    assert work.confidence == Confidence.REVIEW and not work.ibm_confirmed
    work = arxiv_src.fetch_feed(
        source_settings, today=date(2026, 11, 12), watchlist=[], client=client
    )[0]
    assert work.matched_names == [] and work.confidence == Confidence.REVIEW


def test_common_names_are_uncertain(source_settings, api_fixture):
    settings = replace(source_settings, common_names=tuple(author.name for author in WATCHLIST))
    client = SimpleNamespace(results=lambda _: iter(results(api_fixture)[:1]))
    work = arxiv_src.fetch_feed(
        settings, today=date(2026, 11, 12), watchlist=WATCHLIST, client=client
    )[0]
    assert work.confidence == Confidence.UNCERTAIN


def test_names_match_exact_normalized_names_not_substrings(source_settings, api_fixture):
    item = results(api_fixture)[0]
    item.authors = [arxiv.Result.Author("Other Synthetic IBM Author")]
    client = SimpleNamespace(results=lambda _: iter([item]))
    work = arxiv_src.fetch_feed(
        source_settings, today=date(2026, 11, 12), watchlist=WATCHLIST, client=client
    )[0]
    assert work.matched_names == [] and not work.ibm_confirmed


def test_recheck_ignores_window_batches_and_deduplicates(source_settings, api_fixture):
    item = results(api_fixture)[0]
    item.updated = datetime.fromisoformat("2024-01-10T00:00:00+00:00")
    ids = [f"2401.{number:05}" for number in range(99000, 99101)]
    calls = []

    def fetch(search):
        calls.append(search)
        return iter(
            arxiv.Result(
                entry_id=f"https://arxiv.org/abs/{identity}v3",
                published=item.published,
                updated=item.updated,
                title=item.title,
                authors=item.authors,
                doi="10.5555/now-published",
            )
            for identity in search.id_list
        )

    works = arxiv_src.recheck(
        source_settings,
        ids + [ids[0] + "v2"],
        watchlist=WATCHLIST,
        client=SimpleNamespace(results=fetch),
    )
    assert [len(search.id_list) for search in calls] == [100, 1]
    assert len(works) == 101
    assert all(work.lane == Lane.RECHECK and work.doi == "10.5555/now-published" for work in works)


def test_missing_recheck_result_fails_lane(source_settings):
    with pytest.raises(LaneFailed, match="Incomplete known-ID"):
        arxiv_src.recheck(
            source_settings,
            ["2401.99999"],
            watchlist=[],
            client=SimpleNamespace(results=lambda _: iter([])),
        )
    assert arxiv_src.recheck(source_settings, []) == []


def test_default_client_rate_limit_and_retries():
    client = arxiv_src._client()
    assert (client.page_size, client.delay_seconds, client.num_retries) == (100, 3, 3)


def test_watchlist_headers_and_side_validation(tmp_path):
    path = tmp_path / "watchlist.csv"
    with pytest.raises(LaneFailed, match="Copy config"):
        arxiv_src.read_watchlist(path)
    path.write_text("name,side,orcid,arxiv_name\nSynthetic Author,IBM,,Synthetic Author\n")
    assert arxiv_src.read_watchlist(path)[0].side == "IBM"
    path.write_text("name,side,orcid,arxiv_name\nSynthetic Author,UNKNOWN,,Synthetic Author\n")
    with pytest.raises(LaneFailed, match="IBM/CC"):
        arxiv_src.read_watchlist(path)


@pytest.mark.parametrize("status", [429, 503])
def test_arxiv_transport_retries_then_parses_atom(monkeypatch, source_settings, status):
    from pathlib import Path

    import requests

    payload = (Path(__file__).parent / "fixtures/api/arxiv.xml").read_bytes()
    codes = iter([status, 200])
    calls = []
    sleeps = []

    def get(*args, **kwargs):
        calls.append(args)
        response = requests.Response()
        response.status_code = next(codes)
        response._content = payload
        return response

    client = arxiv_src._client()
    monkeypatch.setattr(client._session, "get", get)
    monkeypatch.setattr(arxiv.time, "sleep", sleeps.append)
    works = arxiv_src.recheck(source_settings, ["2401.99999"], watchlist=WATCHLIST, client=client)
    assert len(calls) == 2 and len(works) == 1
    assert works[0].doi == "10.5555/synthetic-1"
    assert sleeps and 0 < sleeps[0] <= 3


def test_arxiv_persistent_failure_is_a_lane_failure(monkeypatch, source_settings):
    import requests

    calls = []

    def get(*args, **kwargs):
        calls.append(args)
        response = requests.Response()
        response.status_code = 503
        return response

    client = arxiv_src._client()
    monkeypatch.setattr(client._session, "get", get)
    monkeypatch.setattr(arxiv.time, "sleep", lambda _: None)
    with pytest.raises(LaneFailed, match="HTTP 503"):
        arxiv_src.recheck(source_settings, ["2401.99999"], watchlist=[], client=client)
    assert len(calls) == 4  # Initial attempt plus arxiv.py's three retries.
