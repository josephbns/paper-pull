"""Generated public master files stay separate and preserve review uncertainty."""

import hashlib
from pathlib import Path

import pytest
from openpyxl import load_workbook

from pubmon import export, pipeline
from pubmon.master import HEADERS
from pubmon.master_export import write_master
from pubmon.store import Store

ROOT = Path(__file__).resolve().parents[1]


def test_paper_link_falls_back_to_openalex(project, monkeypatch):
    pipeline.run(project, no_master=True, fixtures=ROOT / "tests/fixtures/api")
    with Store(project.project_dir / "demo/data/pubmon.db") as store:
        original = store.get_work_state
        monkeypatch.setattr(
            store,
            "get_work_state",
            lambda key: {
                **original(key),
                "doi": None,
                "arxiv_id": None,
                "pmid": None,
                "openalex_id": "W123",
            },
        )
        rows = export.snapshot_rows(store, "test", [], {})
    assert all(row["link"] == "https://openalex.org/W123" for row in rows)


def test_generated_master_includes_all_history_on_rerun_without_touching_input(project):
    original = ROOT / "tests/fixtures/synthetic_master.xlsx"
    before = hashlib.sha256(original.read_bytes()).hexdigest()
    fixtures = ROOT / "tests/fixtures/api"
    first = pipeline.run(project, master_path=original, fixtures=fixtures, xlsx=True)
    initial = Path(first["paths"]["master"])
    saved = initial.read_bytes()
    second = pipeline.run(project, master_path=original, fixtures=fixtures, xlsx=True)
    assert second["candidates"] == 0
    assert second["paths"]["master"] != str(initial)
    assert initial.read_bytes() == saved
    assert hashlib.sha256(original.read_bytes()).hexdigest() == before
    book = load_workbook(second["paths"]["master"])
    assert book.sheetnames == [
        "Publications",
        "Check tie",
        "Backup",
        "Sources",
        "Affiliation evidence",
        "Read me",
    ]
    sheet = book["Publications"]
    assert [cell.value for cell in sheet[1]][: len(HEADERS)] == HEADERS
    assert sheet.max_row == 4
    assert sheet.freeze_panes == "B2" and len(sheet.tables) == 1
    rows = [dict(zip(HEADERS, values)) for values in sheet.iter_rows(min_row=2, values_only=True)]
    assert len({row["Pub ID"] for row in rows}) == 3
    assert any(row["DOI"] and row["arXiv"] for row in rows)
    assert any("CORRECTION" in row["Review flag"] for row in rows)
    for row in rows:
        assert row["Authors"] and row["Review flag"]
        for name in (
            "Include in official count?",
            "SOW Tracking",
            "Theme (manual)",
        ):
            assert row[name] is None
    assert any(row["IBM Authors"] == "Synthetic IBM Author" for row in rows)
    assert any(row["CC and other Authors"] == "Synthetic Clinic Author" for row in rows)
    assert book["Affiliation evidence"].max_row > 1
    assert not any(c.data_type == "f" for s in book for cells in s for c in cells)
    book.close()


def test_master_literals_links_and_overwrite_protection(project, tmp_path):
    pipeline.run(project, no_master=True, fixtures=ROOT / "tests/fixtures/api")
    with Store(project.project_dir / "demo/data/pubmon.db") as store:
        rows = export.snapshot_rows(store, "test", [], {})
    row = rows[0]
    row.update(
        title="=UNTRUSTED()",
        all_authors="=AUTHOR()",
        doi="",
        arxiv_id="",
        pmid="",
        openalex_id="W123",
        possible_duplicate_of="target",
        ibm_confirmed=False,
    )
    path = tmp_path / "master.xlsx"
    write_master([row], path)
    book = load_workbook(path)
    sheet = book["Publications"]
    title = sheet.cell(2, HEADERS.index("Title") + 1)
    assert title.value == "=UNTRUSTED()" and title.data_type == "s"
    assert (
        sheet.cell(2, HEADERS.index("OpenAlex ID") + 1).hyperlink.target
        == "https://openalex.org/W123"
    )
    assert "Possible duplicate" in sheet.cell(2, HEADERS.index("Review flag") + 1).value
    book.close()
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        write_master([row], path)
    assert path.read_bytes() == before
