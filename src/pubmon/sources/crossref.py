"""Crossref DOI enrichment; transient HTTP errors are retried with bounded backoff."""

from datetime import date

from habanero import Crossref
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from pubmon.config import Settings
from pubmon.models import WorkType
from pubmon.normalize import normalize_ids
from pubmon.sources.common import FetchReport, Raw, http_status, lane_guard, raw_hash


def _retryable(error: Exception) -> bool:
    status = http_status(error)
    return status == 429 or (status is not None and 500 <= status < 600)


@retry(
    retry=retry_if_exception(_retryable),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=0.5, max=8),
    reraise=True,
)
def _request(client: Crossref, doi: str) -> Raw:
    return client.works(ids=doi)


def enrich(
    doi: str | None,
    settings: Settings,
    *,
    report: FetchReport | None = None,
    client: Crossref | None = None,
) -> Raw:
    """Return publication fields, preprint links and update notices for one DOI."""
    if not doi or not doi.strip():
        return {}  # DOI-less papers are normal; no request or credentials are needed.
    if not settings.email:
        raise ValueError("Missing environment variable: PUBMON_EMAIL")
    report = report if report is not None else FetchReport()
    with lane_guard("crossref", report):
        canonical = normalize_ids(doi=doi)["doi"]
        try:
            response = _request(client or Crossref(mailto=settings.email), canonical)
        except Exception as exc:
            # A valid DOI can belong to another registry or not yet be indexed here.
            # Keep its source metadata; an absent optional enrichment is not an outage.
            if http_status(exc) != 404:
                raise
            report.skipped["not_found"] += 1
            return {}
        raw = response["message"]
        report.raw_records.append(raw)
        relations = _relations(raw)
        return {
            "doi": canonical,
            "venue": next(iter(raw.get("container-title", [])), None),
            "pub_date": _publication_date(raw),
            "type": _work_type(raw.get("type", "")),
            "relations": relations,
            "extra_dois": sorted(
                {item for ids in relations.values() for item in ids if item != canonical}
            ),
            "update_to": raw.get("update-to", []),
            "is_retracted": any(
                item.get("type") == "retraction" for item in raw.get("update-to", [])
            ),
            "raw_hash": raw_hash(raw),
        }


def _relations(raw: Raw) -> dict[str, list[str]]:
    relations = {}
    for kind in ("has-preprint", "is-preprint-of"):
        ids = [
            normalize_ids(doi=item["id"])["doi"]
            for item in raw.get("relation", {}).get(kind, [])
            if item.get("id-type") == "doi"
        ]
        if ids:
            relations[kind] = ids
    return relations


def _publication_date(raw: Raw) -> str | None:
    dates = raw.get("published", {}).get("date-parts", [])
    # A year or month alone is not an exact date; do not invent missing components.
    if dates and len(dates[0]) == 3:
        return date(*dates[0]).isoformat()
    return None


def _work_type(kind: str) -> WorkType:
    return {
        "posted-content": WorkType.PREPRINT,
        "journal-article": WorkType.ARTICLE,
        "proceedings-article": WorkType.PROCEEDINGS,
    }.get(kind, WorkType.OTHER)
