"""Pure material-change detection and conservative selection of a paper's state."""

from dataclasses import asdict, dataclass
from typing import Any

from pubmon.models import Confidence, Source, Work, WorkStatus, WorkType

MATERIAL_FIELDS = ("doi", "venue", "pub_date", "type", "status", "is_retracted", "journal_ref")
CONFIDENCE_ORDER = {Confidence.UNCERTAIN: 0, Confidence.REVIEW: 1, Confidence.HIGH: 2}


@dataclass(frozen=True)
class Change:
    """One material field's old and new values for an audit event."""

    field: str
    old: Any
    new: Any


def material_changes(old: dict, new: dict) -> list[Change]:
    """Compare only material fields in a fixed order; inputs are not modified."""
    return [
        Change(name, old.get(name), new.get(name))
        for name in MATERIAL_FIELDS
        if old.get(name) != new.get(name)
    ]


def is_published(work: Work) -> bool:
    """Recognize articles and journal DOI metadata attached to an arXiv preprint."""
    if work.type != WorkType.PREPRINT:
        return True
    return (
        work.source == Source.ARXIV
        and bool(work.doi)
        and not work.doi.lower().startswith("10.48550/arxiv.")
    )


def _rank(work: Work) -> tuple:
    authority = {Source.ARXIV: 0, Source.OPENALEX: 1, Source.CROSSREF: 2}
    return is_published(work), authority[work.source], work.pub_date, work.source_id


def canonical_state(versions: list[Work], previous: dict | None = None) -> dict:
    """Prefer published metadata and retain known values when sources omit them."""
    if not versions:
        raise ValueError("A paper needs at least one normalized source version")
    ranked = sorted(versions, key=_rank, reverse=True)
    # Existing published state acts as a floor when a source drops journal metadata.
    published = any(is_published(work) for work in ranked)
    if previous and previous.get("status") == WorkStatus.PUBLISHED and not published:
        state = dict(previous)
    else:
        state = asdict(ranked[0])
        state["status"] = WorkStatus.PUBLISHED if published else WorkStatus.PREPRINT
        if published and state["type"] == WorkType.PREPRINT:
            state["type"] = WorkType.ARTICLE
        for name in ("doi", "arxiv_id", "pmid", "openalex_id", "venue", "journal_ref", "authors"):
            state[name] = next(
                (getattr(work, name) for work in ranked if getattr(work, name)),
                (previous or {}).get(name, [] if name == "authors" else None),
            )
    state["ibm_confirmed"] = any(work.ibm_confirmed for work in versions) or bool(
        (previous or {}).get("ibm_confirmed")
    )
    state["confidence"] = min((work.confidence for work in versions), key=CONFIDENCE_ORDER.get)
    state["is_retracted"] = any(work.is_retracted for work in versions) or bool(
        (previous or {}).get("is_retracted")
    )
    return state
