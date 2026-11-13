"""Material changes ignore fetch bookkeeping and retain deterministic field order."""

from pubmon.diff import material_changes


def test_crossref_preprint_doi_overrides_arxiv_publication_inference():
    from dataclasses import replace

    from pubmon.diff import canonical_state
    from pubmon.models import Lane, Source, Work, WorkType

    arxiv = Work(
        source=Source.ARXIV,
        source_id="2508.08200",
        lane=Lane.ARXIV_FEED,
        title="Synthetic preprint",
        title_norm="synthetic preprint",
        pub_date="2025-08-06",
        year=2025,
        type=WorkType.PREPRINT,
        raw_hash="synthetic",
        doi="10.5555/preprint",
    )
    crossref = replace(arxiv, source=Source.CROSSREF, source_id=arxiv.doi)
    previous = canonical_state([arxiv])
    assert previous["status"] == "published"
    corrected = canonical_state([arxiv, crossref], previous)
    assert corrected["status"] == "preprint" and corrected["type"] == "preprint"
    journal = replace(
        crossref, type=WorkType.ARTICLE, doi="10.5555/journal", source_id="10.5555/journal"
    )
    assert canonical_state([arxiv, crossref, journal])["status"] == "published"


def test_material_changes_includes_all_changed_fields():
    old = {"doi": None, "venue": None, "status": "preprint", "raw_hash": "old"}
    new = {
        "doi": "10.5555/journal",
        "venue": "Synthetic Journal",
        "status": "published",
        "raw_hash": "new",
    }
    changes = material_changes(old, new)
    assert [change.field for change in changes] == ["doi", "venue", "status"]
    assert changes[0].old is None and changes[0].new == "10.5555/journal"


def test_fetch_time_and_raw_hash_are_not_material_changes():
    assert (
        material_changes(
            {"raw_hash": "old", "fetched_at": "before"}, {"raw_hash": "new", "fetched_at": "after"}
        )
        == []
    )
