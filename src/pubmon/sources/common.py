"""Shared adapter results and safe errors; this module makes no network requests."""

import hashlib
import json
import logging
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pubmon.models import Lane

Raw = dict[str, Any]
logger = logging.getLogger(__name__)


class LaneFailed(RuntimeError):
    """A discovery lane failed; callers must not treat this as an empty result."""

    def __init__(self, lane: str, reason: str) -> None:
        self.lane = lane
        super().__init__(f"{lane}: {reason}")


@dataclass
class FetchReport:
    """Per-call public responses and counts for later pipeline logging and archives."""

    run_id: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    raw_records: list[Raw] = field(default_factory=list)
    skipped: Counter[str] = field(default_factory=Counter)
    notices: list[Raw] = field(default_factory=list)


def raw_hash(raw: Raw) -> str:
    """Hash stable JSON, ignoring differences in dictionary key order."""
    value = json.dumps(raw, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def http_status(error: Exception) -> int | None:
    """Extract an HTTP code across requests, arxiv.py and Habanero transports."""
    response = getattr(error, "response", None)
    return (
        getattr(response, "status_code", None)
        or getattr(error, "status_code", None)
        or getattr(error, "status", None)
    )


@contextmanager
def lane_guard(lane: Lane | str, report: FetchReport) -> Iterator[None]:
    """Convert failures to safe lane errors without exposing request URLs or secrets."""
    try:
        yield
    except LaneFailed:
        raise
    except Exception as exc:  # noqa: BLE001 - sanitize third-party errors at the adapter boundary
        status = http_status(exc)
        reason = f"HTTP {status}" if status else type(exc).__name__
        # Library exceptions can include API keys in their URLs; never log str(exc).
        logger.warning("[run_id=%s] %s failed: %s", report.run_id, lane, reason)
        raise LaneFailed(lane, reason) from None


def entity_id(value: str) -> str:
    """Strip the URL wrapper from an OpenAlex entity identifier."""
    return value.rstrip("/").rsplit("/", 1)[-1]
