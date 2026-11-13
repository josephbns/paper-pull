"""Create a new master-format workbook from public history, never an input workbook."""

from datetime import date
from pathlib import Path

from pubmon.evidence import DETAIL_FIELDS, SUMMARY_FIELDS
from pubmon.export import SNAPSHOT_COLUMNS, _atomic
from pubmon.master import HEADERS
from pubmon.xlsx_style import new_workbook, set_link, style_notes, style_table

# Columns after the approved 36: preprint links, then tags and selection evidence.
PUBLICATION_HEADERS = HEADERS + ["Other preprint links"] + SUMMARY_FIELDS
# Manual columns (docs/MASTER_COLUMNS.md, "Never read"): left blank, styled for hand entry.
MANUAL_COLUMNS = {
    "Include in official count?",
    "Official # (from SOW Tracking)",
    "SOW Tracking",
    "Impact Factor or Journal",
    "Theme (manual)",
    "# qubits HW",
    "Involvement",
    "CCF Authors",
    "Hub Members",
    "Other Institutions",
    "Engine",
    "Algorithm",
    "Circuit",
    "A&A Involvement?",
    "R2U Involvement",
}
CENTERED = {"Pub Status", "Status", "Quantum?", "Include in official count?", "# qubits HW"}
WIDE = {
    "Name": 60,
    "Title": 60,
    "Authors": 50,
    "Why selected": 60,
    "Review flag": 50,
    "Pub ID": 22,
}
# Paper sheets in workbook order; a row's tab (set in evidence.py) picks its sheet.
SHEETS = ("Publications", "Check tie", "Backup")
SHEET_FOR_TAB = {"Main": "Publications", "Check tie": "Check tie", "Backup": "Backup"}
LINKS = (
    ("DOI", "https://doi.org/"),
    ("arXiv", "https://arxiv.org/abs/"),
    ("PubMed", "https://pubmed.ncbi.nlm.nih.gov/"),
    ("OpenAlex ID", "https://openalex.org/"),
)
READ_ME = (
    "One row per paper, built only from public metadata (OpenAlex, arXiv, Crossref). It never copies or changes your own master workbook.",
    "Publications starts with the approved 36 columns, followed by preprint links, tags and selection/affiliation evidence columns. Sources retains version history.",
    "Partner tie shows how each paper links to the partner: Author affiliation (a source reports a partner-affiliated author), Named researcher (a profile partner person is an author; the source reports no affiliation) or Used on-site IBM system (no partner author, but the paper names the partner's IBM system). Publications holds only these papers.",
    "Check tie holds papers that only mention the partner, or show no link; review before counting.",
    'Backup holds papers found only through people marked tab = "backup" in the profile, with no partner tie.',
    "Quantum? is Yes when a profile topic phrase appears in a title or abstract or the arXiv category is a profile topic category, Maybe when only a broad word (such as quantum) appears, else No. It tags; it does not decide scope.",
    "IBM hardware (suggested) lists hardware phrases found in papers with no IBM author. It is a prompt to check, not a confirmation.",
    "Date for arXiv and arXiv describe the arXiv preprint of the paper; Other preprint links list bioRxiv, medRxiv and similar preprints.",
    "Review flags are unresolved questions, not an official collaboration/counting decision.",
    "Manual count, SOW, theme, involvement and other internal fields are intentionally blank.",
    "IBM Authors and CC and other Authors contain only source-reported IBM/partner affiliation names. Authors contains all authors, including other institutions.",
    "Partner affiliation authors/affiliations use the profile's partner institution IDs. Institution names/lineages are as reported by OpenAlex, not independent verification.",
    "Affiliation evidence links each matched author to the source publication and matched institution/profile IDs. Evidence may come from a linked paper version.",
    "Watchlist name matches are separate evidence: they do not establish affiliation. Common-name collisions are marked in Affiliation evidence.",
    "Discovery routes describe query inclusion, not confirmed partnership membership or quantum relevance. Missing affiliation evidence stays unverified.",
    "Dates describe the canonical version; linked version dates and identifiers are in Sources.",
    "AUTO IDs identify history records; they are not existing master Pub IDs. Fresh GitHub backfills generate new AUTO IDs.",
    "Possible duplicates stay separate pending review. Correction/retraction flags require review.",
    "All history records are included, including rejected/not_collab records flagged for exclusion.",
    "No input master was modified or copied. This workbook does not include existing internal/manual information.",
)


def _flags(row: dict) -> str:
    flags = []
    if row.get("latest_decision") != "accepted":
        flags.append("Collaboration scope requires review")
    if not row.get("ibm_affiliation_authors", row["ibm_confirmed"]):
        flags.append("IBM affiliation unconfirmed")
    if "Partner affiliation authors" in row and not row["Partner affiliation authors"]:
        flags.append("Partner affiliation unconfirmed")
    if row["possible_duplicate_of"]:
        flags.append("Possible duplicate: see Sources")
    for event in ("CORRECTION", "RETRACTED"):
        if event in row["review_events"].split("; "):
            flags.append(event)
    if row.get("latest_decision") in {"rejected", "not_collab"}:
        flags.append("Excluded by prior review: " + row["latest_decision"])
    if not row["venue"] and row["status"] == "published":
        flags.append("Publication venue missing")
    return "; ".join(flags)


