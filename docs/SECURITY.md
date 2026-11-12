# What may go where

This project supports an IBM research partnership. Assume IBM security and acceptable-use
policies apply, and that a personal GitHub account or a third-party cloud is **not** approved
for IBM-internal information unless IBM says otherwise.

## Data classes

| Class | Examples | Allowed in this repo / Codex / CI? |
| --- | --- | --- |
| Public scholarly metadata | Titles, authors, affiliations, DOIs, arXiv IDs, dates returned by public APIs | Yes |
| Synthetic test data | `tests/fixtures/synthetic_master.xlsx`, hand-written API fixtures | Yes |
| Derived public state | The SQLite history of public records and match links | Yes, once the hosting location is approved |
| Partnership-internal | The real master workbook; SOW attribution; official-count decisions; involvement labels; review decisions and notes; unpublished drafts | **No.** IBM-managed machines only |
| Gray zone | The collaborator watchlist | Only names that already appear on public collaboration papers |

## Rules for code and agents

- The real master path lives only in a local `config/settings.toml` (git-ignored) or a
  command-line flag. Never commit the real master, a copy of it, or an export of it.
- `data/` (database, raw API responses, logs) and `out/` (candidate and back-test files) are
  git-ignored. Candidate files can contain review decisions, so treat `out/` as internal.
- Secrets (`OPENALEX_API_KEY`, `PUBMON_EMAIL`, later `NCBI_API_KEY`, a Slack webhook) live in
  environment variables or a git-ignored `.env`, and in CI only in the platform's secret store.
- Test recordings must not contain keys: filter `api_key` query parameters and
  `Authorization` headers.
- Codex cloud: keep agent internet access **off** (tests are offline). If it is ever turned on,
  allow only `api.openalex.org`, `export.arxiv.org`, `api.crossref.org`, `pypi.org`,
  `files.pythonhosted.org`, with GET/HEAD/OPTIONS methods only.
- Don't paste internal data into a Codex prompt, either.

## Before every commit or upload

```bash
git status                   # nothing under data/, out/, or any .xlsx outside tests/fixtures/
git grep -n "api_key="       # no real keys
```
