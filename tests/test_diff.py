"""Material changes ignore fetch bookkeeping and retain deterministic field order."""

from pubmon.diff import material_changes


def test_material_changes_includes_all_changed_fields():
    old = {"doi": None, "venue": None, "status": "preprint", "raw_hash": "old"}
    new = {
        "doi": "10.5555/journal",
        "venue": "Synthetic Journal",
        "status": "published",
        "raw_hash": "new",
    }
    changes = material_changes(old, new)
    assert [change.field for change in changes] == ["doi", "venue", "status"]
    assert changes[0].old is None and changes[0].new == "10.5555/journal"


def test_fetch_time_and_raw_hash_are_not_material_changes():
    assert (
        material_changes(
            {"raw_hash": "old", "fetched_at": "before"}, {"raw_hash": "new", "fetched_at": "after"}
        )
        == []
    )
