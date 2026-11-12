"""Offline identity and change-history tests with synthetic metadata and public ID pairs."""

import csv
import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest
from rapidfuzz.fuzz import token_sort_ratio

from pubmon.match import resolve_and_store
from pubmon.models import Author, Confidence, EventKind, Lane, Source, Work, WorkType
from pubmon.normalize import normalize_title
from pubmon.sources.common import raw_hash
from pubmon.store import Store

STAMP = "2026-11-12T18:00:00Z"
LATER = "2026-11-12T19:00:00Z"


def paper(**changes) -> Work:
    work = Work(
        source=Source.OPENALEX,
        source_id="W9991",
        lane=Lane.PAIR,
        title="Synthetic quantum simulation",
        title_norm="",
        pub_date="2024-01-10",
        year=2024,
        type=WorkType.PREPRINT,
        raw_hash="",
        confidence=Confidence.HIGH,
        authors=[
            Author(name="Avery Example", orcid=None, institution_ids=[]),
            Author(name="Blair Synthetic", orcid=None, institution_ids=[]),
        ],
    )
    work = replace(work, **changes)
    work.title_norm = normalize_title(work.title)
    work.raw_hash = raw_hash(asdict(work))
    return work


@pytest.fixture
def history(tmp_path):
    with Store(tmp_path / "history.db") as instance:
        yield instance


def run(history, source_settings, works, run_id="run-1", stamp=STAMP):
    with history.transaction():
        history.record_run(run_id, started_at=stamp, finished_at=None, status="running", counts={})
    return resolve_and_store(works, history, source_settings, run_id=run_id, created_at=stamp)


def test_cross_source_same_paper(history, source_settings):
    first = paper(doi="https://doi.org/10.5555/SYNTHETIC")
    second = paper(
        source=Source.ARXIV,
        source_id="arXiv:2401.99999v2",
        lane=Lane.ARXIV_FEED,
        doi="10.5555/synthetic",
        arxiv_id="2401.99999",
    )
    results = run(history, source_settings, [first, second])
    assert results[0].work_key == results[1].work_key
    assert len(history.list_works()) == 1
    ids = history.get_identifiers(results[0].work_key)
    assert {item["scheme"] for item in ids} == {"doi", "arxiv"}
    assert len(history.list_source_records(results[0].work_key)) == 2


def test_preprint_links_to_journal(history, source_settings):
    preprint = paper(doi="10.5555/preprint", arxiv_id="2401.99999")
    journal = paper(
        source_id="W9992",
        doi="10.5555/journal",
        extra_dois=["10.5555/preprint"],
        type=WorkType.ARTICLE,
        pub_date="2025-03-01",
        year=2025,
        title="A changed journal title",
        venue="Synthetic Journal",
    )
    key = run(history, source_settings, [preprint])[0].work_key
    result = run(history, source_settings, [journal], "run-2", LATER)[0]
    assert result.work_key == key and result.method == "link"
    state = history.get_work_state(key)
    assert state["doi"] == "10.5555/journal" and state["arxiv_id"] == "2401.99999"
    assert state["status"] == "published" and state["venue"] == "Synthetic Journal"
    events = history.list_events(key)
    assert sum(event["kind"] == EventKind.LINKED_PREPRINT for event in events) == 1
    assert any(
        event["field"] == "status" and event["old"] == "preprint" and event["new"] == "published"
        for event in events
    )


def test_publication_triggers_update(history, source_settings):
    preprint = paper(
        source=Source.ARXIV, source_id="2401.99999", arxiv_id="2401.99999", lane=Lane.ARXIV_FEED
    )
    key = run(history, source_settings, [preprint])[0].work_key
    published = paper(
        source=Source.ARXIV,
        source_id="2401.99999",
        arxiv_id="2401.99999",
        lane=Lane.RECHECK,
        doi="10.5555/journal",
        journal_ref="Synthetic Journal 2026",
    )
    run(history, source_settings, [published], "run-2", LATER)
    state = history.get_work_state(key)
    assert state["status"] == "published" and state["type"] == "article"
    updates = [row for row in history.list_events(key) if row["kind"] == EventKind.UPDATED]
    assert {row["field"] for row in updates} >= {"doi", "status", "type", "journal_ref"}


