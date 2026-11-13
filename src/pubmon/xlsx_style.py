"""House style for every Excel file pubmon writes: banking conventions, one place.

Conventions (as in banking models): black text is data from public sources, blue text is
entered by hand, green text is a link. Arial 10 throughout, a navy header row, thin grey
rules instead of gridlines, consistent column widths, and pages ready to print.
"""

from datetime import date, datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.utils.indexed_list import IndexedList
from openpyxl.worksheet.table import Table, TableStyleInfo

FONT = "Arial"
SIZE = 10
NAVY = "1F3864"
WHITE = "FFFFFF"
BLACK = "000000"
BLUE = "0000FF"  # entered by hand
GREEN = "008000"  # link
GREY_TEXT = "595959"
RULE = "D9D9D9"
DATE_FORMAT = "mm/dd/yyyy"
COUNT_FORMAT = "#,##0"
ROW_HEIGHT = 12.75  # Excel's standard height for one line of Arial 10

DATA = Font(name=FONT, size=SIZE, color=BLACK)
INPUT = Font(name=FONT, size=SIZE, color=BLUE)
LINK = Font(name=FONT, size=SIZE, color=GREEN)
HEADER = Font(name=FONT, size=SIZE, bold=True, color=WHITE)
HEADER_FILL = PatternFill("solid", fgColor=NAVY)
THIN = Side(style="thin", color=RULE)
GRID = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
TAB_COLORS = {"main": NAVY, "supporting": "8EA9DB", "notes": "A6A6A6"}


def new_workbook() -> Workbook:
    """Create a workbook whose default font is Arial 10, so typed cells match the style."""
    book = Workbook()
    # openpyxl has no public setting for the default font; font 0 is what Excel uses for
    # unformatted cells, so it is replaced before any cell is styled.
    book._fonts = IndexedList([Font(name=FONT, size=SIZE, family=2)])
    return book


def set_link(cell, url: str) -> None:
    """Make a cell a clickable link, in banking green."""
    cell.hyperlink = url
    cell.font = LINK


def _width(header: str, values: list, cap: int) -> float:
    # Short columns fit their longest entry; long ones fit most entries (90th percentile).
    # Either way, leave room for the header on two lines.
    lengths = sorted(10 if isinstance(v, (date, datetime)) else len(str(v)) for v in values if v)
    typical = lengths[int(len(lengths) * 0.9)] if lengths else 0
    if lengths and lengths[-1] <= 24:
        typical = lengths[-1]
    longest_word = max((len(word) for word in header.split()), default=8)
    header_fit = max(longest_word + 3, (len(header) + 1) // 2 + 4)
    return float(min(max(typical + 2, header_fit, 10), max(cap, header_fit)))


def _format_cell(cell, header: str, inputs: set[str], centered: set[str]) -> None:
    value = cell.value
    if cell.hyperlink is None:
        cell.font = INPUT if header in inputs else DATA
    cell.border = GRID
    middle = header in centered or isinstance(value, (date, datetime, bool))
    # Wrapping inside a fixed one-line row, anchored at the top, shows each cell's first
    # line and keeps long text from spilling into empty neighbouring cells; the full text
    # stays in the cell.
    cell.alignment = Alignment(
        horizontal="center" if middle else "left", vertical="top", wrap_text=True
    )
    if isinstance(value, str):
        cell.data_type = "s"  # Public titles and names must never become Excel formulas.
        cell.number_format = "@"
    elif isinstance(value, (date, datetime)):
        cell.number_format = DATE_FORMAT
    elif isinstance(value, int) and not isinstance(value, bool):
        cell.number_format = COUNT_FORMAT
        cell.alignment = Alignment(horizontal="right", vertical="top")


def style_table(
    sheet,
    table_name: str,
    *,
    inputs: set[str] = frozenset(),
    centered: set[str] = frozenset(),
    caps: dict[str, int] | None = None,
    tab: str = "supporting",
) -> None:
    """Apply the house style to a sheet whose first row is a header row."""
    headers = [cell.value for cell in sheet[1]]
    for cell in sheet[1]:
        cell.font, cell.fill, cell.border = HEADER, HEADER_FILL, GRID
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for column, header in enumerate(headers, start=1):
        cells = [row[column - 1] for row in sheet.iter_rows(min_row=2)]
        for cell in cells:
            _format_cell(cell, header, inputs, centered)
        cap = (caps or {}).get(header, 45)
        width = _width(header, [cell.value for cell in cells], cap)
        sheet.column_dimensions[get_column_letter(column)].width = width
    sheet.row_dimensions[1].height = 30
    for row in range(2, sheet.max_row + 1):
        sheet.row_dimensions[row].height = ROW_HEIGHT
    _finish(sheet, table_name, tab)


def _finish(sheet, table_name: str, tab: str) -> None:
    sheet.freeze_panes = "B2"
    sheet.sheet_view.showGridLines = False
    sheet.sheet_view.zoomScale = 90
    sheet.sheet_properties.tabColor = TAB_COLORS[tab]
    last = f"{get_column_letter(max(sheet.max_column, 1))}{max(sheet.max_row, 2)}"
    if sheet.max_row > 1:
        table = Table(displayName=table_name, ref=f"A1:{last}")
        table.tableStyleInfo = TableStyleInfo(name="TableStyleLight1", showRowStripes=True)
        sheet.add_table(table)
    _print_setup(sheet)


def _print_setup(sheet) -> None:
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.paperSize = sheet.PAPERSIZE_LETTER
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.print_title_rows = "1:1"
    sheet.page_margins.left = sheet.page_margins.right = 0.4
    sheet.page_margins.top = sheet.page_margins.bottom = 0.6
    sheet.oddFooter.left.text = "&A"
    sheet.oddFooter.right.text = "Page &P of &N"
    for part in (sheet.oddFooter.left, sheet.oddFooter.right):
        part.font, part.size = FONT, 8


def style_notes(sheet, title: str, subtitle: str, legend: bool, notes: list[str]) -> None:
    """Write a Read me sheet: title, generation details, colour key and numbered notes."""
    sheet.append([title])
    sheet.append([subtitle])
    sheet["A1"].font = Font(name=FONT, size=14, bold=True, color=NAVY)
    sheet["A2"].font = Font(name=FONT, size=SIZE, italic=True, color=GREY_TEXT)
    if legend:
        sheet.append([])
        sheet.append(["Colour key"])
        sheet.cell(sheet.max_row, 1).font = Font(name=FONT, size=SIZE, bold=True)
        for text, font in (
            ("Black: data from public sources", DATA),
            ("Blue: entered by hand (manual columns are left blank for you)", INPUT),
            ("Green: link; click to open the public record", LINK),
        ):
            sheet.append([text])
            sheet.cell(sheet.max_row, 1).font = font
    sheet.append([])
    sheet.append(["Notes"])
    sheet.cell(sheet.max_row, 1).font = Font(name=FONT, size=SIZE, bold=True)
    for number, text in enumerate(notes, start=1):
        sheet.append([f"{number}. {text}"])
        cell = sheet.cell(sheet.max_row, 1)
        cell.font = DATA
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        # Excel does not resize wrapped rows written by a program, so estimate the lines.
        sheet.row_dimensions[cell.row].height = 13.5 * (1 + (len(cell.value) - 1) // 145)
    sheet.column_dimensions["A"].width = 120
    sheet.sheet_view.showGridLines = False
    sheet.sheet_properties.tabColor = TAB_COLORS["notes"]
    _print_setup(sheet)
