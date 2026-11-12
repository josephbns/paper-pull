"""Resolve public source records to stable papers and write their change history."""

import json
import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, replace
from datetime import date
from uuid import uuid4

from rapidfuzz.fuzz import token_sort_ratio

from pubmon.config import Settings
from pubmon.diff import canonical_state, is_published, material_changes
from pubmon.models import Confidence, EventKind, Source, Work, WorkStatus, WorkType
from pubmon.normalize import normalize_ids, normalize_title, surname
from pubmon.store import IdentifierConflict, Row, Store


@dataclass(frozen=True)
class MatchResult:
    """A chosen identity plus any unresolved alternatives requiring human review."""

    work_key: str
    method: str
    is_new: bool = False
    possible_duplicates: tuple[str, ...] = ()


def _normalized(work: Work) -> Work:
    ids = normalize_ids(
        doi=work.doi, arxiv_id=work.arxiv_id, pmid=work.pmid, openalex_id=work.openalex_id
    )
    source_id = work.source_id
    if work.source == Source.ARXIV:
        source_id = normalize_ids(arxiv_id=source_id)["arxiv_id"]
    elif work.source == Source.OPENALEX:
        source_id = normalize_ids(openalex_id=source_id)["openalex_id"]
    else:
        source_id = normalize_ids(doi=source_id)["doi"]
    return replace(work, source_id=source_id, title_norm=normalize_title(work.title), **ids)


def _primary_ids(work: Work) -> dict[str, str | None]:
    return {
        "doi": work.doi,
        "arxiv": work.arxiv_id,
        "pmid": work.pmid,
        "openalex": work.openalex_id,
    }


def _doi_clues(work: Work) -> list[str]:
    clues = set(work.extra_dois)
    for value in re.findall(r"10\.\d{4,9}/[^\s<>\"']+", work.journal_ref or ""):
        value = value.rstrip(".,;")
        while value.endswith(")") and value.count(")") > value.count("("):
            value = value[:-1]
        clues.add(value)
    return sorted({normalize_ids(doi=value)["doi"] for value in clues if value})


def _known_keys(store: Store, ids: Mapping[str, str | None]) -> set[str]:
    try:
        found = store.find_work_key(ids)
        return {found} if found else set()
    except IdentifierConflict as conflict:
        return set(conflict.work_keys)


def resolve(work: Work, store: Store, settings: Settings) -> MatchResult:
    """Choose shared identity, link clue, guarded fuzzy match, or a new UUID in order."""
    work = _normalized(work)
    primary = _known_keys(store, _primary_ids(work))
    source = store.get_source_record(work.source, work.source_id)
    if source:
        primary.add(source["work_key"])
    clues = set()
    for doi in _doi_clues(work):
        clues.update(_known_keys(store, {"doi": doi}))
    if len(primary) > 1:
        key = source["work_key"] if source else str(uuid4())
        return MatchResult(key, "conflict", source is None, tuple(sorted(primary - {key})))
    if primary:
        key = next(iter(primary))
        return MatchResult(key, "id", False, tuple(sorted(clues - {key})))
    if len(clues) == 1:
        return MatchResult(next(iter(clues)), "link")
    if clues:
        return MatchResult(str(uuid4()), "conflict", True, tuple(sorted(clues)))
    return _fuzzy(work, store, settings)


def _versions(store: Store, key: str) -> list[Work]:
    return [
        Work(**json.loads(row["normalized_json"]))
        for row in store.list_source_records(key)
        if row["normalized_json"]
    ]


def _numbers(title: str) -> set[str]:
    # Roman part labels must also differ: the digit guard alone misses Part I / II.
    title = unicodedata.normalize("NFKD", title).casefold()
    numbers = set(re.findall(r"[+-]?\d+(?:\.\d+)?", title))
    numbers.update("part:" + label for label in re.findall(r"\bpart\s+([ivxlcdm]+)\b", title))
    return numbers


def _author_guard(first: Work, second: Work) -> bool:
    names1 = [surname(author["name"]) for author in first.authors]
    names2 = [surname(author["name"]) for author in second.authors]
    same_first = bool(names1 and names2 and names1[0] and names1[0] == names2[0])
    return same_first or len((set(names1) & set(names2)) - {""}) >= 2


def _year_guard(first: Work, second: Work, window: tuple[int, int]) -> bool:
    if is_published(first) != is_published(second):
        journal, preprint = (first, second) if is_published(first) else (second, first)
        difference = journal.year - preprint.year
    else:
        difference = abs(first.year - second.year)
    return window[0] <= difference <= window[1]


def _fuzzy(work: Work, store: Store, settings: Settings) -> MatchResult:
    automatic, review = set(), set()
    for row in store.list_works():
        for candidate in _versions(store, row["work_key"]):
            if (
                not work.title_norm
                or not candidate.title_norm
                or abs(work.year - candidate.year) > 4
            ):
                continue
            score = token_sort_ratio(work.title_norm, candidate.title_norm)
            if score < settings.review:
                continue
            review.add(row["work_key"])
            if (
                score >= settings.auto_link
                and _author_guard(work, candidate)
                and _year_guard(work, candidate, settings.year_window)
                and _numbers(work.title) == _numbers(candidate.title)
            ):
                automatic.add(row["work_key"])
    if len(automatic) == 1:
        return MatchResult(next(iter(automatic)), "fuzzy")
    return MatchResult(str(uuid4()), "new", True, tuple(sorted(automatic or review)))


