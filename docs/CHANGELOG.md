# Changelog

## 2026-11-13 — Every Publications row ties to the partner

- New **Partner tie** column (evidence.partner_tie): Author affiliation, Named researcher,
  On-site hardware only, Mention only, None found. Only the first two reach Publications.
- New sheets: **Hardware only** (no partner author; the paper names the partner's IBM system,
  from the profile's new `[qic] onsite_hardware`) and **Check tie** (mention only or no link).
  Backup now holds backup-person-only papers without any partner tie.
- Checked against the 13 Nov live output (rerun 22:11 UTC, main branch): 148 papers tie to
  Cleveland Clinic through an author; 2 used ibm_cleveland only (QAOA, short-rate models);
  1 only cites Clinic work ("Bridging the NISQ…"); 1 could not be verified (Pressure-Poisson);
  44 are Strelchuk-only. AEGISS confirmed tied (Vijay Krishna, Cleveland Clinic Research).
- Validation: 220 offline tests passed, 2 skipped; lint/format clean.

## 2026-11-13 — Banking-style Excel formatting

- Added xlsx_style.py, one house style for both Excel outputs: Arial 10 (also the workbook
  default font), navy header row with white bold text, black for source data, blue for
  hand-entry columns (the 15 manual master columns; decision and reviewer_note), green for
  links, thin grey rules with gridlines off, mm/dd/yyyy dates, #,##0 counts, light row stripes.
- Uniform 12.75 pt rows with top-anchored wrapping: each cell shows its first line and long
  text no longer spills into empty neighbouring cells. Short columns fit their longest value;
  long ones fit most values; headers always fit on two lines.
- Print-ready: landscape, one page wide, header row repeated, sheet name and page numbers in
  the footer. Tab colours separate main, supporting and notes sheets.
- Read me sheets now have a title, generation details (date, profile, paper counts), a colour
  key and numbered notes. The candidates workbook gained a Read me with review instructions,
  leads with the title and the two review columns, shows real dates and Yes/No.
- HTML leftovers from sources ("&amp;", italic tags) are removed from titles and venues.
- Validation: 219 offline tests passed, 2 skipped; lint/format clean. Visual check by rendering
  both workbooks rebuilt from the 13 Nov live output through LibreOffice.

## 2026-11-13 — Named QIC profiles, topic tags and setup guide (owner-approved scope)

- Added profile.py and `profiles/`: one strictly checked, committed, public settings file per
  QIC (`profiles/cleveland-clinic.toml`, blank `profiles/TEMPLATE.toml.example`). Unknown or
  missing keys stop the command with the section and allowed keys. Profiles translate into
  the existing Settings object, so existing validation, history and tests are unchanged.
- Commands now require a profile (`--profile`, `PUBMON_PROFILE`, or `PUBMON_PROFILE` in
  `.env`) or an existing local `config/settings.toml`; the silent fallback to the example
  file no longer applies to the command line. New `pubmon check-profile` validates a profile
  and prints the generated arXiv query without calling APIs.
- People are listed once. Partner people and phrases build the arXiv query; IBM people only
  confirm papers. A test pins the CCF query to every clause of the original feed; the only
  deliberate additions are Ruihao Li / Rui-Hao Li. Seeded 32 IBM people: 31 IBM-affiliated
  (per OpenAlex) authors on two or more public quantum papers with a Cleveland Clinic author,
  plus Sarah Mostame from the public FCC-lattice arXiv paper.
- Topic terms replace the bare word "quantum" in the OpenAlex partner search (groups of at
  most five, phrases quoted). New master columns: Other preprint links, Quantum? (Yes/Maybe/
  No), IBM hardware (suggested); Date for arXiv is now filled. New Backup sheet for papers
  found only through `tab = "backup"` people (Sergii Strelchuk).
- The private master path moved to `PUBMON_MASTER` in `.env` (or `--master`); profiles reject
  it. GitHub workflow takes a profile input. Added docs/SETUP.md (sign-ups, install,
  profiles, GitHub Actions, moving to IBM GitHub) and rewrote CUSTOMIZATION.md.
- Validation: 215 offline tests passed, 2 optional source recordings skipped. Lint and
  formatting pass; synthetic dry run and workbook generation pass with the profile. On the
  13 Nov live output (titles only), all 22 off-topic partner papers tag "No" and the 44
  Strelchuk-only papers route to Backup. No live API run yet.
- Remaining owner TODOs: verify quoted OpenAlex phrase search live; review hardware terms,
  IBM people and common names (e.g. Jun Qin); institution scope (IBM Japan, Clinic Abu Dhabi,
  Akron, London).

## 2026-11-13 — Publication selection and affiliation evidence

- Added evidence.py to explain inclusion from stored public source records, current profile
  institution IDs/lineage and watchlist. No extra network calls, private data or guessed names.
- Generated master now fills IBM Authors and CC and other Authors with source-reported
  IBM/partner affiliation matches. All other authors remain in Authors. Appended explicit
  selection reasons/routes, partner author/institution evidence, IBM institutions, separate
  watchlist matches, source links and evidence status after the existing 36 columns.
- Added an Affiliation evidence sheet tracing each matched author to institution/profile
  IDs, source publication and evidence basis. Watchlist matches (including common names)
  never establish affiliation. Partner columns follow the profile (CCF by default), and
  unverified ties/partnership scope remain review flags even when a query found the paper.
- Evidence is rebuilt from stored linked versions on zero-candidate reruns. No changes to
  selection queries, matching thresholds, workbook input handling or row identities.
- Validation: 200 offline tests passed, 2 optional source recordings skipped. Lint,
  formatting and synthetic workbook generation passed, including lineage/profile isolation,
  name-only ambiguity, provenance links, rerun history and workbook affiliation columns.
- Remaining owner TODOs: review institution scope, IBM watchlist/common names, collaboration
  scope and recall. A new GitHub run is required to regenerate live master evidence.

## 2026-11-13 — New generated master workbook (owner-authorized scope)

- Added master_export.py: `--xlsx` creates a new master_<date>.xlsx with the approved
  36-column Publications table, full-history Sources table, public hyperlinks, wrapped
  text, frozen headers, date/ID formatting and usage notes. It includes all canonical
  papers even on a zero-candidate rerun and refuses to overwrite an existing export.
- Public metadata/all authors are filled. Manual count/SOW/theme/involvement columns and
  unverified individual IBM/partner author splits stay blank. Scope uncertainty, duplicates,
  corrections/retractions and prior exclusions are flagged instead of silently decided.
  AUTO IDs derive from history keys, not existing master IDs; fresh backfills reset them.
- Fixed Crossref-confirmed preprint DOIs misclassified as published through arXiv's DOI
  field. Explicit registry evidence can correct that prior inference while separate journal
  evidence remains published. Added PubMed/OpenAlex fallback links to paper exports.
- GitHub artifacts now include the new master workbook alongside candidate Excel/CSV and
  the public snapshot. No input workbook or manual/private data is copied or modified.
- Validation: 197 offline tests passed, 2 optional recordings skipped; lint, formatting,
  synthetic dry run and generated-master fixture backfill passed. Tests cover full-history
  reruns, input immutability, formula-safe text, hyperlinks, review flags and no overwrites.
- Existing owner TODOs remain: institution scope, IBM watchlist/common names and real-world
  recall. No new dependencies, institution IDs or matching thresholds were introduced.

## 2026-11-13 — Crossref absence during live backfill

- GitHub run 43476018062 verified both repository secrets, passed all three fresh live
  source tests, and discovered 196 candidate papers. Collection was marked partial because
  29 DOI enrichment requests returned Crossref HTTP 404; 129 enrichments succeeded.
- Treat a DOI absent from Crossref as unavailable optional enrichment, retain its source
  metadata, and count it in crossref.skipped.not_found. Other errors remain lane failures;
  transient errors retain their retry behavior. No new dependencies or thresholds.
- Added adapter and end-to-end regression coverage for absent DOI metadata versus forbidden
  requests/service outages, including retained papers, generated Excel and run diagnostics.
- Local validation: 193 passed, 2 optional recordings skipped; lint and formatting clean.
  A new Actions run on the updated main branch is needed to verify the live backfill fix.

## 2026-11-13 — Manual GitHub public-source Excel generation

- Added `.github/workflows/candidates.yml` with manual dispatch, read-only repository
  permissions, dependency/lint/format/offline checks, a synthetic dry run, fresh live source
  recordings and public-source backfill with `--no-master --xlsx`.
- Credentials are injected only from repository secrets into live steps. Artifacts contain
  generated candidate Excel/CSV and public work snapshots, not secrets, logs, raw responses,
  recordings, databases or master workbooks. Retention is 14 days.
- Documented Actions launch/download steps and the fresh-history limitation: each run is a
  full backfill, not a persistent incremental weekly monitor. Failed/partial collection is
  shown as failure and any produced files are explicitly labeled incomplete.
- Workflow syntax and embedded Python checked locally; offline suite, synthetic dry run,
  lint and formatting passed. Live GitHub execution must verify the repository secrets.

## 2026-11-13 — Offline verification and initial online checks

- Installed the declared development dependencies in a local virtual environment;
  dependency consistency, Ruff lint, formatting and whitespace checks passed.
- Initial offline suite: 188 passed, 3 optional recordings skipped. The synthetic CLI
  fixture dry-run completed with 3 papers/candidates, no persistent runtime directories,
  and a byte-identical synthetic master. The real workbook was never accessed.
- Recorded the credential-free arXiv known-ID source test successfully and inspected its
  cassette: public metadata only, no API-key/contact query fields or authorization/User-Agent
  headers. Fixed the recording fixture's existence check to include pytest-recording's
  `.yaml` suffix; previously even an available cassette was silently skipped on replay.
- Final network-blocked suite: 189 passed, 2 skipped. The new arXiv cassette now replays
  offline. Reproduce with `python -m pytest -o addopts='' -q --block-network`,
  `ruff check .`, `ruff format --check .`, and `python -m pip check`.
  Reproduce the synthetic run with `pubmon run --dry-run --master
  tests/fixtures/synthetic_master.xlsx --fixtures tests/fixtures/api`.
- Public HTTPS probes returned HTTP 200 from OpenAlex and Crossref. The configured Clinic
  title/abstract quantum filter returned 89 works with a one-record page, confirming filter
  acceptance (not full pagination or relevance). Crossref returned the expected public DOI.
- Blocked: OpenAlex/Crossref source-recording tests and a complete live pipeline rehearsal,
  because OPENALEX_API_KEY and PUBMON_EMAIL are absent. Set them through environment settings
  before `python -m pytest tests/test_source_recordings.py --record-mode=once`.
  No credential values were printed or invented. No changes were pushed to GitHub.
- Existing owner decisions remain: institution scope, IBM-side public watchlist authors,
  common-name collisions, real-world recall on the approved machine, and weekly validation.
  No new dependencies, matching thresholds or source behavior were introduced.

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

## 2026-11-12 — Milestone 5

- Implemented read-only master reconciliation with exact headers, an allowed-column
  projection, identifier and guarded authors/date matching, and ZIP relationship hyperlink
  fallback. Never opened an editable handle to the input workbook or saved it.
- Added grouped CSV/Excel review exports and complete work snapshots. Every paper has one
  row containing all pending eligible events/changes and both version IDs. Protected manual
  fields are absent. Same-day review files are preserved using run-suffixed filenames.
- Added full run, dry-run, backfill, no-master, master override, Excel, status and local
  decision-import commands. Explicit --fixtures replay makes the entire CLI testable offline.
- Added source collection/failure isolation, Crossref enrichment caching, raw archives,
  consistent SQLite backups, correction/retraction linking, and run-scoped console/file logs.
- Added approved merges with old-key aliases, retained identifiers/source records/events,
  and idempotent review import. Rejection suppression allows only later material changes.
- Corrected copied synthetic fixture IDs that accidentally made unrelated fixture papers
  share identities. Added a generator that writes new synthetic workbooks only.
- Strengthened notice caching and retained retraction status across stale source refreshes.
  Dry runs use a disposable history copy, leaving the original database and outputs unchanged.
- Offline acceptance checks cover all 17 named SPEC §14 cases, including one row per paper,
  multiple changes in one row, rate limits/outages, manual-cell spying, workbook byte identity,
  pending-event recovery and explicit merge/re-import behavior. Live API recordings remain
  optional and unrun; full back-testing/README completion remains Milestone 6.
- Final validation: 163 passed, 3 optional live-recording tests skipped; lint, format,
  dependency and Git whitespace checks passed. Both explicit fixture dry-run commands
  completed with 3 paper rows and no persistent database/output files in this checkout.
- Isolated non-dry synthetic replay under ignored demo/ with explicit --demo status/review
  selection, so fixture runs cannot contaminate live data/pubmon.db or live output files.

## 2026-11-12 — Milestone 6

- Added `pubmon backtest --master PATH --since YYYY-MM-DD [--demo]` and `backtest.py`.
  Reports tracker-row recall, found/missing/ambiguous IDs, and explicit exclusions; prints
  misses with Pub ID/Name and writes a new BOM CSV without overwriting a prior report.
- Reused identifier/guarded authors-date matching. Preprint and journal master rows can
  resolve to one paper identity; the diagnostic denominator is eligible rows, not an official
  publication count. Empty eligible scope reports null recall, not a false perfect score.
- Added read-only SQLite Store mode, including safe reading of pre-migration history;
  back-testing never migrates or updates the history database. Input byte identity is tested.
- Replaced the scaffold README with a Windows PowerShell beginner guide covering installation,
  offline demos, secure environment variables, settings/watchlists, institution lookup,
  backfill, weekly review/import, back-testing and data boundaries. Native Windows execution
  remains unverified; equivalent installed CLI workflows were exercised on Linux.
- Added docs/V1_REVIEW.md mapping all five hard rules and 17 acceptance cases to code/tests,
  and refreshed START_HERE/work-plan status. All six implementation milestones are complete.
- Validation: 174 offline tests passed, 3 optional live-recording tests skipped; Ruff lint
  and formatting, dependency and whitespace checks passed. Independent installed-CLI replay
  plus back-test wrote 11 diagnostic rows, preserved database/workbook bytes and prior reports.
- The demo API fixture corpus intentionally does not cover the synthetic master: its zero
  recall is a reporting smoke result, not live performance. Controlled-history tests verify
  five found eligible rows out of nine and exercise exclusions, cutoffs and ambiguity.
- No new TODO(owner) decisions. Live API configuration/queries, institution/watchlist review,
  real-master recall and two weekly validation runs remain outstanding. The owner deferred
  live account/mailbox setup; no live requests were made during this milestone.

## 2026-11-12 — Consolidated partner customization

- Made config/settings.toml the complete collaboration profile, with public CCF defaults for
  names/labels, institution IDs, dates, keywords, inline query/watchlist, matching, workspace
  and master path. The proven CCF query and 16 public feed entries were preserved.
- Kept secrets/contact email in .env/environment bindings; configured the owner's supplied
  contact privately without putting the address or a key into tracked files.
- Added generic partner institution lookup and IBM/PARTNER watchlist sides. Legacy CC IDs,
  query/watchlist files and CSV side CC remain supported; contradictory inputs fail clearly.
- Added configurable runtime workspaces so different QICs can keep separate histories,
  outputs and reviews. Default CCF storage remains unchanged; CLI status/import/back-test
  follow the profile workspace. The existing approved workbook layout is still required.
- Added docs/CUSTOMIZATION.md and updated README/spec/security guidance. No new dependencies,
  institution IDs or author guesses were introduced. Live API validation remains deferred.
- Validation: 188 offline tests passed, 3 optional live-recording tests skipped; lint,
  formatting, dependency checks and a complete CCF fixture dry-run passed. Both local private
  files are git-ignored; the supplied contact value is excluded from the staged changes.