def test_rerun_is_idempotent(history, source_settings):
    preprint = paper(source=Source.ARXIV, source_id="2401.99999", arxiv_id="2401.99999")
    journal = paper(
        source_id="W9992",
        type=WorkType.ARTICLE,
        doi="10.5555/journal",
        arxiv_id="2401.99999",
        venue="Synthetic Journal",
        pub_date="2025-03-01",
        year=2025,
    )
    key = run(history, source_settings, [preprint, journal])[0].work_key
    first = history.get_work_state(key)
    original_events = history.list_events(key)
    with history.transaction():
        history.mark_events_exported([row["event_id"] for row in original_events], "run-1")
    run(history, source_settings, [journal, preprint], "run-2", LATER)
    assert history.get_work_state(key) == first
    assert len(history.list_events(key)) == len(original_events)
    assert history.list_unexported_events() == []
    assert history.get_work(key)["last_changed"] == STAMP


def test_similar_titles_not_merged(history, source_settings):
    first = paper(title="Quantum simulation on synthetic systems Part I")
    second = paper(source_id="W9992", title="Quantum simulation on synthetic systems Part II")
    results = run(history, source_settings, [first, second])
    assert results[0].work_key != results[1].work_key
    original = "Quantum computing methods for molecular simulation"
    similar = "Quantum computing methods for molecular simulation review study"
    score = token_sort_ratio(normalize_title(original), normalize_title(similar))
    assert 88 <= score < 89
    third = paper(source_id="W9993", title=original)
    fourth = paper(source_id="W9994", title=similar)
    results = run(history, source_settings, [third, fourth], "run-2")
    assert results[0].work_key != results[1].work_key
    assert any(
        row["kind"] == EventKind.POSSIBLE_DUPLICATE
        for row in history.list_events(results[1].work_key)
    )


def test_missing_doi_ok(history, source_settings):
    work = paper(title="Record without any external identifiers")
    key = run(history, source_settings, [work])[0].work_key
    assert history.get_work_state(key)["doi"] is None
    run(history, source_settings, [work], "run-2")
    assert len(history.list_works()) == 1
    assert sum(row["kind"] == EventKind.NEW for row in history.list_events(key)) == 1


@pytest.mark.parametrize("guard", ["authors", "numbers", "year"])
def test_fuzzy_requires_every_guard(history, source_settings, guard):
    first = paper(title="Synthetic quantum simulation using 20 qubits")
    changes = {"source_id": "W9992"}
    if guard == "authors":
        changes["authors"] = [Author(name="Unrelated Writer", orcid=None, institution_ids=[])]
    elif guard == "numbers":
        changes["title"] = "Synthetic quantum simulation using 21 qubits"
    else:
        changes.update(year=2028, pub_date="2028-01-01", type=WorkType.ARTICLE)
    results = run(history, source_settings, [first, paper(**changes)])
    assert results[0].work_key != results[1].work_key


def test_fuzzy_two_shared_surnames_allow_different_first_author(history, source_settings):
    first = paper()
    second = paper(source_id="W9992", authors=list(reversed(first.authors)))
    results = run(history, source_settings, [first, second])
    assert results[0].work_key == results[1].work_key
    assert results[1].method == "fuzzy"


def test_fuzzy_journal_year_window_is_directional(history, source_settings):
    journal = paper(type=WorkType.ARTICLE, year=2025, pub_date="2025-01-01")
    preprint = paper(source_id="W9992", year=2022, pub_date="2022-01-01")
    results = run(history, source_settings, [journal, preprint])
    assert results[0].work_key == results[1].work_key


def test_link_from_journal_reference_doi(history, source_settings):
    first = paper(doi="10.5555/journal", type=WorkType.ARTICLE)
    second = paper(
        source_id="W9992",
        title="Completely changed title",
        journal_ref="See https://doi.org/10.5555/JOURNAL.",
    )
    results = run(history, source_settings, [first, second])
    assert results[0].work_key == results[1].work_key
    assert results[1].method == "link"


def test_conflicting_identifiers_are_flagged_never_merged(history, source_settings):
    first = paper(doi="10.5555/first", title="Paper about A")
    second = paper(
        source_id="W9992", arxiv_id="2401.99999", title="Different work about B", authors=[]
    )
    run(history, source_settings, [first, second])
    conflict = paper(source_id="W9993", doi="10.5555/first", arxiv_id="2401.99999")
    result = run(history, source_settings, [conflict], "run-2")[0]
    assert result.method == "conflict" and len(result.possible_duplicates) == 2
    assert len(history.list_works()) == 3
    count = len(history.list_events(result.work_key))
    again = run(history, source_settings, [conflict], "run-3")[0]
    assert again.work_key == result.work_key and len(history.list_works()) == 3
    assert len(history.list_events(result.work_key)) == count