def _write_summary(store: Store, key: str, state: Row, created_at: str, *, changed: bool) -> None:
    existing = store.get_work(key)
    store.upsert_work(
        key,
        title=state["title"],
        year=state["year"],
        venue=state.get("venue"),
        type=WorkType(state["type"]),
        status=WorkStatus(state["status"]),
        ibm_confirmed=state["ibm_confirmed"],
        best_confidence=Confidence(state["confidence"]),
        first_seen=created_at,
        last_changed=created_at if changed or not existing else existing["last_changed"],
    )
    store.save_work_state(key, state)


def _attach_ids(store: Store, key: str, work: Work) -> None:
    pairs = [(scheme, value) for scheme, value in _primary_ids(work).items() if value]
    pairs.extend(("doi", value) for value in _doi_clues(work))
    for scheme, value in pairs:
        # Conflicting identifiers stay with their original owner; the review event records it.
        owner = store.find_work_key({scheme: value})
        if owner is None or owner == key:
            store.upsert_identifier(scheme, value, key)


def _review_event(
    store: Store, key: str, targets: tuple[str, ...], run_id: str, stamp: str
) -> None:
    if not targets:
        return
    value = json.dumps(targets)
    if any(
        event["kind"] == EventKind.POSSIBLE_DUPLICATE and event["new"] == value
        for event in store.list_events(key)
    ):
        return
    store.add_event(
        run_id,
        key,
        EventKind.POSSIBLE_DUPLICATE,
        field="possible_duplicate_of",
        new=value,
        created_at=stamp,
    )


def _change_events(
    store: Store, key: str, before: Row | None, after: Row, run_id: str, stamp: str
) -> bool:
    if before is None:
        store.add_event(run_id, key, EventKind.NEW, created_at=stamp)
        return True
    changes = material_changes(before, after)
    for change in changes:
        store.add_event(
            run_id,
            key,
            EventKind.UPDATED,
            field=change.field,
            old=_event_value(change.old),
            new=_event_value(change.new),
            created_at=stamp,
        )
    if not before.get("is_retracted") and after["is_retracted"]:
        store.add_event(run_id, key, EventKind.RETRACTED, created_at=stamp)
    return bool(changes)


def _event_value(value: object) -> str | None:
    if value is None or isinstance(value, str):
        return value
    return json.dumps(value)


def _link_event(store: Store, key: str, versions: list[Work], run_id: str, stamp: str) -> None:
    has_preprint = any(work.type == WorkType.PREPRINT for work in versions)
    has_journal = any(is_published(work) for work in versions)
    linked = any(event["kind"] == EventKind.LINKED_PREPRINT for event in store.list_events(key))
    if has_preprint and has_journal and not linked:
        store.add_event(run_id, key, EventKind.LINKED_PREPRINT, created_at=stamp)


def _source_raw(work: Work, store: Store, supplied: Mapping | None) -> Row:
    identity = (work.source, work.source_id)
    if supplied is not None and identity in supplied:
        return supplied[identity]
    prior = store.get_source_record(*identity)
    if prior and prior["raw_hash"] == work.raw_hash:
        return json.loads(prior["raw_json"])
    # Pure matching callers may have normalized input only; label it explicitly.
    return {"_pubmon_normalized_only": asdict(work)}


def resolve_and_store(
    works: Iterable[Work],
    store: Store,
    settings: Settings,
    *,
    run_id: str,
    created_at: str,
    raw_records: Mapping[tuple[Source, str], Row] | None = None,
) -> list[MatchResult]:
    """Resolve a complete batch and write snapshots and events in one transaction."""
    results, before, duplicates = [], {}, {}
    with store.transaction():
        for incoming in works:
            work = _normalized(incoming)
            date.fromisoformat(work.pub_date)
            result = resolve(work, store, settings)
            key = result.work_key
            if key not in before:
                before[key] = store.get_work_state(key)
                if before[key] is None and store.get_work(key):
                    before[key] = store.get_work(key)  # Preserve legacy identity, avoiding NEW.
            if result.is_new:
                _write_summary(store, key, canonical_state([work]), created_at, changed=True)
            _attach_ids(store, key, work)
            store.upsert_source_record(
                work.source,
                work.source_id,
                key,
                lane=work.lane,
                fetched_at=created_at,
                raw=_source_raw(work, store, raw_records),
                raw_hash=work.raw_hash,
                normalized=asdict(work),
            )
            duplicates.setdefault(key, set()).update(result.possible_duplicates)
            results.append(result)
        for key, previous in before.items():
            versions = _versions(store, key)
            state = canonical_state(versions, previous or store.get_work_state(key))
            changed = _change_events(store, key, previous, state, run_id, created_at)
            _write_summary(store, key, state, created_at, changed=changed)
            _link_event(store, key, versions, run_id, created_at)
            _review_event(store, key, tuple(sorted(duplicates[key])), run_id, created_at)
    return results