def _master_row(row: dict) -> dict:
    status = "Preprint" if row["status"] == "preprint" else "Published"
    kind = {
        "preprint": "Open Publication",
        "article": "Peer Reviewed Journal",
        "proceedings": "Conference Paper",
    }.get(row["type"], "")
    return {
        "Name": row["title"],
        "Title": row["title"],
        "Type of Paper": kind,
        "Publication or Conference (short name)": row["venue"],
        "Journal": row["venue"],
        "Status": status,
        "Pub Status": status,
        "Date of Publication": date.fromisoformat(row["pub_date"]) if row["pub_date"] else None,
        "Authors": row["all_authors"],
        "IBM Authors": row.get("ibm_affiliation_authors", ""),
        "CC and other Authors": row.get("Partner affiliation authors", ""),
        "arXiv": row["arxiv_id"],
        "Date for arXiv": date.fromisoformat(row["arxiv_date"]) if row.get("arxiv_date") else None,
        "Other preprint links": row.get("other_preprints", ""),
        "PubMed": row["pmid"],
        "DOI": row["doi"],
        "OpenAlex ID": row["openalex_id"],
        "Pub ID": "AUTO-" + row["work_key"],
        "Merge source": row["sources"],
        "Review flag": _flags(row),
        **{name: row.get(name, "") for name in SUMMARY_FIELDS},
    }


def _publications(sheet, rows: list[dict], table_name: str, tab: str) -> None:
    """Write one row per paper in the master layout, with clickable identifier links."""
    sheet.append(PUBLICATION_HEADERS)
    for row in rows:
        values = _master_row(row)
        sheet.append([values.get(name, "") for name in PUBLICATION_HEADERS])
        for name, prefix in LINKS:
            cell = sheet.cell(sheet.max_row, PUBLICATION_HEADERS.index(name) + 1)
            if cell.value:
                set_link(cell, prefix + str(cell.value).removeprefix("arXiv:"))
        for name in ("Other preprint links", "Evidence links"):
            cell = sheet.cell(sheet.max_row, PUBLICATION_HEADERS.index(name) + 1)
            if cell.value:
                set_link(cell, str(cell.value).split("; ")[0])  # Excel allows one link per cell
    style_table(sheet, table_name, inputs=MANUAL_COLUMNS, centered=CENTERED, caps=WIDE, tab=tab)


def _sources(book, rows: list[dict]) -> None:
    sources = book.create_sheet("Sources")
    columns = SNAPSHOT_COLUMNS + ["all_authors", "review_events"] + SUMMARY_FIELDS
    sources.append(columns)
    for row in rows:
        sources.append([row.get(name, "") for name in columns])
        link = sources.cell(sources.max_row, columns.index("link") + 1)
        if str(link.value).startswith(("https://", "http://")):
            set_link(link, link.value)
    caps = {
        "title": 60,
        "versions": 60,
        "all_authors": 50,
        "possible_duplicate_of": 50,
        "candidate_id": 22,
        "work_key": 22,
    }
    style_table(
        sources,
        "SourcesTable",
        inputs={"latest_decision"},
        centered={"confidence", "status", "type", "Quantum?"},
        caps=caps,
    )


def _evidence(book, rows: list[dict]) -> None:
    evidence = book.create_sheet("Affiliation evidence")
    evidence.append(DETAIL_FIELDS)
    for row in rows:
        for item in row.get("affiliation_evidence", []):
            evidence.append([item.get(name, "") for name in DETAIL_FIELDS])
            link = evidence.cell(evidence.max_row, DETAIL_FIELDS.index("source_link") + 1)
            if str(link.value).startswith(("https://", "http://")):
                set_link(link, link.value)
    style_table(
        evidence,
        "AffiliationEvidenceTable",
        centered={"side"},
        caps={"title": 60, "basis": 50, "institution": 45, "work_key": 22},
    )


def _read_me(book, sheets: dict[str, list[dict]], meta: dict) -> None:
    total = sum(len(rows) for rows in sheets.values())
    counts = ", ".join(f"{len(rows)} {name}" for name, rows in sheets.items())
    subtitle = (
        f"Generated {meta.get('generated', date.today()):%m/%d/%Y} by pubmon"
        + (f" · profile {meta['profile']}" if meta.get("profile") else "")
        + f" · {total} papers ({counts})"
    )
    title = f"{meta.get('collaboration', 'IBM collaboration')} publication master"
    style_notes(book.create_sheet("Read me"), title, subtitle, legend=True, notes=list(READ_ME))


def write_master(rows: list[dict], path: Path, meta: dict | None = None) -> None:
    """Write all canonical papers to a new styled workbook with provenance and review flags.

    `meta` may hold `collaboration`, `profile` and `generated` (a date) for the Read me title.
    """

    def write(temporary: Path) -> None:
        book = new_workbook()
        ordered = sorted(rows, key=lambda row: (row["pub_date"], row["title"]), reverse=True)
        sheets = {name: [] for name in SHEETS}
        for row in ordered:
            sheets[SHEET_FOR_TAB.get(row.get("tab", "Main"), "Check tie")].append(row)
        book.active.title = "Publications"
        for number, (name, sheet_rows) in enumerate(sheets.items()):
            sheet = book.active if number == 0 else book.create_sheet(name)
            table = name.replace(" ", "") + "Table"
            _publications(sheet, sheet_rows, table, "main" if number == 0 else "supporting")
        _sources(book, ordered)
        _evidence(book, ordered)
        _read_me(book, sheets, meta or {})
        book.save(temporary)
        book.close()

    _atomic(path, write)