def test_retraction_produces_a_material_change(history, source_settings):
    work = paper(type=WorkType.ARTICLE, doi="10.5555/article")
    key = run(history, source_settings, [work])[0].work_key
    run(history, source_settings, [replace(work, is_retracted=True)], "run-2")
    assert history.get_work_state(key)["is_retracted"]
    assert any(row["kind"] == EventKind.RETRACTED for row in history.list_events(key))


def test_partial_preprint_cannot_erase_journal_metadata(history, source_settings):
    work = paper(
        source=Source.ARXIV,
        source_id="2401.99999",
        arxiv_id="2401.99999",
        doi="10.5555/journal",
        journal_ref="Synthetic Journal",
    )
    key = run(history, source_settings, [work])[0].work_key
    run(history, source_settings, [replace(work, doi=None, journal_ref=None)], "run-2")
    state = history.get_work_state(key)
    assert state["doi"] == "10.5555/journal" and state["status"] == "published"
    assert state["journal_ref"] == "Synthetic Journal"


def test_batch_failure_rolls_back_matching_snapshots_and_events(history, source_settings, tmp_path):
    run(history, source_settings, [paper()])
    with history.transaction():
        history.record_run("run-2", started_at=LATER, finished_at=None, status="running", counts={})
    path = tmp_path / "history.db"
    before = path.read_bytes()

    def broken_input():
        yield paper(source_id="W9992", doi="10.5555/new", type=WorkType.ARTICLE)
        raise RuntimeError("interrupted batch")

    with pytest.raises(RuntimeError, match="interrupted batch"):
        resolve_and_store(
            broken_input(), history, source_settings, run_id="run-2", created_at=LATER
        )
    assert path.read_bytes() == before


def test_raw_and_normalized_snapshots_are_stored_separately(history, source_settings):
    work = paper()
    with history.transaction():
        history.record_run("run-1", started_at=STAMP, finished_at=None, status="running", counts={})
    raw = {"id": "https://openalex.org/W9991", "synthetic": True}
    result = resolve_and_store(
        [work],
        history,
        source_settings,
        run_id="run-1",
        created_at=STAMP,
        raw_records={(Source.OPENALEX, "W9991"): raw},
    )[0]
    record = history.list_source_records(result.work_key)[0]
    assert json.loads(record["raw_json"]) == raw
    assert json.loads(record["normalized_json"])["title"] == work.title


with (Path(__file__).parent / "fixtures/golden_pairs.csv").open() as stream:
    GOLDEN_PAIRS = list(csv.DictReader(stream))


@pytest.mark.parametrize("pair", GOLDEN_PAIRS, ids=lambda pair: pair["arxiv_id"])
def test_public_golden_pairs_link_without_live_api_claims(history, source_settings, pair):
    preprint = paper(
        source=Source.ARXIV,
        source_id=pair["arxiv_id"],
        arxiv_id=pair["arxiv_id"],
        doi=pair["doi"],
        title="Synthetic preprint title",
    )
    journal = paper(
        source_id="W9992",
        doi=pair["doi"],
        type=WorkType.ARTICLE,
        title=pair["published_title"],
        venue=pair["journal"],
    )
    results = run(history, source_settings, [preprint, journal])
    assert results[0].work_key == results[1].work_key
    state = history.get_work_state(results[0].work_key)
    assert state["arxiv_id"] == pair["arxiv_id"] and state["doi"] == pair["doi"]


def test_decimal_numbers_are_compared_before_punctuation_is_removed(history, source_settings):
    first = paper(title="Quantum simulation at resolution 1.2")
    second = paper(source_id="W9992", title="Quantum simulation at resolution 2.1")
    assert token_sort_ratio(first.title_norm, second.title_norm) == 100
    results = run(history, source_settings, [first, second])
    assert results[0].work_key != results[1].work_key


def test_other_published_work_type_is_not_classified_as_preprint(history, source_settings):
    result = run(history, source_settings, [paper(type=WorkType.OTHER)])[0]
    assert history.get_work_state(result.work_key)["status"] == "published"


