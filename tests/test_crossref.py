"""Habanero transport fixtures verify enrichment and HTTP retry policy offline."""

from dataclasses import replace
from types import SimpleNamespace

import httpx2
import pytest

from pubmon.sources import crossref
from pubmon.sources.common import FetchReport, LaneFailed


def transport(monkeypatch, payload, statuses):
    calls = []
    statuses = iter(statuses)

    def get(url, **kwargs):
        calls.append((url, kwargs))
        status = next(statuses)
        body = payload if status == 200 else {"message": [{"message": "Synthetic failure"}]}
        return httpx2.Response(status, json=body, request=httpx2.Request("GET", url))

    monkeypatch.setattr(httpx2, "get", get)
    monkeypatch.setattr(crossref._request.retry, "sleep", lambda _: None)
    return calls


def test_enrich_parses_publication_and_preprint_relation(monkeypatch, source_settings, api_fixture):
    calls = transport(monkeypatch, api_fixture("crossref.json"), [200])
    report = FetchReport()
    result = crossref.enrich("https://doi.org/10.5555/SYNTHETIC-1", source_settings, report=report)
    assert result["doi"] == "10.5555/synthetic-1"
    assert result["pub_date"] == "2026-11-01"
    assert result["venue"] == "Synthetic Quantum Journal"
    assert result["relations"] == {"has-preprint": ["10.5555/preprint"]}
    assert result["extra_dois"] == ["10.5555/preprint"]
    assert len(report.raw_records) == 1 and len(result["raw_hash"]) == 64
    assert len(calls) == 1
    assert "synthetic@example.invalid" in calls[0][1]["headers"]["User-Agent"]


@pytest.mark.parametrize("status", [429, 500, 503])
def test_transient_http_errors_are_retried(monkeypatch, source_settings, api_fixture, status):
    calls = transport(monkeypatch, api_fixture("crossref.json"), [status, status, 200])
    assert crossref.enrich("10.5555/synthetic-1", source_settings)["doi"] == "10.5555/synthetic-1"
    assert len(calls) == 3


def test_persistent_http_failure_becomes_lane_failure(monkeypatch, source_settings, api_fixture):
    calls = transport(monkeypatch, api_fixture("crossref.json"), [503] * 5)
    with pytest.raises(LaneFailed, match="HTTP 503"):
        crossref.enrich("10.5555/synthetic-1", source_settings)
    assert len(calls) == 5


def test_client_error_is_not_retried(monkeypatch, source_settings, api_fixture):
    calls = transport(monkeypatch, api_fixture("crossref.json"), [404])
    with pytest.raises(LaneFailed, match="HTTP 404"):
        crossref.enrich("10.5555/synthetic-1", source_settings)
    assert len(calls) == 1


def test_missing_doi_needs_neither_credentials_nor_network(source_settings):
    def fail(**kwargs):
        raise AssertionError("A DOI-less paper must not trigger an HTTP request")

    assert (
        crossref.enrich(
            None, replace(source_settings, email=None), client=SimpleNamespace(works=fail)
        )
        == {}
    )


def test_notice_retains_original_doi_and_correction_kind(monkeypatch, source_settings, api_fixture):
    transport(monkeypatch, api_fixture("crossref_notice.json"), [200])
    result = crossref.enrich("10.5555/correction", source_settings)
    assert result["update_to"] == [{"DOI": "10.5555/synthetic-1", "type": "correction"}]
    assert result["is_retracted"] is False


def test_partial_date_is_not_invented(monkeypatch, source_settings, api_fixture):
    payload = api_fixture("crossref.json")
    payload["message"]["published"]["date-parts"] = [[2026]]
    transport(monkeypatch, payload, [200])
    assert crossref.enrich("10.5555/synthetic-1", source_settings)["pub_date"] is None
