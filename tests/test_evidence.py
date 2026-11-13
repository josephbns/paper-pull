"""Selection evidence must distinguish affiliation from name/query matches."""

from dataclasses import replace
from pathlib import Path

from pubmon import export, pipeline
from pubmon.config import WatchAuthor
from pubmon.evidence import _affiliations, _watch_matches, add_selection_evidence
from pubmon.store import Store

FIXTURES = Path(__file__).parent / "fixtures/api"


def test_child_institution_lineage_retains_author_and_source_evidence(source_settings):
    raw = {
        "id": "https://openalex.org/W123",
        "authorships": [
            {
                "author": {"display_name": "Synthetic Partner"},
                "institutions": [
                    {
                        "id": "https://openalex.org/Ichild",
                        "display_name": "Synthetic campus",
                        "lineage": ["https://openalex.org/I1316902750"],
                    }
                ],
            }
        ],
    }
    details = _affiliations(raw, source_settings, "work", "Synthetic paper")
    assert len(details) == 1 and details[0]["side"] == "PARTNER"
    assert details[0]["institution"] == "Synthetic campus"
    assert details[0]["matched_profile_ids"] == "I1316902750"
    assert details[0]["source_link"] == "https://openalex.org/W123"
    different_partner = replace(source_settings, cc_institution_ids=("Iother",))
    assert not _affiliations(raw, different_partner, "work", "Synthetic paper")


def test_name_match_is_not_affiliation_and_marks_common_names(source_settings):
    settings = replace(source_settings, common_names=("Synthetic Partner",))
    watched = [WatchAuthor("Synthetic Partner", "PARTNER", "Synthetic Partner")]
    details = _watch_matches(
        {"authors": ["Synthetic Partner"], "entry_id": "https://arxiv.org/abs/2401.99999"},
        settings,
        watched,
        "work",
        "Synthetic paper",
    )
    assert len(details) == 1 and not details[0]["institution_id"]
    assert "affiliation unverified" in details[0]["basis"]
    assert "common-name ambiguity" in details[0]["basis"]


def test_history_evidence_survives_rerun_and_does_not_promote_watchlist(project):
    pipeline.run(project, no_master=True, fixtures=FIXTURES)
    settings = replace(
        project,
        watchlist=(WatchAuthor("Synthetic Clinic Author", "PARTNER", "Synthetic Clinic Author"),),
    )
    with Store(project.project_dir / "demo/data/pubmon.db") as store:
        rows = export.snapshot_rows(store, "rerun", [], {})
        add_selection_evidence(rows, store, settings)
    linked = next(row for row in rows if row["doi"] == "10.5555/synthetic-1")
    assert linked["Partner affiliation authors"] == "Synthetic Clinic Author"
    assert linked["ibm_affiliation_authors"] == "Synthetic IBM Author"
    assert linked["Partner watchlist matches"] == "Synthetic Clinic Author"
    assert "OpenAlex query" in linked["Why selected"]
    assert "Both sides reported" in linked["Affiliation evidence status"]
    assert linked["Evidence links"] and linked["affiliation_evidence"]
    assert all(row["Why selected"] and row["Evidence links"] for row in rows)
