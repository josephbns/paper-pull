"""Optional public API recordings; replay is offline and first recording is explicit."""

import csv
from pathlib import Path

import pytest

from pubmon.config import load_config
from pubmon.sources import arxiv_src, crossref, openalex

pytestmark = pytest.mark.vcr


@pytest.fixture
def recording_settings(
    request, record_mode, disable_recording, vcr_cassette_dir, default_cassette_name
):
    """Skip unrecorded API checks unless the owner explicitly enables recording."""
    if disable_recording:
        pytest.skip("Optional API recordings disabled")
    cassette = Path(vcr_cassette_dir) / default_cassette_name
    recording = record_mode != "none"
    if not recording and not cassette.exists():
        pytest.skip("No recorded cassette yet; see README recording instructions")
    settings = load_config(Path(__file__).resolve().parents[1])
    if recording:
        if request.node.name != "test_arxiv_recording":
            settings.require_network_credentials()
    else:
        # VCR removes credentials from matching; replay needs no real secret values.
        from dataclasses import replace

        settings = replace(settings, openalex_api_key="replay-only", email="replay@example.invalid")
    return settings


def _public_pair():
    with (Path(__file__).parent / "fixtures/golden_pairs.csv").open() as stream:
        return next(csv.DictReader(stream))


def test_openalex_recording(recording_settings):
    works = openalex.fetch_pair(recording_settings)
    assert works and all(work.openalex_id for work in works)


def test_arxiv_recording(recording_settings):
    identity = _public_pair()["arxiv_id"]
    works = arxiv_src.recheck(recording_settings, [identity], watchlist=[])
    assert len(works) == 1 and works[0].arxiv_id == identity


def test_crossref_recording(recording_settings):
    doi = _public_pair()["doi"]
    result = crossref.enrich(doi, recording_settings)
    assert result["doi"] == doi and result["venue"]
