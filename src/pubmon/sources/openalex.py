"""OpenAlex discovery, completeness checks, and institution lookup through PyAlex."""

from datetime import date
from itertools import product
from urllib.parse import urlsplit

import pyalex
from pyalex import Institutions, Works

from pubmon.config import Settings
from pubmon.models import Author, Confidence, EventKind, Lane, Source, Work, WorkType
from pubmon.normalize import normalize_ids, normalize_title
from pubmon.sources.common import FetchReport, LaneFailed, Raw, entity_id, lane_guard, raw_hash


def _configure(settings: Settings) -> None:
    settings.require_network_credentials()
    pyalex.config.api_key = settings.openalex_api_key
    pyalex.config.email = settings.email
    pyalex.config.max_retries = 3
    pyalex.config.retry_backoff_factor = 0.5
    pyalex.config.retry_http_codes = [429, *range(500, 600)]


def _pages(query: Works, lane: Lane) -> list[Raw]:
    records: dict[str, Raw] = {}
    expected = None
    seen_cursors = {"*"}
    for page in query.paginate(per_page=200, n_max=None):
        if expected is None:
            expected = page.meta["count"]
        for item in page:
            records[item["id"]] = item
        cursor = page.meta.get("next_cursor")
        if cursor is not None:
            if cursor in seen_cursors:
                raise LaneFailed(lane, "Pagination repeated a cursor")
            seen_cursors.add(cursor)
    if expected is None or len(records) != expected:
        raise LaneFailed(lane, "Incomplete pagination; fetched count differs from meta.count")
    return list(records.values())


def fetch_pair(settings: Settings, *, report: FetchReport | None = None) -> list[Work]:
    """Fetch the union of all IBM × Clinic institution-pair queries."""
    _configure(settings)
    report = report if report is not None else FetchReport()
    with lane_guard(Lane.PAIR, report):
        if not settings.ibm_institution_ids or not settings.cc_institution_ids:
            raise LaneFailed(Lane.PAIR, "Both institution lists must be configured")
        records = {}
        for ibm, clinic in product(settings.ibm_institution_ids, settings.cc_institution_ids):
            query = Works().filter(authorships={"institutions": {"lineage": [ibm, clinic]}})
            query = query.filter(from_publication_date=settings.start_date)
            records.update((item["id"], item) for item in _pages(query, Lane.PAIR))
        return _papers(list(records.values()), settings, Lane.PAIR, report)


def fetch_clinic_quantum(
    settings: Settings,
    *,
    report: FetchReport | None = None,
) -> list[Work]:
    """Fetch Clinic papers using title/abstract terms rather than full-text search."""
    _configure(settings)
    report = report if report is not None else FetchReport()
    with lane_guard(Lane.CLINIC_QUANTUM, report):
        if not settings.cc_institution_ids or not settings.quantum_terms:
            raise LaneFailed(Lane.CLINIC_QUANTUM, "Clinic institutions and terms are required")
        records = {}
        for clinic in settings.cc_institution_ids:
            query = Works().filter(authorships={"institutions": {"lineage": clinic}})
            # TODO(owner): verify this filter live before the first collection run.
            query = query.search_filter(title_and_abstract=" OR ".join(settings.quantum_terms))
            query = query.filter(from_publication_date=settings.start_date)
            records.update((item["id"], item) for item in _pages(query, Lane.CLINIC_QUANTUM))
        return _papers(list(records.values()), settings, Lane.CLINIC_QUANTUM, report)


def _papers(records: list[Raw], settings: Settings, lane: Lane, report: FetchReport) -> list[Work]:
    report.raw_records.extend(records)
    works = []
    for raw in records:
        if date.fromisoformat(raw["publication_date"]) < date.fromisoformat(settings.start_date):
            report.skipped["before_start"] += 1
            continue
        kind = raw.get("type", "other")
        if kind in {"erratum", "retraction"}:
            event = EventKind.CORRECTION if kind == "erratum" else EventKind.RETRACTED
            report.notices.append(
                {"doi": normalize_ids(doi=raw.get("doi"))["doi"], "kind": event, "raw": raw}
            )
            continue  # The pipeline links notices to originals using Crossref update-to.
        if kind in settings.skip_types:
            report.skipped[kind] += 1
            continue
        works.append(_to_work(raw, settings, lane))
    return works


