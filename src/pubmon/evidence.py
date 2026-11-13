"""Explain selection using stored public affiliations and explicit watchlist matches."""

import json
import re

from pubmon.config import Settings
from pubmon.normalize import normalize_title
from pubmon.sources.arxiv_src import read_watchlist
from pubmon.sources.common import entity_id
from pubmon.store import Store

SUMMARY_FIELDS = [
    "Partner tie",
    "Quantum?",
    "IBM hardware (suggested)",
    "Why selected",
    "Discovery routes",
    "Partner affiliation authors",
    "Partner affiliations",
    "IBM affiliations",
    "Partner watchlist matches",
    "IBM watchlist matches",
    "Evidence links",
    "Affiliation evidence status",
]
DETAIL_FIELDS = [
    "work_key",
    "title",
    "author",
    "side",
    "institution",
    "institution_id",
    "matched_profile_ids",
    "basis",
    "source_link",
]


def _affiliations(raw: dict, settings: Settings, key: str, title: str) -> list[dict]:
    evidence = []
    groups = (("IBM", settings.ibm_institution_ids), ("PARTNER", settings.partner_institution_ids))
    for authorship in raw.get("authorships", []):
        name = authorship.get("author", {}).get("display_name", "")
        for institution in authorship.get("institutions", []):
            identity = entity_id(institution.get("id") or "")
            lineage = {identity, *(entity_id(value) for value in institution.get("lineage", []))}
            for side, configured in groups:
                matches = lineage & {entity_id(value) for value in configured}
                if name and matches:
                    evidence.append(
                        {
                            "work_key": key,
                            "title": title,
                            "author": name,
                            "side": side,
                            "institution": institution.get("display_name") or identity,
                            "institution_id": identity,
                            "matched_profile_ids": "; ".join(sorted(matches)),
                            "basis": "OpenAlex authorship affiliation (institution ID/lineage)",
                            "source_link": "https://openalex.org/" + entity_id(raw["id"]),
                        }
                    )
    return evidence


def _watch_matches(
    raw: dict, settings: Settings, watchlist: list, key: str, title: str
) -> list[dict]:
    authors = {normalize_title(name): name for name in raw.get("authors", [])}
    common = {normalize_title(name) for name in settings.common_names}
    evidence = []
    for watched in watchlist:
        name = authors.get(normalize_title(watched.arxiv_name))
        if not name:
            continue
        ambiguous = bool({normalize_title(watched.name), normalize_title(name)} & common)
        basis = "Watchlist name match only; affiliation unverified"
        if ambiguous:
            basis += "; common-name ambiguity"
        evidence.append(
            {
                "work_key": key,
                "title": title,
                "author": name,
                "side": watched.side,
                "institution": "",
                "institution_id": "",
                "matched_profile_ids": "",
                "basis": basis,
                "source_link": raw.get("entry_id", ""),
            }
        )
    return evidence


def _join(items) -> str:
    return "; ".join(sorted({item for item in items if item}))


def source_text(raw: dict) -> str:
    """Return a source record's title and abstract (arXiv summary or OpenAlex word index)."""
    title = raw.get("title") or raw.get("display_name") or ""
    abstract = raw.get("summary") or ""
    index = raw.get("abstract_inverted_index") or {}
    if index:
        # OpenAlex stores abstracts as {word: [positions]}; rebuild the text in order.
        placed = sorted((spot, word) for word, spots in index.items() for spot in spots)
        abstract = " ".join(word for _, word in placed)
    return f"{title} {abstract}"


def find_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    """Return the terms that appear in the text as whole words, ignoring case."""
    found = []
    for term in terms:
        # Word edges stop "qubit" matching inside "qubits2" and "IBM Eagle" inside "IBM Eagles".
        if re.search(rf"(?<![\w-]){re.escape(term)}(?![\w-])", text, flags=re.IGNORECASE):
            found.append(term)
    return found


def _tags(row: dict, texts: list[str], categories: set[str], settings: Settings) -> None:
    """Add the Quantum? and IBM hardware columns, and choose the output tab."""
    text = " ".join(texts)
    on_topic = bool(
        find_terms(text, settings.tag_terms) or categories & set(settings.topic_categories)
    )
    ibm_seen = row["IBM affiliations"] or row["IBM watchlist matches"]
    hardware = [] if ibm_seen else find_terms(text, settings.hardware_terms)
    matches = row["Partner watchlist matches"] + "; " + row["IBM watchlist matches"]
    watched = {normalize_title(name) for name in matches.split("; ") if name}
    backup_spellings = {normalize_title(name) for name in settings.backup_names}
    affiliated = row["IBM affiliations"] or row["Partner affiliations"]
    # Backup only when every matched person is a backup person and no affiliation is reported.
    backup = bool(watched) and watched <= backup_spellings and not affiliated
    # "Maybe" catches on-topic papers whose wording the specific phrases miss.
    maybe = not on_topic and bool(find_terms(text, settings.broad_terms))
    row["Quantum?"] = "Yes" if on_topic else "Maybe" if maybe else "No"
    row["IBM hardware (suggested)"] = "Check: mentions " + ", ".join(hardware) if hardware else ""
    row["Partner tie"] = partner_tie(row, text, settings)
    row["tab"] = TIE_TABS.get(row["Partner tie"], "Check tie")
    if backup and row["tab"] != "Main":
        row["tab"] = "Backup"


