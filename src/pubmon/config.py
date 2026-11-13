"""Load public settings and private runtime credentials without network access."""

import os
import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from dotenv import dotenv_values


@dataclass(frozen=True)
class WatchAuthor:
    """An explicitly configured public author and collaboration side."""

    name: str
    side: str
    arxiv_name: str
    orcid: str | None = None


@dataclass(frozen=True)
class Settings:
    """Immutable settings with credentials excluded from diagnostic representations."""

    project_dir: Path
    start_date: str
    arxiv_window_days: int
    ibm_institution_ids: tuple[str, ...]
    cc_institution_ids: tuple[str, ...]
    quantum_terms: tuple[str, ...]
    skip_types: tuple[str, ...]
    query_file: Path
    watchlist_file: Path
    common_names: tuple[str, ...]
    auto_link: float
    review: float
    year_window: tuple[int, int]
    master_path: Path | None
    openalex_api_key: str | None = field(repr=False)
    email: str | None = field(repr=False)
    collaboration_name: str = "IBM–Cleveland Clinic"
    partner_name: str = "Cleveland Clinic"
    partner_label: str = "CCF"
    ibm_name: str = "IBM"
    arxiv_query: str | None = field(default=None, repr=False)
    watchlist: tuple[WatchAuthor, ...] | None = field(default=None, repr=False)
    workspace_dir: Path | None = None
    # Set only by named profiles (profile.py); older settings files leave the defaults.
    profile_name: str | None = None
    topic_terms: tuple[str, ...] = ()
    topic_categories: tuple[str, ...] = ()
    broad_terms: tuple[str, ...] = ()
    hardware_terms: tuple[str, ...] = ()
    backup_names: tuple[str, ...] = ()

    @property
    def tag_terms(self) -> tuple[str, ...]:
        """Terms that mark a paper as on-topic; older profiles reuse the OpenAlex terms."""
        return self.topic_terms or self.quantum_terms

    @property
    def partner_institution_ids(self) -> tuple[str, ...]:
        """Expose generic partner IDs while preserving legacy Settings compatibility."""
        return self.cc_institution_ids

    def require_network_credentials(self) -> None:
        """Fail only when a caller is about to use a network command."""
        missing = []
        if not self.openalex_api_key:
            missing.append("OPENALEX_API_KEY")
        if not self.email:
            missing.append("PUBMON_EMAIL")
        if missing:
            raise ValueError("Missing environment variables: " + ", ".join(missing))

    def read_arxiv_query(self) -> str:
        """Read the owner's query verbatim, without rewriting whitespace or terms."""
        if self.arxiv_query is not None:
            return self.arxiv_query
        return self.query_file.read_text(encoding="utf-8")


def _strings(section: dict, name: str) -> tuple[str, ...]:
    value = section[name]
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{name} must be a list of strings")
    return tuple(value)


def _validate(raw: dict) -> None:
    for name in ("openalex", "arxiv", "matching", "master", "collaboration", "storage"):
        if name in raw and not isinstance(raw[name], dict):
            raise ValueError(f"{name} must be a TOML table")
    date.fromisoformat(raw["start_date"])
    days = raw["arxiv_window_days"]
    if type(days) is not int or days <= 0:
        raise ValueError("arxiv_window_days must be a positive integer")
    matching = raw["matching"]
    review, auto = matching["review"], matching["auto_link"]
    if any(type(x) not in (int, float) for x in (review, auto)):
        raise ValueError("Matching thresholds must be numbers")
    if not 0 <= review <= auto <= 100:
        raise ValueError("Matching thresholds must satisfy 0 <= review <= auto_link <= 100")
    window = matching["year_window"]
    if (
        not isinstance(window, list)
        or len(window) != 2
        or any(type(x) is not int for x in window)
        or window[0] > window[1]
    ):
        raise ValueError("year_window must contain two ordered integers")


def load_config(project_dir: Path | str = ".", *, path: Path | str | None = None) -> Settings:
    """Load the older settings TOML (tests and existing installs); new setups use profiles.

    The command line never relies on the example fallback below: `pubmon` requires a named
    profile or an existing local config/settings.toml (see cli.load_settings).
    """
    root = Path(project_dir).resolve()
    config_path = Path(path) if path is not None else Path("config/settings.toml")
    config_path = root / config_path
    if path is None and not config_path.exists():
        config_path = root / "config/settings.example.toml"
    with config_path.open("rb") as stream:
        raw = tomllib.load(stream)
    try:
        _validate(raw)
        return _settings(root, raw)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid settings in {config_path}: {exc}") from exc


