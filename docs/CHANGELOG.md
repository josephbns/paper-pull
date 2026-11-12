# Changelog

## 2026-11-12 — Milestone 1

- Imported the supplied build pack into the existing personal GitHub checkout, excluding
  its embedded `.git` directory. The owner's personal-repository instruction supersedes
  the pack's historical advice to wait for work GitHub. No remote push was performed.
- Added the src package skeleton, explicit Work model and enums, frozen settings loader,
  and pure identifier/title/surname normalization helpers.
- Settings fall back to the example, preserve the arXiv query verbatim, resolve paths from
  the project root, and require credentials only when a network caller requests them.
  Process variables override `.env`; credentials are excluded from settings representations.
- Formatted bundled documentation code examples with Ruff; specification behavior unchanged.
- Added 35 offline tests for normalization, settings validation and model collection isolation.
  Validation: 35 passed with recording disabled and network blocked; Ruff lint and format
  checks clean; installed dependency check and CLI help/version verified.
- Full pipeline, database, matching and one-row-per-paper exports remain later milestones.
  The CLI currently supplies help/version only, and no workbook was read by application code.

### Remaining owner decisions (not blockers for Milestone 1)

- TODO(owner): decide whether institution entities outside the supplied parent lineages belong.
- TODO(owner): review the watchlist; supply IBM-side names and identify ambiguous common names.
- TODO(owner): confirm the Clinic title/abstract search with a live request in Milestone 3.
- TODO(owner): supply API configuration securely before live collection.

### Interpretation notes for future milestones

- LaTeX wrappers are removed while their text is retained; non-ASCII Greek characters are
  dropped by the specification's NFKD-to-ASCII rule. This is normalization, not transliteration.
- SPEC §7's numeric-token guard cannot distinguish Roman-numeral Part I/II by itself. Retain
  the negative acceptance case and resolve that guard in Milestone 4 before enabling merges.
- One source record is a Work; later identity resolution groups several source records into
  one paper. Only that paper identity controls final output rows.

## 2026-11-12 — Milestone 2

- Added `store.py`: idempotent schema creation via sqlite-utils, explicit transactions,
  paper/identifier/source upserts, event queue/export markers, run history and local decisions.
- Enabled foreign keys and bound SQL parameters. Duplicate identifiers stay on one paper;
  conflicting identifiers or source identities raise `IdentifierConflict` for later review.
- Added 24 file-backed history tests. Validation: 59 tests passed offline in total;
  Ruff lint and formatting checks clean. Rollback was checked against the database bytes
  as well as all six tables, including recovery on the same connection.
- Updated README development status and documented transaction use and test commands.
- Milestone 1 was committed and pushed to personal GitHub as `c03a348`; this milestone
  continues in the same checkout. No uploaded workbook or actual runtime data is committed.

### Design choices and remaining work

- Decisions retain history; the latest imported decision is authoritative. An identical
  re-import preserves the original decision timestamp rather than creating another row.
- A merge decision records intent only; applying the merge belongs to Milestone 5.
- Run/event orchestration, database backups and the CLI arrive with the later pipeline work.
- No new TODO(owner) items or blocking ambiguities. Earlier institution/watchlist decisions
  remain open for live collection; no credentials are needed for this milestone.