def _authors(raw: Raw) -> list[Author]:
    authors = []
    for authorship in raw.get("authorships", []):
        author = authorship["author"]
        authors.append(
            Author(
                name=author["display_name"],
                orcid=author.get("orcid"),
                institution_ids=[
                    entity_id(item["id"]) for item in authorship.get("institutions", [])
                ],
            )
        )
    return authors


def _has_ibm(raw: Raw, settings: Settings) -> bool:
    for authorship in raw.get("authorships", []):
        for institution in authorship.get("institutions", []):
            lineage = [institution["id"], *institution.get("lineage", [])]
            if set(map(entity_id, lineage)) & set(settings.ibm_institution_ids):
                return True
    return False


def _location_ids(raw: Raw) -> tuple[list[str], str | None]:
    dois, arxiv_id = set(), None
    for location in raw.get("locations", []):
        for key in ("landing_page_url", "pdf_url"):
            url = location.get(key) or ""
            host = urlsplit(url).hostname
            if host in {"doi.org", "dx.doi.org"}:
                dois.add(normalize_ids(doi=url)["doi"])
            elif host in {"arxiv.org", "www.arxiv.org"}:
                arxiv_id = normalize_ids(arxiv_id=url.removesuffix(".pdf"))["arxiv_id"]
    return sorted(dois), arxiv_id


def _to_work(raw: Raw, settings: Settings, lane: Lane) -> Work:
    ids = raw.get("ids") or {}
    extra, arxiv_id = _location_ids(raw)
    title = raw.get("title") or raw.get("display_name") or ""
    published = raw["publication_date"]
    kind = raw.get("type")
    work_type = {
        "article": WorkType.ARTICLE,
        "review": WorkType.ARTICLE,
        "letter": WorkType.ARTICLE,
        "preprint": WorkType.PREPRINT,
        "conference-paper": WorkType.PROCEEDINGS,
        "conference-abstract": WorkType.PROCEEDINGS,
    }.get(kind, WorkType.OTHER)
    confidence = Confidence.HIGH if lane == Lane.PAIR else Confidence.REVIEW
    if kind == "conference-abstract":
        confidence = Confidence.REVIEW
    location = raw.get("primary_location") or {}
    venue = (location.get("source") or {}).get("display_name")
    canonical = normalize_ids(
        doi=raw.get("doi") or ids.get("doi"),
        arxiv_id=arxiv_id,
        pmid=ids.get("pmid"),
        openalex_id=raw["id"],
    )
    return Work(
        source=Source.OPENALEX,
        source_id=canonical["openalex_id"],
        lane=lane,
        title=title,
        title_norm=normalize_title(title),
        pub_date=published,
        year=date.fromisoformat(published).year,
        type=work_type,
        venue=venue,
        extra_dois=[doi for doi in extra if doi != canonical["doi"]],
        authors=_authors(raw),
        ibm_confirmed=lane == Lane.PAIR or _has_ibm(raw, settings),
        confidence=confidence,
        is_retracted=bool(raw.get("is_retracted")),
        raw_hash=raw_hash(raw),
        **canonical,
    )


def lookup_institutions(settings: Settings, names: list[str]) -> list[Raw]:
    """Return up to 25 institution candidates per name without changing configuration."""
    _configure(settings)
    with lane_guard("institutions", FetchReport()):
        records = {}
        for name in names:
            for raw in Institutions().search(name).get(per_page=25):
                records[raw["id"]] = {
                    key: raw.get(key)
                    for key in (
                        "id",
                        "display_name",
                        "ror",
                        "country_code",
                        "works_count",
                        "lineage",
                    )
                }
        return list(records.values())
