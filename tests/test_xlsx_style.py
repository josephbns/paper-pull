"""The house style: Arial 10, navy headers, green links, blue hand-entry columns."""

from datetime import date
from pathlib import Path

from openpyxl import load_workbook

from pubmon import pipeline
from pubmon.export import display_text
from pubmon.xlsx_style import BLUE, GREEN, NAVY, new_workbook, set_link, style_table

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/api"


def _rgb(color) -> str:
    return (color.rgb or "")[-6:] if color is not None else ""


def test_style_table_applies_banking_conventions(tmp_path):
    book = new_workbook()
    sheet = book.active
    sheet.append(["Title", "Date", "DOI", "Manual note", "Count"])
    sheet.append(["A paper", date(2026, 1, 2), "10.1/x", "", 7])
    set_link(sheet["C2"], "https://doi.org/10.1/x")
    style_table(sheet, "T", inputs={"Manual note"})
    book.save(tmp_path / "s.xlsx")
    sheet = load_workbook(tmp_path / "s.xlsx").active
    header, title, day, doi, note, count = sheet["A1"], *sheet[2]
    assert header.font.name == "Arial" and header.font.b and _rgb(header.fill.fgColor) == NAVY
    assert title.font.name == "Arial" and title.font.sz == 10
    assert _rgb(doi.font.color) == GREEN and doi.hyperlink.target.startswith("https://")
    assert _rgb(note.font.color) == BLUE
    assert day.number_format == "mm/dd/yyyy" and day.alignment.horizontal == "center"
    assert count.number_format == "#,##0" and count.alignment.horizontal == "right"
    assert sheet.freeze_panes == "B2" and not sheet.sheet_view.showGridLines
    assert sheet.page_setup.orientation == "landscape" and sheet.print_title_rows == "$1:$1"


def test_default_font_is_arial_for_cells_typed_later():
    assert new_workbook()._fonts[0].name == "Arial"


def test_display_text_removes_html_leftovers():
    assert (
        display_text("Parkinsonism &amp; Related Disorders") == "Parkinsonism & Related Disorders"
    )
    assert display_text("Effects <i>in vivo</i>") == "Effects in vivo"


def test_generated_workbooks_follow_the_house_style(project):
    result = pipeline.run(project, no_master=True, fixtures=FIXTURES, xlsx=True)
    master = load_workbook(result["paths"]["master"])
    sheet = master["Publications"]
    headers = [cell.value for cell in sheet[1]]
    manual = sheet.cell(2, headers.index("SOW Tracking") + 1)
    doi = sheet.cell(2, headers.index("DOI") + 1)
    assert _rgb(manual.font.color) == BLUE and manual.value is None
    assert doi.value and _rgb(doi.font.color) == GREEN
    assert master["Read me"]["A1"].value.endswith("publication master")
    review = load_workbook(Path(result["paths"]["candidates"]).with_suffix(".xlsx"))
    sheet = review["Candidates"]
    headers = [cell.value for cell in sheet[1]]
    assert headers[0] == "title" and headers[-1] == "work_key"
    assert {sheet.cell(2, headers.index("ibm_confirmed") + 1).value} <= {"Yes", "No"}
    assert _rgb(sheet.cell(2, headers.index("decision") + 1).font.color) == BLUE
    assert review.sheetnames == ["Candidates", "Read me"]