def test_preprint_doi_does_not_masquerade_as_journal_publication(history, source_settings):
    work = paper(
        source=Source.ARXIV,
        source_id="2401.99999",
        arxiv_id="2401.99999",
        doi="10.48550/arXiv.2401.99999",
    )
    key = run(history, source_settings, [work])[0].work_key
    assert history.get_work_state(key)["status"] == "preprint"
    assert not any(event["kind"] == EventKind.LINKED_PREPRINT for event in history.list_events(key))


def test_ambiguous_automatic_matches_require_review(history, source_settings):
    first = paper()
    second = paper(source_id="W9992")
    # Simulate two identities already present in imported history.
    with history.transaction():
        for key, work in [("legacy-a", first), ("legacy-b", second)]:
            history.upsert_work(
                key,
                title=work.title,
                year=work.year,
                venue=None,
                type=work.type,
                status="preprint",
                ibm_confirmed=False,
                best_confidence=work.confidence,
                first_seen=STAMP,
                last_changed=STAMP,
            )
            history.upsert_source_record(
                work.source,
                work.source_id,
                key,
                lane=work.lane,
                fetched_at=STAMP,
                raw={},
                raw_hash=work.raw_hash,
                normalized=asdict(work),
            )
    result = run(history, source_settings, [paper(source_id="W9993")])[0]
    assert result.is_new
    assert result.possible_duplicates == ("legacy-a", "legacy-b")
    assert len(history.list_works()) == 3


def test_linked_journal_arriving_first_keeps_both_identifiers(history, source_settings):
    journal = paper(
        source_id="W9992",
        doi="10.5555/journal",
        extra_dois=["10.5555/preprint"],
        type=WorkType.ARTICLE,
    )
    preprint = paper(
        source=Source.ARXIV, source_id="2401.99999", arxiv_id="2401.99999", doi="10.5555/preprint"
    )
    results = run(history, source_settings, [journal, preprint])
    assert results[0].work_key == results[1].work_key
    state = history.get_work_state(results[0].work_key)
    assert state["doi"] == "10.5555/journal" and state["arxiv_id"] == "2401.99999"


def test_pair_confirmation_survives_same_source_found_in_review_lane(history, source_settings):
    confirmed = paper(ibm_confirmed=True)
    review = replace(
        confirmed, lane=Lane.CLINIC_QUANTUM, ibm_confirmed=False, confidence=Confidence.REVIEW
    )
    key = run(history, source_settings, [confirmed, review])[0].work_key
    state = history.get_work_state(key)
    assert state["ibm_confirmed"] is True and state["confidence"] == "review"


def test_raw_snapshot_is_retained_when_unchanged_record_is_reused(history, source_settings):
    work = paper()
    with history.transaction():
        history.record_run("run-1", started_at=STAMP, finished_at=None, status="running", counts={})
    raw = {"id": "https://openalex.org/W9991", "public": "synthetic original response"}
    key = resolve_and_store(
        [work],
        history,
        source_settings,
        run_id="run-1",
        created_at=STAMP,
        raw_records={(Source.OPENALEX, "W9991"): raw},
    )[0].work_key
    run(history, source_settings, [work], "run-2")
    assert json.loads(history.list_source_records(key)[0]["raw_json"]) == raw


def test_adapter_records_reconcile_with_one_paper_identity(
    history,
    source_settings,
    api_fixture,
    monkeypatch,
):
    from datetime import datetime
    from types import SimpleNamespace

    import arxiv

    from pubmon.sources import arxiv_src, openalex

    page = api_fixture("openalex.json")["results"][:1]
    monkeypatch.setattr(openalex, "_pages", lambda *args: page)
    journal = openalex.fetch_pair(source_settings)[0]
    raw = api_fixture("arxiv.json")[0]
    item = arxiv.Result(
        entry_id=raw["entry_id"],
        published=datetime.fromisoformat(raw["published"]),
        updated=datetime.fromisoformat(raw["updated"]),
        title=raw["title"],
        doi=raw["doi"],
        journal_ref=raw["journal_ref"],
    )
    preprint = arxiv_src.recheck(
        source_settings,
        ["2401.99999"],
        watchlist=[],
        client=SimpleNamespace(results=lambda _: iter([item])),
    )[0]
    results = run(history, source_settings, [journal, preprint])
    assert results[0].work_key == results[1].work_key
    assert len(history.list_works()) == 1
    assert history.get_work_state(results[0].work_key)["doi"] == "10.5555/synthetic-1"
