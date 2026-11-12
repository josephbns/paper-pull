"""Read approved workbook fields without saving or evaluating manual fields."""

import posixpath
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.workbook import Workbook
from openpyxl.worksheet._read_only import ReadOnlyWorksheet

from pubmon.normalize import normalize_ids, surname

HEADERS = [
    "Name",
    "Include in official count?",
    "Type of Paper",
    "Publication or Conference (short name)",
    "Pub Status",
    "Date of Publication",
    "IBM Authors",
    "CC and other Authors",
    "Official # (from SOW Tracking)",
    "SOW Tracking",
    "Impact Factor or Journal",
    "Theme (manual)",
    "# qubits HW",
    "Most Recent Publication date",
    "Title",
    "Authors",
    "Involvement",
    "CCF Authors",
    "Hub Members",
    "Other Institutions",
    "Engine",
    "Algorithm",
    "Circuit",
    "Status",
    "Journal",
    "A&A Involvement?",
    "R2U Involvement",
    "Date for arXiv",
    "arXiv",
    "PubMed",
    "DOI",
    "Pub ID",
    "OpenAlex ID",
    "Same work as",
    "Merge source",
    "Review flag",
]
ALLOWED = (
    "Name",
    "Type of Paper",
    "Publication or Conference (short name)",
    "Pub Status",
    "Date of Publication",
    "IBM Authors",
    "CC and other Authors",
    "Title",
    "Status",
    "arXiv",
    "PubMed",
    "DOI",
    "OpenAlex ID",
    "Pub ID",
    "Same work as",
)
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


@dataclass(frozen=True)
class MasterRow:
    """Only approved public/matching cells from a master row."""

    pub_id: str
    values: dict


@dataclass(frozen=True)
class MasterMatch:
    """Existing tracker IDs; both version rows may identify one real paper."""

    pub_ids: tuple[str, ...] = ()
    method: str = ""


def _hyperlinks(path: Path, sheet_name: str) -> dict[str, str]:
    # Read only relationship attributes; a second normal workbook would load manual values.
    with ZipFile(path) as archive:
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {item.attrib["Id"]: item.attrib["Target"] for item in relationships}
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        sheet = next(
            item
            for item in workbook.findall("s:sheets/s:sheet", NS)
            if item.attrib["name"] == sheet_name
        )
        target = targets[sheet.attrib[f"{{{REL}}}id"]]
        part = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
        rel_path = posixpath.dirname(part) + "/_rels/" + posixpath.basename(part) + ".rels"
        if rel_path not in archive.namelist():
            return {}
        refs = {
            item.attrib["Id"]: item.attrib["Target"]
            for item in ET.fromstring(archive.read(rel_path))
        }
        root = ET.fromstring(archive.read(part))
        return {
            item.attrib["ref"]: refs[item.attrib[f"{{{REL}}}id"]]
            for item in root.findall("s:hyperlinks/s:hyperlink", NS)
            if f"{{{REL}}}id" in item.attrib
        }


def _sheet(workbook: Workbook) -> tuple[ReadOnlyWorksheet, dict[str, int]]:
    candidates, missing = [], list(HEADERS)
    for sheet in workbook.worksheets:
        header = [cell.value for cell in next(sheet.iter_rows(min_row=1, max_row=1), ())]
        absent = [name for name in HEADERS if name not in header]
        if len(absent) < len(missing):
            missing = absent
        if not absent:
            if any(header.count(name) != 1 for name in HEADERS):
                raise ValueError("Master header contains duplicate column names")
            candidates.append((sheet, {name: header.index(name) for name in ALLOWED}))
    if len(candidates) != 1:
        if not candidates:
            raise ValueError("Master is missing columns: " + ", ".join(missing))
        raise ValueError("More than one master sheet has the required headers")
    return candidates[0]


def _ids(values: dict, cells: dict, links: dict) -> dict:
    names = {"doi": "DOI", "arxiv_id": "arXiv", "pmid": "PubMed", "openalex_id": "OpenAlex ID"}
    ids = {}
    for scheme, name in names.items():
        value = str(values[name] or "").strip()
        if value.casefold() in {"", "arxiv", "pubmed", "doi", "—"}:
            value = links.get(cells[name], "")
        ids[scheme] = value or None
    return normalize_ids(**ids)


def read_master(path: Path | str) -> list[MasterRow]:
    """Validate headers and read only allowlisted cells; never save the workbook."""
    path = Path(path)
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet, positions = _sheet(workbook)
        links = _hyperlinks(path, sheet.title)
        rows = []
        for row_number, row in enumerate(sheet.iter_rows(min_row=2), 2):
            cells = {name: row[index] for name, index in positions.items()}
            values = {name: cell.value for name, cell in cells.items()}
            if not any(value is not None for value in values.values()):
                continue
            if not values["Pub ID"]:
                raise ValueError("Every nonempty master row needs a Pub ID")
            coordinates = {
                name: f"{get_column_letter(index + 1)}{row_number}"
                for name, index in positions.items()
            }
            values.update(_ids(values, coordinates, links))
            rows.append(MasterRow(str(values["Pub ID"]), values))
        if len({row.pub_id for row in rows}) != len(rows):
            raise ValueError("Master Pub IDs must be unique")
        return rows
    finally:
        workbook.close()


def publication_date(value: object) -> date | None:
    """Convert complete date values only, leaving missing/partial dates unknown."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def match_master(
    state: dict, rows: list[MasterRow], identifiers: Sequence[dict] = ()
) -> MasterMatch:
    """Match on DOI/arXiv/PMID, then authors/date for rows with no identifiers."""
    ids = {("doi", state.get("doi")), ("arxiv", state.get("arxiv_id")), ("pmid", state.get("pmid"))}
    ids.update((item["scheme"], item["value"]) for item in identifiers)
    keys = {"doi": "doi", "arxiv": "arxiv_id", "pmid": "pmid"}
    exact = [
        row.pub_id
        for row in rows
        if any((scheme, row.values[key]) in ids for scheme, key in keys.items() if row.values[key])
    ]
    if exact:
        return MasterMatch(tuple(sorted(exact)), "id")
    names = {surname(author["name"]) for author in (state.get("authors") or [])} - {""}
    published = publication_date(state.get("pub_date"))
    matches = []
    for row in rows:
        if any(row.values[key] for key in keys.values()):
            continue
        author_text = (
            str(row.values["IBM Authors"] or "")
            + ","
            + str(row.values["CC and other Authors"] or "")
        )
        surnames = {surname(name) for name in author_text.split(",")} - {""}
        master_date = publication_date(row.values["Date of Publication"])
        if (
            published
            and master_date
            and abs((published - master_date).days) <= 30
            and len(names & surnames) >= 2
        ):
            matches.append(row.pub_id)
    # Several authors/date matches are ambiguous and must not pick an arbitrary row.
    return MasterMatch(tuple(matches), "authors+date") if len(matches) == 1 else MasterMatch()