def _settings(root: Path, raw: dict) -> Settings:
    openalex, arxiv, matching = raw["openalex"], raw["arxiv"], raw["matching"]
    profile = _profile(raw.get("collaboration", {}))
    query, watchlist = _inline_arxiv(arxiv)
    workspace = raw.get("storage", {}).get("workspace", ".")
    if not isinstance(workspace, str) or not workspace.strip():
        raise ValueError("storage.workspace must be a nonempty path")
    partner_key = (
        "partner_institution_ids" if "partner_institution_ids" in openalex else "cc_institution_ids"
    )
    if "partner_institution_ids" in openalex and "cc_institution_ids" in openalex:
        raise ValueError("Use partner_institution_ids or legacy cc_institution_ids, not both")
    # Process variables take precedence; reading .env does not modify os.environ.
    local_env = dotenv_values(root / ".env", interpolate=False)
    key = os.environ.get("OPENALEX_API_KEY", local_env.get("OPENALEX_API_KEY"))
    email = os.environ.get("PUBMON_EMAIL", local_env.get("PUBMON_EMAIL"))
    master = raw["master"]["path"]
    return Settings(
        project_dir=root,
        start_date=raw["start_date"],
        arxiv_window_days=raw["arxiv_window_days"],
        ibm_institution_ids=_strings(openalex, "ibm_institution_ids"),
        cc_institution_ids=_strings(openalex, partner_key),
        quantum_terms=_strings(openalex, "quantum_terms"),
        skip_types=_strings(openalex, "skip_types"),
        query_file=root / arxiv.get("query_file", "config/arxiv_query.txt"),
        watchlist_file=root / arxiv.get("watchlist_file", "config/watchlist.csv"),
        common_names=_strings(arxiv, "common_names"),
        auto_link=matching["auto_link"],
        review=matching["review"],
        year_window=tuple(matching["year_window"]),
        master_path=root / master if master else None,
        openalex_api_key=key.strip() if key else None,
        email=email.strip() if email else None,
        arxiv_query=query,
        watchlist=watchlist,
        workspace_dir=(root / workspace).resolve(),
        **profile,
    )


def _profile(raw: dict) -> dict[str, str]:
    names = {
        "name": "collaboration_name",
        "partner_name": "partner_name",
        "partner_label": "partner_label",
        "ibm_name": "ibm_name",
    }
    result = {}
    for key, field_name in names.items():
        if key in raw:
            value = raw[key]
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"collaboration.{key} must be a nonempty string")
            result[field_name] = value.strip()
    return result


def watch_author(raw: dict) -> WatchAuthor:
    """Validate one inline/legacy watchlist entry without guessing author names."""
    name = raw.get("name")
    side = raw.get("side")
    if not isinstance(name, str) or not name.strip() or side not in {"IBM", "PARTNER", "CC"}:
        raise ValueError(
            "Watchlist entries require a name and side IBM or PARTNER (legacy CC allowed)"
        )
    alias = raw.get("arxiv_name") or name
    orcid = raw.get("orcid") or None
    if (
        not isinstance(alias, str)
        or not alias.strip()
        or (orcid is not None and not isinstance(orcid, str))
    ):
        raise ValueError("Watchlist arxiv_name and orcid must be strings")
    return WatchAuthor(
        name=name.strip(),
        side="PARTNER" if side == "CC" else side,
        arxiv_name=alias.strip(),
        orcid=orcid.strip() or None if orcid else None,
    )


def _inline_arxiv(raw: dict) -> tuple[str | None, tuple[WatchAuthor, ...] | None]:
    for inline, legacy in (("query", "query_file"), ("watchlist", "watchlist_file")):
        if inline in raw and legacy in raw:
            raise ValueError(f"Use arxiv.{inline} or arxiv.{legacy}, not both")
    query = raw.get("query")
    if query is not None and (not isinstance(query, str) or not query.strip()):
        raise ValueError("arxiv.query must be a nonempty string")
    if "watchlist" not in raw:
        return query, None
    entries = raw["watchlist"]
    if not isinstance(entries, list) or any(not isinstance(item, dict) for item in entries):
        raise ValueError("arxiv.watchlist must be a list of author tables")
    return query, tuple(watch_author(entry) for entry in entries)
