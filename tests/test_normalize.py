"""Offline examples of canonical identifiers, titles and author names."""

import pytest

from pubmon.normalize import normalize_ids, normalize_title, surname


@pytest.mark.parametrize(
    "value",
    [
        "10.5555/Example",
        "https://doi.org/10.5555/Example",
        "doi:10.5555/Example",
        " 10.5555/Example ",
    ],
)
def test_doi_prefixes_and_case(value):
    assert normalize_ids(doi=value)["doi"] == "10.5555/example"


@pytest.mark.parametrize(
    "value,expected",
    [
        ("arXiv:2401.12340v2", "2401.12340"),
        ("https://arxiv.org/abs/2401.12340v3", "2401.12340"),
        ("ARXIV: 2401.12340", "2401.12340"),
        ("hep-th/9901001v2", "hep-th/9901001"),
    ],
)
def test_arxiv_prefixes_and_versions(value, expected):
    assert normalize_ids(arxiv_id=value)["arxiv_id"] == expected


def test_pmid_and_openalex():
    ids = normalize_ids(pmid="PMID:12345678", openalex_id="https://openalex.org/W12345")
    assert ids["pmid"] == "12345678"
    assert ids["openalex_id"] == "W12345"
    assert normalize_ids(openalex_id="w12345")["openalex_id"] == "W12345"


def test_missing_identifiers():
    assert all(value is None for value in normalize_ids().values())
    assert all(value is None for value in normalize_ids(doi=" ", arxiv_id="").values())


def test_invalid_openalex_id():
    with pytest.raises(ValueError, match="OpenAlex work ID"):
        normalize_ids(openalex_id="I123")


@pytest.mark.parametrize(
    "title,expected",
    [
        ("$Δ$ADAPT-VQE", "adapt vqe"),
        (r"\textsf{SU}(2) circuits", "su 2 circuits"),
        ("<i>Quantum</i>-centric &amp; computing", "quantum centric computing"),
        ("Jędrzej and Flöther", "jedrzej and flother"),
        ("  Quantum\n computing! ", "quantum computing"),
        ("Part II: 20 qubits", "part ii 20 qubits"),
    ],
)
def test_title_normalization(title, expected):
    assert normalize_title(title) == expected
    assert normalize_title(expected) == expected


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Kenneth Merz Jr.", "merz"),
        ("Kenneth Merz Sr", "merz"),
        ("Example Author III", "author"),
        ("Example Author II", "author"),
        ("Jędrzej Flöther", "flother"),
        ("", ""),
    ],
)
def test_surname_suffixes_and_accents(name, expected):
    assert surname(name) == expected
