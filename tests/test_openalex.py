"""Offline transport tests exercise real PyAlex query building and pagination."""

import copy
import json
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

import pyalex
import pytest
import requests

from pubmon.models import Confidence, EventKind, Lane
from pubmon.sources import openalex
from pubmon.sources.common import FetchReport, LaneFailed


def transport(monkeypatch, payloads):
    urls = []
    payloads = iter(payloads)

    def send(session, request, **kwargs):
        urls.append(request.url)
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps(next(payloads)).encode()
        response.request = request
        response.url = request.url
        return response

    monkeypatch.setattr(requests.Session, "send", send)
    return urls


def test_pair_queries_all_institution_combinations_and_unions(
    monkeypatch, source_settings, api_fixture
):
    payload = api_fixture("openalex.json")
    urls = transport(monkeypatch, [payload] * 4)
    settings = replace(
        source_settings,
        ibm_institution_ids=("I1341412227", "I9991"),
        cc_institution_ids=("I1316902750", "I9992"),
    )
    report = FetchReport(run_id="synthetic-run")
    works = openalex.fetch_pair(settings, report=report)
    assert len(urls) == 4
    assert len(works) == 3
    assert all(work.lane == Lane.PAIR and work.ibm_confirmed for work in works)
    assert works[0].confidence == Confidence.HIGH
    assert works[0].doi == "10.5555/synthetic-1"
    assert works[0].arxiv_id == "2401.99999"
    assert works[0].pmid == "99999999"
    assert works[0].openalex_id == "W9991"
    assert works[0].extra_dois == ["10.5555/other-version"]
    assert works[0].authors[0]["institution_ids"] == ["I99999"]
    assert works[-1].confidence == Confidence.REVIEW  # Conference abstract.
    assert len(report.raw_records) == 8
    assert report.skipped == {"dataset": 1, "software": 1, "before_start": 1}
    assert [notice["kind"] for notice in report.notices] == [
        EventKind.CORRECTION,
        EventKind.RETRACTED,
    ]
    for url in urls:
        query = parse_qs(urlsplit(url).query)
        assert query["per-page"] == ["200"]
        assert query["cursor"] == ["*"]
        assert "from_publication_date:2021-01-01" in query["filter"][0]
        assert "+" in urlsplit(url).query  # PyAlex emits the AND operator literally.
    assert pyalex.config.max_retries == 3
    assert pyalex.config.retry_http_codes == [429, *range(500, 600)]


def test_clinic_query_is_title_abstract_and_keeps_clinic_only(
    monkeypatch, source_settings, api_fixture
):
    payload = api_fixture("openalex.json")
    urls = transport(monkeypatch, [payload])
    works = openalex.fetch_clinic_quantum(source_settings)
    assert works[0].ibm_confirmed is True  # Parent appears in the child's lineage.
    assert works[1].ibm_confirmed is False
    assert all(work.confidence == Confidence.REVIEW for work in works)
    query = parse_qs(urlsplit(urls[0]).query)
    assert "title_and_abstract.search:quantum" in query["filter"][0]
    assert "search" not in query


def test_cursor_pagination_checks_unique_count(monkeypatch, source_settings, api_fixture):
    payload = api_fixture("openalex.json")
    first, second = copy.deepcopy(payload), copy.deepcopy(payload)
    first["results"] = payload["results"][:4]
    first["meta"]["next_cursor"] = "next-synthetic-page"
    second["results"] = payload["results"][4:]
    urls = transport(monkeypatch, [first, second])
    assert len(openalex.fetch_pair(source_settings)) == 3
    assert parse_qs(urlsplit(urls[1]).query)["cursor"] == ["next-synthetic-page"]


def test_incomplete_pagination_fails_lane(monkeypatch, source_settings, api_fixture):
    payload = api_fixture("openalex.json")
    payload["meta"]["count"] = 9
    transport(monkeypatch, [payload])
    with pytest.raises(LaneFailed, match="Incomplete pagination"):
        openalex.fetch_pair(source_settings)


def test_zero_results_is_a_complete_response(monkeypatch, source_settings):
    transport(monkeypatch, [{"meta": {"count": 0, "next_cursor": None}, "results": []}])
    assert openalex.fetch_pair(source_settings) == []


def test_lookup_returns_public_identity_fields_without_config_edits(monkeypatch, source_settings):
    original = source_settings.query_file.read_bytes()
    row = {
        "id": "https://openalex.org/I999",
        "display_name": "Synthetic Institution",
        "ror": "https://ror.org/synthetic",
        "country_code": "US",
        "works_count": 12,
        "lineage": ["https://openalex.org/I999"],
        "irrelevant": "ignored",
    }
    transport(monkeypatch, [{"meta": {"count": 1}, "results": [row]}] * 2)
    found = openalex.lookup_institutions(source_settings, ["Synthetic", "Institution"])
    assert len(found) == 1 and "irrelevant" not in found[0]
    assert source_settings.query_file.read_bytes() == original


def test_transport_failure_hides_key_and_is_not_an_empty_lane(monkeypatch, source_settings, caplog):
    def fail(*args, **kwargs):
        raise requests.HTTPError("https://example.invalid?api_key=synthetic-secret")

    monkeypatch.setattr(requests.Session, "send", fail)
    with pytest.raises(LaneFailed) as error:
        openalex.fetch_pair(source_settings, report=FetchReport(run_id="safe-run"))
    assert "synthetic-secret" not in str(error.value) + caplog.text
    assert "safe-run" in caplog.text


def test_missing_institution_list_fails_before_fetch(source_settings):
    with pytest.raises(LaneFailed, match="Both institution lists"):
        openalex.fetch_pair(replace(source_settings, ibm_institution_ids=()))


@pytest.mark.parametrize("status", [429, 503])
def test_pyalex_transport_retries_transient_statuses(
    monkeypatch,
    source_settings,
    api_fixture,
    status,
):
    from io import BytesIO

    import pyalex.api
    import urllib3

    payload = api_fixture("openalex.json")
    statuses = iter([status, 200])
    calls = []
    original = pyalex.api._get_requests_session

    def session():
        client = original()
        client.trust_env = False  # The mocked connection pool never needs a proxy or socket.
        return client

    def request(*args, **kwargs):
        code = next(statuses)
        calls.append(code)
        return urllib3.response.HTTPResponse(
            status=code, body=BytesIO(json.dumps(payload).encode()), preload_content=False
        )

    monkeypatch.setattr(pyalex.api, "_get_requests_session", session)
    monkeypatch.setattr(urllib3.connectionpool.HTTPSConnectionPool, "_make_request", request)
    monkeypatch.setattr(urllib3.util.retry.Retry, "sleep", lambda *args: None)
    assert len(openalex.fetch_pair(source_settings)) == 3
    assert calls == [status, 200]


def test_repeated_cursor_fails_instead_of_looping(monkeypatch, source_settings, api_fixture):
    payload = api_fixture("openalex.json")
    payload["meta"]["next_cursor"] = "stuck-cursor"
    transport(monkeypatch, [payload, payload])
    with pytest.raises(LaneFailed, match="repeated a cursor"):
        openalex.fetch_pair(source_settings)
