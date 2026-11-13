"""Create a new master-format workbook from public history, never an input workbook."""

from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

from pubmon.evidence import DETAIL_FIELDS, SUMMARY_FIELDS
from pubmon.export import SNAPSHOT_COLUMNS, _atomic
from pubmon.master import HEADERS


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
        "PubMed": row["pmid"],
        "DOI": row["doi"],
        "OpenAlex ID": row["openalex_id"],
        "Pub ID": "AUTO-" + row["work_key"],
        "Merge source": row["sources"],
        "Review flag": _flags(row),
        **{name: row.get(name, "") for name in SUMMARY_FIELDS},
    }


def _style(sheet, table_name: str, widths: dict[str, int]) -> None:
    sheet.freeze_panes = "B2"
    sheet.sheet_view.zoomScale = 85
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="17365D")
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        sheet.column_dimensions[cell.column_letter].width = widths.get(cell.value, 20)
    sheet.row_dimensions[1].height = 45
    for cells in sheet.iter_rows(min_row=2):
        for cell in cells:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            if isinstance(cell.value, str):
                cell.data_type = "s"  # Public titles/names must never become Excel formulas.
                cell.number_format = "@"
            elif isinstance(cell.value, date):
                cell.number_format = "yyyy-mm-dd"
    if sheet.max_row > 1:
        table = Table(
            displayName=table_name, ref=f"A1:{get_column_letter(sheet.max_column)}{sheet.max_row}"
        )
        table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
        sheet.add_table(table)


def write_master(rows: list[dict], path: Path) -> None:
    """Write all canonical papers to a new styled workbook with provenance and review flags."""

    def write(temporary: Path) -> None:
        book = Workbook()
        sheet = book.active
        sheet.title = "Publications"
        headers = HEADERS + SUMMARY_FIELDS
        sheet.append(headers)
        ordered = sorted(rows, key=lambda row: (row["pub_date"], row["title"]), reverse=True)
        for row in ordered:
            values = _master_row(row)
            sheet.append([values.get(name, "") for name in headers])
            for name, prefix in (
                ("DOI", "https://doi.org/"),
                ("arXiv", "https://arxiv.org/abs/"),
                ("PubMed", "https://pubmed.ncbi.nlm.nih.gov/"),
                ("OpenAlex ID", "https://openalex.org/"),
            ):
                cell = sheet.cell(sheet.max_row, HEADERS.index(name) + 1)
                if cell.value:
                    cell.hyperlink = prefix + str(cell.value).removeprefix("arXiv:")
        _style(
            sheet, "PublicationsTable", {"Title": 65, "Name": 50, "Authors": 60, "Review flag": 65}
        )
        sources = book.create_sheet("Sources")
        columns = SNAPSHOT_COLUMNS + ["all_authors", "review_events"] + SUMMARY_FIELDS
        sources.append(columns)
        for row in ordered:
            sources.append([row.get(name, "") for name in columns])
        _style(
            sources,
            "SourcesTable",
            {"title": 65, "versions": 70, "all_authors": 60, "possible_duplicate_of": 70},
        )
        evidence = book.create_sheet("Affiliation evidence")
        evidence.append(DETAIL_FIELDS)
        for row in ordered:
            for item in row.get("affiliation_evidence", []):
                evidence.append([item.get(name, "") for name in DETAIL_FIELDS])
                link = evidence.cell(evidence.max_row, DETAIL_FIELDS.index("source_link") + 1)
                if str(link.value).startswith(("https://", "http://")):
                    link.hyperlink = link.value
        _style(evidence, "AffiliationEvidenceTable", {"title": 65, "basis": 60, "institution": 45})
        notes = book.create_sheet("Read me")
        for text in (
            "Generated master — public source metadata, one row per canonical paper.",
            "Publications starts with the approved 36 columns, followed by selection/affiliation evidence columns. Sources retains version history.",
            "Review flags are unresolved questions, not an official collaboration/counting decision.",
            "Manual count, SOW, theme, involvement and other internal fields are intentionally blank.",
            "IBM Authors and CC and other Authors contain only source-reported IBM/partner affiliation names. Authors contains all authors, including other institutions.",
            "Partner affiliation authors/affiliations use configured partner IDs (CCF by default). Institution names/lineages are as reported by OpenAlex, not independent verification.",
            "Affiliation evidence links each matched author to the source publication and matched institution/profile IDs. Evidence may come from a linked paper version.",
            "Watchlist name matches are separate evidence: they do not establish affiliation. Common-name collisions are marked in Affiliation evidence.",
            "Discovery routes describe query inclusion, not confirmed partnership membership or quantum relevance. Missing affiliation evidence stays unverified.",
            "Dates describe the canonical version; linked version dates and identifiers are in Sources.",
            "AUTO IDs identify history records; they are not existing master Pub IDs. Fresh GitHub backfills generate new AUTO IDs.",
            "Possible duplicates stay separate pending review. Correction/retraction flags require review.",
            "All history records are included, including rejected/not_collab records flagged for exclusion.",
            "No input master was modified or copied. This workbook does not include existing internal/manual information.",
        ):
            notes.append([text])
        notes.column_dimensions["A"].width = 120
        for cells in notes:
            cells[0].alignment = Alignment(wrap_text=True, vertical="top")
            notes.row_dimensions[cells[0].row].height = 32
        book.save(temporary)
        book.close()

    _atomic(path, write)
