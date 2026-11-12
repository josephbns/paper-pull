"""Workbook matching never uses Name or reads manual data cells."""

import hashlib
from datetime import datetime
from pathlib import Path

import pytest
from openpyxl import Workbook
from openpyxl.cell.read_only import ReadOnlyCell

from pubmon.master import ALLOWED, HEADERS, match_master, read_master

MASTER = Path(__file__).parent / "fixtures/synthetic_master.xlsx"


def test_master_untouched():
    before = hashlib.sha256(MASTER.read_bytes()).hexdigest()
    rows = read_master(MASTER)
    assert len(rows) == 11
    assert hashlib.sha256(MASTER.read_bytes()).hexdigest() == before


def test_manual_columns_never_read(monkeypatch):
    original = ReadOnlyCell.value.fget
    setter = ReadOnlyCell.value.fset

    def value(cell):
        if cell.row > 1 and HEADERS[cell.column - 1] not in ALLOWED:
            raise AssertionError("A manual cell was accessed")
        return original(cell)

    monkeypatch.setattr(ReadOnlyCell, "value", property(value, setter))
    rows = read_master(MASTER)
    assert "POISON-DO-NOT-READ" not in repr(rows)


def test_master_matching_uses_ids_not_name():
    rows = read_master(MASTER)
    state = {"doi": "10.5555/syn.2025.0001", "authors": []}
    assert match_master(state, rows).pub_ids == ("SYN-0001",)
    state = {
        "title": "arXiv: Quantum walks on synthetic protein graphs, 2025-04-01",
        "pub_date": "2025-04-01",
        "authors": [{"name": "Unrelated Writer"}],
    }
    assert match_master(state, rows).pub_ids == ()
    state = {
        "pub_date": "2025-08-21",
        "authors": [{"name": "Ben Example"}, {"name": "Cara Testcase"}],
    }
    matched = match_master(state, rows)
    assert matched.pub_ids == ("SYN-0004",) and matched.method == "authors+date"


def test_hyperlink_id_fallback():
    rows = read_master(MASTER)
    row = next(row for row in rows if row.pub_id == "SYN-0005")
    assert row.values["arxiv_id"] == "2502.99905"
    assert match_master({"arxiv_id": row.values["arxiv_id"]}, rows).pub_ids == ("SYN-0005",)


def test_missing_headers_fail_loudly(tmp_path):
    path = tmp_path / "bad.xlsx"
    workbook = Workbook()
    workbook.active.append(["Name", "Pub ID"])
    workbook.save(path)
    with pytest.raises(ValueError, match="missing columns.*DOI"):
        read_master(path)


def test_non_master_tabs_are_ignored(tmp_path):
    path = tmp_path / "multiple.xlsx"
    workbook = Workbook()
    workbook.active.append(["About this synthetic workbook"])
    sheet = workbook.create_sheet("Master")
    sheet.append(HEADERS)
    row = {
        "Pub ID": "TEST-1",
        "DOI": "10.5555/synthetic",
        "Date of Publication": datetime(2025, 1, 1),
    }
    sheet.append([row.get(header) for header in HEADERS])
    workbook.save(path)
    assert read_master(path)[0].values["doi"] == "10.5555/synthetic"


def test_synthetic_fixture_generator_uses_exact_headers(tmp_path):
    import runpy

    generator = runpy.run_path(str(MASTER.parent / "generate_master.py"))
    target = tmp_path / "generated.xlsx"
    generator["generate"](target)
    rows = read_master(target)
    assert len(rows) == 11
    assert rows[4].values["arxiv_id"] == "2502.99905"
    with pytest.raises(FileExistsError):
        generator["generate"](target)


def test_absent_authors_do_not_create_a_fallback_match():
    assert not match_master(
        {"pub_date": "2025-08-20", "authors": None}, read_master(MASTER)
    ).pub_ids
