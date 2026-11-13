"""Load a named QIC profile (profiles/<name>.toml) into the shared Settings object.

A profile holds only public criteria: institution IDs, published author names and keywords.
Secrets and the private master path come from environment variables or a git-ignored `.env`.
This module translates the profile into the older settings shape, so the existing checks in
`config.py` still apply (an adapter: new outside format, unchanged inside format).
"""

import os
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path

from dotenv import dotenv_values

from pubmon.config import Settings, _settings, _validate

PROFILE_DIR = "profiles"

# Every key a profile may contain. Anything else is a typo and stops the run, because an
# ignored key silently falls back to a default (for example, the wrong workspace).
ALLOWED = {
    "": {"qic", "institutions", "topic", "search", "matching", "people"},
    "qic": {"name", "label", "start_date", "workspace", "collaboration", "ibm_name"},
    "institutions": {"ibm", "partner"},
    "topic": {"terms", "broad_terms", "arxiv_categories", "hardware_terms"},
    "search": {
        "arxiv_window_days",
        "arxiv_phrases",
        "skip_types",
        "common_names",
        "arxiv_query_override",
    },
    "matching": {"auto_link", "review", "year_window"},
    "people": {"name", "side", "aliases", "orcid", "tab"},
}
REQUIRED = {
    "": {"qic", "institutions", "topic", "matching", "people"},
    "qic": {"name", "label", "start_date", "workspace"},
    "institutions": {"ibm", "partner"},
    "topic": {"terms"},
    "matching": {"auto_link", "review", "year_window"},
    "people": {"name", "side"},
}
DEFAULT_SKIP_TYPES = [
    "dataset",
    "software",
    "paratext",
    "peer-review",
    "grant",
    "supplementary-materials",
    "editorial",
    "report",
    "other",
]


@dataclass(frozen=True)
class Person:
    """One public author: their side, spelling variants and which output tab they feed."""

    name: str
    side: str
    aliases: tuple[str, ...] = ()
    orcid: str | None = None
    tab: str = "main"

    @property
    def spellings(self) -> tuple[str, ...]:
        """All spellings, display name first, without repeats."""
        return tuple(dict.fromkeys((self.name, *self.aliases)))


def available_profiles(project_dir: Path | str) -> list[str]:
    """List profile names (file names without .toml) in the project's profiles folder."""
    folder = Path(project_dir) / PROFILE_DIR
    return sorted(path.stem for path in folder.glob("*.toml")) if folder.exists() else []


def load_profile(project_dir: Path | str, name: str) -> Settings:
    """Read, strictly check and translate one named profile; never falls back to another."""
    root = Path(project_dir).resolve()
    path = root / PROFILE_DIR / f"{name}.toml"
    if not path.exists():
        names = ", ".join(available_profiles(root)) or "none found"
        raise ValueError(f"Profile '{name}' not found in {PROFILE_DIR}/. Available: {names}")
    with path.open("rb") as stream:
        raw = tomllib.load(stream)
    try:
        check_keys(raw)
        people = read_people(raw["people"])
        legacy = to_legacy(raw, people)
        _validate(legacy)
        settings = _settings(root, legacy)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid profile {path.name}: {exc}") from exc
    return replace(
        settings,
        profile_name=name,
        topic_terms=tuple(raw["topic"]["terms"]),
        topic_categories=tuple(raw["topic"].get("arxiv_categories", [])),
        broad_terms=tuple(raw["topic"].get("broad_terms", [])),
        hardware_terms=tuple(raw["topic"].get("hardware_terms", [])),
        backup_names=tuple(s for p in people if p.tab == "backup" for s in p.spellings),
        master_path=_master_path(root),
    )


def check_keys(raw: dict) -> None:
    """Reject unknown or missing keys in every section, naming the section and the key."""
    _check_table(raw, "")
    for section in ALLOWED[""] - {"people"}:
        if section in raw:
            if not isinstance(raw[section], dict):
                raise ValueError(f"[{section}] must be a table")
            _check_table(raw[section], section)
    if not isinstance(raw["people"], list) or not raw["people"]:
        raise ValueError("Add at least one [[people]] entry")
    for number, person in enumerate(raw["people"], start=1):
        if not isinstance(person, dict):
            raise TypeError(f"[[people]] entry {number} must be a table")
        _check_table(person, "people", label=f"[[people]] entry {number}")


