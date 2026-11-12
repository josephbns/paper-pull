"""Load public settings and private runtime credentials without network access."""

import os
import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from dotenv import dotenv_values


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
        return self.query_file.read_text(encoding="utf-8")


def _strings(section: dict, name: str) -> tuple[str, ...]:
    value = section[name]
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{name} must be a list of strings")
    return tuple(value)


def _validate(raw: dict) -> None:
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
    """Load the local TOML, falling back to the example only when it is absent."""
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
        cc_institution_ids=_strings(openalex, "cc_institution_ids"),
        quantum_terms=_strings(openalex, "quantum_terms"),
        skip_types=_strings(openalex, "skip_types"),
        query_file=root / arxiv["query_file"],
        watchlist_file=root / arxiv.get("watchlist_file", "config/watchlist.csv"),
        common_names=_strings(arxiv, "common_names"),
        auto_link=matching["auto_link"],
        review=matching["review"],
        year_window=tuple(matching["year_window"]),
        master_path=root / master if master else None,
        openalex_api_key=key.strip() if key else None,
        email=email.strip() if email else None,
    )
