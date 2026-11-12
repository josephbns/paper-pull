"""Pure normalization helpers; these functions never call the network."""

import html
import re
import unicodedata

import idutils


def normalize_ids(
    *,
    doi: str | None = None,
    arxiv_id: str | None = None,
    pmid: str | None = None,
    openalex_id: str | None = None,
) -> dict[str, str | None]:
    """Return optional identifiers in their canonical matching forms."""
    doi = idutils.normalize_doi(doi.strip()).lower() if doi and doi.strip() else None
    if arxiv_id and arxiv_id.strip():
        arxiv_id = re.sub(r"^arxiv:\s*", "", arxiv_id.strip(), flags=re.IGNORECASE)
        arxiv_id = re.sub(
            r"^https?://(?:www\.)?arxiv.org/(?:abs|pdf)/", "", arxiv_id, flags=re.IGNORECASE
        )
        arxiv_id = idutils.normalize_arxiv(arxiv_id)
        # IDUtils adds the display prefix; internal matching uses the bare ID.
        arxiv_id = re.sub(r"^arxiv:\s*", "", arxiv_id, flags=re.IGNORECASE)
        arxiv_id = re.sub(r"v\d+$", "", arxiv_id, flags=re.IGNORECASE)
    else:
        arxiv_id = None
    pmid = idutils.normalize_pmid(pmid.strip()) if pmid and pmid.strip() else None
    if openalex_id and openalex_id.strip():
        openalex_id = openalex_id.strip().rstrip("/").rsplit("/", 1)[-1]
        if not re.fullmatch(r"W\d+", openalex_id, re.IGNORECASE):
            raise ValueError("OpenAlex work ID must have the form W followed by digits")
        openalex_id = openalex_id.upper()
    else:
        openalex_id = None
    return {"doi": doi, "arxiv_id": arxiv_id, "pmid": pmid, "openalex_id": openalex_id}


def normalize_title(title: str) -> str:
    """Normalize presentation while retaining words and numbers used for matching."""
    title = re.sub(r"<[^>]+>", " ", title)
    title = html.unescape(title)
    # Remove formatting commands, preserving their contents (SU(2), not just 2).
    title = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?", "", title)
    title = title.replace("$", "").replace("{", "").replace("}", "")
    title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    title = re.sub(r"[^a-z0-9\s]", " ", title.lower())
    return " ".join(title.split())


def surname(name: str) -> str:
    """Return the last normalized name token, excluding common name suffixes."""
    tokens = normalize_title(name).split()
    while tokens and tokens[-1] in {"jr", "sr", "ii", "iii"}:
        tokens.pop()
    return tokens[-1] if tokens else ""