def _check_table(table: dict, section: str, label: str | None = None) -> None:
    where = label or (f"[{section}]" if section else "the top level")
    unknown = sorted(set(table) - ALLOWED[section])
    if unknown:
        allowed = ", ".join(sorted(ALLOWED[section]))
        raise ValueError(f"Unknown key(s) {unknown} in {where}. Allowed: {allowed}")
    missing = sorted(REQUIRED.get(section, set()) - set(table))
    if missing:
        raise ValueError(f"Missing key(s) {missing} in {where}")


def read_people(entries: list[dict]) -> tuple[Person, ...]:
    """Validate each person's side, tab and spellings."""
    people = []
    for number, entry in enumerate(entries, start=1):
        where = f"[[people]] entry {number} ({entry.get('name', '?')})"
        name, side = entry["name"], entry["side"]
        tab = entry.get("tab", "main")
        aliases = entry.get("aliases", [])
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{where}: name must be nonempty text")
        if side not in {"ibm", "partner"}:
            raise ValueError(f"{where}: side must be 'ibm' or 'partner'")
        if tab not in {"main", "backup"}:
            raise ValueError(f"{where}: tab must be 'main' or 'backup'")
        if not isinstance(aliases, list) or any(not isinstance(a, str) for a in aliases):
            raise ValueError(f"{where}: aliases must be a list of text")
        orcid = entry.get("orcid")
        if orcid is not None and not isinstance(orcid, str):
            raise ValueError(f"{where}: orcid must be text")
        people.append(
            Person(name.strip(), side, tuple(a.strip() for a in aliases), orcid or None, tab)
        )
    return tuple(people)


def to_legacy(raw: dict, people: tuple[Person, ...]) -> dict:
    """Translate the profile into the older settings dictionary that config.py validates."""
    qic, topic = raw["qic"], raw["topic"]
    search = raw.get("search", {})
    query = search.get("arxiv_query_override") or build_arxiv_query(
        people,
        search.get("arxiv_phrases", []),
        topic["terms"],
        topic.get("arxiv_categories", []),
    )
    return {
        "start_date": qic["start_date"],
        "arxiv_window_days": search.get("arxiv_window_days", 90),
        "collaboration": {
            "name": qic.get("collaboration", f"IBM–{qic['name']}"),
            "partner_name": qic["name"],
            "partner_label": qic["label"],
            "ibm_name": qic.get("ibm_name", "IBM"),
        },
        "storage": {"workspace": qic["workspace"]},
        "openalex": {
            "ibm_institution_ids": raw["institutions"]["ibm"],
            "partner_institution_ids": raw["institutions"]["partner"],
            "quantum_terms": topic["terms"],
            "skip_types": search.get("skip_types", DEFAULT_SKIP_TYPES),
        },
        "arxiv": {
            "query": query,
            "watchlist": _watchlist(people),
            "common_names": search.get("common_names", []),
        },
        "matching": raw["matching"],
        "master": {"path": ""},  # The private master path never lives in a shared profile.
    }


def _watchlist(people: tuple[Person, ...]) -> list[dict]:
    # One watchlist row per spelling, so every spelling is recognised when matching authors.
    rows = []
    for person in people:
        for spelling in person.spellings:
            rows.append(
                {
                    "name": person.name,
                    "side": person.side.upper(),
                    "arxiv_name": spelling,
                    "orcid": person.orcid,
                }
            )
    return rows


def build_arxiv_query(
    people: tuple[Person, ...],
    phrases: list[str],
    terms: list[str],
    categories: list[str],
) -> str:
    """Build '(partner authors OR phrases) AND (categories OR topic terms)' for arXiv.

    Only partner-side people search. IBM people only confirm papers: searching for them
    would pull in every quantum paper they write, with or without the partner.
    """
    who = [f'au:"{spelling}"' for p in people if p.side == "partner" for spelling in p.spellings]
    who += [f'all:"{phrase}"' for phrase in phrases]
    what = [f"cat:{category}" for category in categories]
    what += [f'all:"{term}"' for term in terms]
    if not who or not what:
        raise ValueError("The arXiv search needs partner people or phrases, and topic terms")
    return "( " + " OR ".join(who) + " ) AND ( " + " OR ".join(what) + " )"


def _master_path(root: Path) -> Path | None:
    # The real master workbook is internal, so its path comes from the private environment.
    local = dotenv_values(root / ".env", interpolate=False)
    value = os.environ.get("PUBMON_MASTER", local.get("PUBMON_MASTER"))
    return root / value.strip() if value and value.strip() else None