# Where each kind of partner tie is listed in the generated workbook. Papers by partner
# authors and papers that used the partner's on-site IBM system go on Publications.
TIE_TABS = {
    "Author affiliation": "Main",
    "Named researcher": "Main",
    "Used on-site IBM system": "Main",
}


def partner_tie(row: dict, text: str, settings: Settings) -> str:
    """Name the strongest link between a paper and the partner institution."""
    backup = {normalize_title(name) for name in settings.backup_names}
    named = [
        name
        for name in row["Partner watchlist matches"].split("; ")
        if name and normalize_title(name) not in backup
    ]
    if row["Partner affiliations"]:
        return "Author affiliation"
    if named:
        return "Named researcher"
    if find_terms(text, settings.onsite_hardware):
        return "Used on-site IBM system"
    if find_terms(text, (settings.partner_name,)):
        return "Mention only"
    return "None found"


def _summary(
    row: dict, details: list[dict], routes: set[str], settings: Settings, links: set[str]
) -> None:
    affiliated = [item for item in details if item["institution_id"]]
    watched = [item for item in details if not item["institution_id"]]
    partner = [item for item in affiliated if item["side"] == "PARTNER"]
    ibm = [item for item in affiliated if item["side"] == "IBM"]
    reasons = []
    if "pair" in routes:
        reasons.append(
            f"OpenAlex query: {settings.ibm_name} + {settings.partner_name} institution lineages"
        )
    if "clinic_quantum" in routes:
        terms = ", ".join(settings.quantum_terms[:3]) + (
            ", …" if len(settings.quantum_terms) > 3 else ""
        )
        reasons.append(f"OpenAlex query: {settings.partner_name} + title/abstract terms ({terms})")
    if "arxiv_feed" in routes:
        reasons.append("arXiv configured query; query/name matches are not proof of affiliation")
    if not reasons:
        reasons.append("Retained history/recheck; original discovery route unavailable")
    row.update(
        {
            "Why selected": " | ".join(reasons),
            "Discovery routes": _join(routes),
            "Partner affiliation authors": _join(item["author"] for item in partner),
            "Partner affiliations": _join(item["institution"] for item in partner),
            "IBM affiliations": _join(item["institution"] for item in ibm),
            "Partner watchlist matches": _join(
                item["author"] for item in watched if item["side"] == "PARTNER"
            ),
            "IBM watchlist matches": _join(
                item["author"] for item in watched if item["side"] == "IBM"
            ),
            "Evidence links": _join(links),
            "Affiliation evidence status": (
                "Both sides reported by OpenAlex; partnership scope unreviewed"
                if partner and ibm
                else "Partner affiliation reported; IBM affiliation unverified"
                if partner
                else "IBM affiliation reported; partner affiliation unverified"
                if ibm
                else "No author-level affiliation evidence; query/watchlist only"
            ),
            "ibm_affiliation_authors": _join(item["author"] for item in ibm),
            "affiliation_evidence": details,
        }
    )


def add_selection_evidence(rows: list[dict], store: Store, settings: Settings) -> None:
    """Attach per-paper explanations without extra requests or reading any input master."""
    watchlist = (
        list(settings.watchlist)
        if settings.watchlist is not None
        else (read_watchlist(settings.watchlist_file) if settings.watchlist_file.exists() else [])
    )
    for row in rows:
        details, routes = [], set(filter(None, row.get("lanes", "").split("; ")))
        links, texts, categories = set(), [], set()
        for record in store.list_source_records(row["work_key"]):
            routes.add(record["lane"])
            raw = json.loads(record["raw_json"])
            texts.append(source_text(raw))
            categories.update(raw.get("categories") or [])
            if record["source"] == "openalex":
                links.add("https://openalex.org/" + entity_id(raw["id"]))
                details.extend(_affiliations(raw, settings, row["work_key"], row["title"]))
            elif record["source"] == "arxiv":
                links.add("https://arxiv.org/abs/" + record["source_id"])
                details.extend(
                    _watch_matches(raw, settings, watchlist, row["work_key"], row["title"])
                )
        details = list({tuple(item.items()): item for item in details}.values())
        _summary(row, details, routes, settings, links)
        _tags(row, texts or [row["title"]], categories, settings)
