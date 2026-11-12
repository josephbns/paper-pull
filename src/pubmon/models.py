"""Shared vocabulary for normalized source records."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TypedDict


class Source(StrEnum):
    """Public metadata providers."""

    OPENALEX = "openalex"
    ARXIV = "arxiv"
    CROSSREF = "crossref"


class Lane(StrEnum):
    """Discovery routes, independent of the provider."""

    PAIR = "pair"
    CLINIC_QUANTUM = "clinic_quantum"
    ARXIV_FEED = "arxiv_feed"
    RECHECK = "recheck"


class WorkType(StrEnum):
    """Normalized publication types."""

    PREPRINT = "preprint"
    ARTICLE = "article"
    PROCEEDINGS = "proceedings"
    OTHER = "other"


class Confidence(StrEnum):
    """Evidence strength; uncertain records require human review."""

    HIGH = "high"
    REVIEW = "review"
    UNCERTAIN = "uncertain"


class WorkStatus(StrEnum):
    """Publication states retained in history."""

    PREPRINT = "preprint"
    PUBLISHED = "published"


class EventKind(StrEnum):
    """Individual audit events, later grouped by paper for export."""

    NEW = "NEW"
    UPDATED = "UPDATED"
    LINKED_PREPRINT = "LINKED_PREPRINT"
    POSSIBLE_DUPLICATE = "POSSIBLE_DUPLICATE"
    CORRECTION = "CORRECTION"
    RETRACTED = "RETRACTED"


class Author(TypedDict):
    """Source author with optional public identity information."""

    name: str
    orcid: str | None
    institution_ids: list[str]


@dataclass
class Work:
    """One source record; multiple records may describe the same real paper."""

    source: Source
    source_id: str
    lane: Lane
    title: str
    title_norm: str
    pub_date: str
    year: int
    type: WorkType
    raw_hash: str
    venue: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    pmid: str | None = None
    openalex_id: str | None = None
    extra_dois: list[str] = field(default_factory=list)
    journal_ref: str | None = None
    authors: list[Author] = field(default_factory=list)
    ibm_confirmed: bool = False
    matched_names: list[str] = field(default_factory=list)
    confidence: Confidence = Confidence.UNCERTAIN
    is_retracted: bool = False
