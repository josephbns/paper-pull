"""Generate a new synthetic workbook; never read or overwrite an existing master."""

import argparse
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook

from pubmon.master import ALLOWED, HEADERS


def generate(path: Path) -> None:
    """Create eleven synthetic rows, with poison markers in every manual column."""
    if path.exists():
        raise FileExistsError("Synthetic generation requires a new output path")
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Master"
    sheet.append(HEADERS)
    for index in range(1, 12):
        values = {
            "Pub ID": f"SYN-{index:04}",
            "Name": f"Synthetic label {index}",
            "Title": f"Synthetic quantum paper {index}",
            "Type of Paper": "Peer Reviewed Journal",
            "Pub Status": "Published",
            "Date of Publication": datetime(2025, 1, index),
            "IBM Authors": "Ada Synth,Ben Example",
            "CC and other Authors": "Cara Testcase,Dev Fixture",
            "DOI": f"10.5555/syn.2025.{index:04}",
        }
        _case(index, values)
        sheet.append(
            [values.get(name) if name in ALLOWED else "POISON-DO-NOT-READ" for name in HEADERS]
        )
        if index == 5:
            sheet.cell(
                index + 1, HEADERS.index("arXiv") + 1
            ).hyperlink = "https://arxiv.org/abs/2502.99905"
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)
    workbook.close()


def _case(index: int, values: dict) -> None:
    if index in {1, 2}:
        values["arXiv"] = "2501.99901"
        values["Same work as"] = "SYN-0002" if index == 1 else "SYN-0001"
    if index in {2, 3, 5}:
        values.update({"DOI": None, "Type of Paper": "Open Publication", "Status": "Preprint"})
        if index == 3:
            values["arXiv"] = "2503.99902"
        if index == 5:
            values["arXiv"] = "arXiv"
    if index in {4, 6, 7, 8}:
        values.update({"DOI": None, "Title": None})
    if index == 6:
        values["Type of Paper"] = "Conference Presentation"
    if index == 7:
        values.update({"Pub Status": "Drafting", "Date of Publication": None})
    if index == 8:
        values.update(
            {
                "Name": "Quantum walks on synthetic protein graphs",
                "IBM Authors": "Hal Dummy",
                "CC and other Authors": "Ivy Sample",
            }
        )
    if index in {9, 10}:
        values["Title"] = "Error mitigation on synthetic arrays, Part " + (
            "I" if index == 9 else "II"
        )
    if index == 11:
        values.update({"IBM Authors": None, "PubMed": "99000011"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    generate(parser.parse_args().output)
