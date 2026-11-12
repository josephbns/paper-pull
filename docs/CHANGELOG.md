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

## 2026-11-12 — Milestone 3

- Implemented OpenAlex pair and Clinic-quantum discovery, arXiv feed/rechecks, and Crossref
  enrichment. Added institution lookup to the CLI without automatic configuration changes.
- Added common safe lane errors and FetchReport snapshots/counts/notices for later pipeline
  wiring. Correction/retraction notices are not returned as new papers.
- Added hand-written synthetic JSON/Atom fixtures and adapter/CLI/retry/sanitization tests.
  Validation: 96 tests passed offline and 3 optional live-recording tests were skipped;
  Ruff lint and formatting passed. No actual API access or live institution verification
  is claimed. All three API transports were exercised with synthetic HTTP responses.
- Added default network blocking to pytest. Added VCR configuration that scrubs API-key and
  contact query parameters and authorization/User-Agent headers, plus a serialization test
  proving synthetic credential values are absent from saved cassettes.
- Updated README with the exact recording command and required destinations. Existing
  OPENALEX_API_KEY and PUBMON_EMAIL bindings were checked by presence only; neither exists
  in this cloud instance, so live OpenAlex/Crossref checks remain unrun.

### Design corrections and remaining work

- Clarified the backfill ordering in SPEC §4: use submission date, not update date, before
  applying the publication-date early stop. A recently updated old paper must not hide
  newer publications. Weekly discovery still sorts by last update.
- Unknown/unmapped OpenAlex publication types normalize to OTHER. Partial Crossref dates
  are left unknown instead of inventing missing month/day components.
- TODO(owner): confirm the Clinic title/abstract filter with live API access; review
  institution scope and watchlist names as previously documented.
- Crossref results and correction notices are ready for later matching/CLI orchestration;
  this milestone does not implement the full run/export pipeline.

## 2026-11-12 — Milestone 4

- Rechecked Milestones 1–3 before proceeding: 96 offline tests passed, 3 optional live API
  checks skipped, lint/format/dependency checks passed. Live connectivity remains unverified.
- Added `match.py`: normalized identifier/source identity resolution, DOI clues, guarded
  fuzzy matching, conflict/ambiguity review events, and atomic batch resolution/storage.
- Added `diff.py`: deterministic material-field comparisons and canonical metadata selection.
  Published versions retain their preprint IDs; older preprint responses cannot downgrade
  known publication status. The batch compares before/after once per paper.
- Added nullable canonical/source snapshot columns through an idempotent additive migration.
  Kept raw responses separate, retained legacy identities, and tested migration/reopening.
- Added the six matching acceptance tests and 11 public golden-pair cases with synthetic
  metadata. Added regression checks for conflicts, missing IDs, batch rollback, stale
  responses, multi-lane confirmation, decimal/Roman title guards, and adapter-to-store use.
- Fixed arXiv PDF/HTML URL normalization and added regressions. Identified that checking
  digits only after punctuation stripping could falsely merge decimal values like 1.2/2.1;
  matching now checks original titles. Clarified these guards in SPEC §7.
- Validation: 137 passed offline, 3 optional live-recording tests skipped; lint, format and
  dependency checks passed. Golden-pair tests prove matching behavior with supplied public
  IDs, not live API relation coverage. CSV/Excel output acceptance remains Milestone 5.
- No new TODO(owner) decisions. Existing institution/watchlist/API prerequisites remain open
  for live collection and do not block offline master/export implementation.
