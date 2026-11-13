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


def _tag_row(**changes) -> dict:
    row = {
        "IBM affiliations": "",
        "IBM watchlist matches": "",
        "Partner affiliations": "",
        "Partner watchlist matches": "",
    }
    row.update(changes)
    return row


def test_topic_terms_match_whole_phrases_only(source_settings):
    from dataclasses import replace

    from pubmon.evidence import find_terms

    terms = ("quantum computing", "qubit", "IBM Eagle")
    text = "Quantum dots and quantum mechanical calculations; IBM Eagles; 12 qubits."
    assert find_terms(text, terms) == []
    assert find_terms("Advances in Quantum Computing on a qubit", terms) == [
        "quantum computing",
        "qubit",
    ]
    settings = replace(source_settings, topic_terms=terms)
    assert settings.tag_terms == terms


def test_openalex_abstract_is_rebuilt_in_word_order():
    from pubmon.evidence import source_text

    raw = {"title": "T", "abstract_inverted_index": {"hardware": [2], "IBM": [0], "quantum": [1]}}
    assert source_text(raw) == "T IBM quantum hardware"


def test_tags_quantum_hardware_and_backup_tab(source_settings):
    from dataclasses import replace

    from pubmon.evidence import _tags

    settings = replace(
        source_settings,
        topic_terms=("quantum computing",),
        topic_categories=("quant-ph",),
        hardware_terms=("ibm_cleveland",),
        backup_names=("Synthetic Backup",),
    )
    clinic_only = _tag_row(**{"Partner affiliations": "Cleveland Clinic"})
    _tags(clinic_only, ["Runs on ibm_cleveland for quantum computing"], set(), settings)
    assert clinic_only["Quantum?"] == "Yes" and clinic_only["tab"] == "Main"
    assert clinic_only["IBM hardware (suggested)"] == "Check: mentions ibm_cleveland"
    with_ibm = _tag_row(**{"IBM affiliations": "IBM (United States)"})
    _tags(with_ibm, ["Runs on ibm_cleveland"], set(), settings)
    assert with_ibm["IBM hardware (suggested)"] == "" and with_ibm["Quantum?"] == "No"
    maybe = _tag_row()
    _tags(maybe, ["Quantum ensembling methods"], set(), replace(settings, broad_terms=("quantum",)))
    assert maybe["Quantum?"] == "Maybe"
    backup = _tag_row(**{"Partner watchlist matches": "Synthetic Backup"})
    _tags(backup, ["Matchgate theory"], {"quant-ph"}, settings)
    assert backup["tab"] == "Backup" and backup["Quantum?"] == "Yes"


def test_partner_tie_decides_which_sheet_a_paper_goes_to(source_settings):
    from dataclasses import replace

    from pubmon.evidence import _tags

    settings = replace(
        source_settings,
        partner_name="Cleveland Clinic",
        onsite_hardware=("ibm_cleveland",),
        backup_names=("Synthetic Backup",),
    )
    cases = [
        ({"Partner affiliations": "Cleveland Clinic"}, "", "Author affiliation", "Main"),
        ({"Partner watchlist matches": "Synthetic Partner"}, "", "Named researcher", "Main"),
        ({}, "Runs on ibm_cleveland", "On-site hardware only", "Hardware only"),
        ({}, "Compared with work by Cleveland Clinic", "Mention only", "Check tie"),
        ({}, "Unrelated text", "None found", "Check tie"),
        ({"Partner watchlist matches": "Synthetic Backup"}, "Theory", "None found", "Backup"),
    ]
    for fields, text, tie, tab in cases:
        row = _tag_row(**fields)
        _tags(row, [text], set(), settings)
        assert (row["Partner tie"], row["tab"]) == (tie, tab), fields
