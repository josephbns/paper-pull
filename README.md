# pubmon

A publication monitor for the IBM–Cleveland Clinic collaboration, under development.
Final exports will have **one row per paper**, combining preprint and journal identifiers.

Milestones 1–5 provide the complete run/review pipeline: public discovery, matching,
read-only master reconciliation, one-row-per-paper exports, decisions and history.
The back-test command and full beginner walkthrough arrive in Milestone 6.

## Development quick start (Python 3.11+)

```bash
cd /workspace/paper-pull
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest -q
ruff check .
ruff format --check .
pubmon --help
```

On Windows PowerShell activate with `.venv\Scripts\Activate.ps1` instead.
Tests use synthetic inputs and make no network calls. Package installation needs Internet.
No API credentials are needed for this milestone.

Settings load from `config/settings.toml`, falling back to `config/settings.example.toml`.
Paths inside TOML are relative to the project directory supplied to `load_config()`.
Credentials come from process variables, then a git-ignored `.env`; network commands will
validate them when implemented. Never commit keys, contact emails, real workbooks or outputs.

The build pack's statements that GitHub is unavailable are superseded by the owner's
instruction to use `josephbns/paper-pull`. Its bundled Git history was not imported.
See `docs/SPEC.md`, `docs/WORK_PLAN.md` and `CODEX_PROMPT.md` for the remaining milestones.
A complete beginner guide arrives in Milestone 6.

## History database (Milestone 2)

`Store` in `src/pubmon/store.py` opens `data/pubmon.db` by default. This local state remains
ignored by Git. Every write must run inside `with store.transaction():`; a failure rolls
back the entire block. Nested transactions are rejected so a helper cannot commit part of
a larger operation by accident.

The store retains paper summaries, identifiers, latest source records, audit events, runs,
and decision history. Identifier or source-identity conflicts raise `IdentifierConflict`;
the caller must send them for review rather than silently reassigning a paper's identity.
Merge decisions are recorded here; applying them arrives with decision import in Milestone 5.

Run the history tests without API access:

```bash
pytest -o addopts='' -q --disable-recording --block-network tests/test_store.py
```

Two engineering concepts to look for:

- **Atomicity:** `Store.transaction()` makes a batch of writes succeed or fail together.
  `test_interrupted_run_safe` verifies the database file is byte-identical after failure.
- **Idempotency:** `Store.upsert_identifier()` keeps one identifier row when called repeatedly.
  `Store.store_decision()` similarly avoids duplicating an unchanged review decision.

## Source adapters (Milestone 3)

- `sources/openalex.py`: `fetch_pair()` and `fetch_clinic_quantum()` return normalized Work
  lists, checking unique fetched counts against OpenAlex metadata for each query. Pair
  combinations are unioned by OpenAlex ID; dataset/software records are counted and skipped.
- `sources/arxiv_src.py`: `fetch_feed()` uses the saved query verbatim; `recheck()` refreshes
  known IDs in batches of 100, even when they are older than the weekly window. Backfill
  sorts by submission date so the start-date stopping condition is safe.
- `sources/crossref.py`: `enrich()` returns DOI publication fields, preprint relations and
  correction/retraction links. Only HTTP 429 and 5xx errors are retried, up to five attempts.
- `sources/common.py`: `FetchReport` holds source records, skip counts and notices for later
  pipeline wiring. `LaneFailed` distinguishes failure from an empty successful search;
  errors omit underlying request URLs, which may contain credentials.

Correction/retraction notices are separated from normal papers. Linking their Crossref
`update-to` targets to stored originals and writing audit events arrives in the later pipeline.
A Crossref response with only a year or month does not invent an exact publication date.

### Institution lookup (live, optional during development)

After setting `OPENALEX_API_KEY` and `PUBMON_EMAIL` securely in your process environment:

```bash
pubmon resolve-institutions "Cleveland Clinic" "IBM"
```

This prints candidate IDs, names, ROR, country, work counts and lineage. It never edits
settings. The supplied parent institution IDs remain defaults; extra entities are an owner
scope decision. Before feed collection, copy `config/watchlist.example.csv` to the ignored
`config/watchlist.csv` and review it. The example currently supplies Clinic-side names only;
provide IBM-side public author names to enable arXiv IBM confirmation.

### Recording real public responses (optional)

All adapter tests use hand-written fixtures; **live API behavior is not yet verified**.
Three optional tests in `tests/test_source_recordings.py` are skipped until cassettes exist.
On a machine with the API destinations allowed and environment credentials configured, run
this exact command from the repository root:

```bash
python -m pytest tests/test_source_recordings.py --record-mode=once
```

The destinations are `api.openalex.org`, `export.arxiv.org`, and `api.crossref.org`.
`tests/conftest.py` removes API-key/contact query parameters and authorization/User-Agent
headers before cassette writes. Inspect recordings for secrets before committing them.
After recording, `pytest -q` replays them with network blocked and without real credentials.
Use `pytest -q --disable-recording` to explicitly omit the optional recording checks.

Two concepts to learn here:

- **Adapters:** `openalex.fetch_pair()` and `arxiv_src.fetch_feed()` translate different APIs
  into the same Work model. Matching code can use that model without knowing each API format.
- **Failure isolation:** `common.lane_guard()` raises a safe `LaneFailed` instead of returning
  an empty list after an outage. Later pipeline code can record that failure and continue
  other lanes without interpreting missing results as deleted papers.

TODO(owner): verify the Clinic title/abstract filter live, review extra institution scope,
add public IBM watchlist names, and identify ambiguous names. These do not block offline
matching development in Milestone 4.

## Matching and changes (Milestone 4)

`match.resolve_and_store()` processes a batch of normalized Work objects in one transaction.
It uses shared identifiers first, then DOI links, then guarded fuzzy matching; otherwise it
creates a new stable UUID. Conflicting IDs and ambiguous matches remain separate and gain a
POSSIBLE_DUPLICATE event. Fuzzy matches must pass every configured title, author, year and
number guard, including decimal numbers and Roman-numeral part labels.

Each source snapshot is retained separately from the canonical paper state. Published
metadata takes precedence over preprint metadata. Changes are compared once per paper after
the batch, so rerunning a mixed preprint/journal batch does not generate alternating updates.
Individual events remain in the audit trail; grouping them into one output row is Milestone 5.
The run must already exist in the store before calling the batch function.

Supply `raw_records` keyed by `(Source, normalized_source_id)` when original API responses
are available. For normalized-only callers, a clearly labelled normalized snapshot is kept
instead; an unchanged source's existing original response is preserved.

The additive migration keeps existing work IDs, raw responses and identifiers. Databases
created before Milestone 4 gain nullable snapshot columns; normalized author/title evidence
becomes available when those records are fetched again. Missing legacy evidence is never
used to justify a fuzzy merge.

Run the complete offline checks from the activated environment:

```bash
pytest -o addopts='' -q --block-network
ruff check .
ruff format --check .
python -m pip check
```

Two concepts to learn:

- **Canonical state:** `diff.canonical_state()` selects one current view from multiple source
  versions. Retaining the originals lets the matcher compare earlier titles and identifiers.
- **Determinism:** `diff.material_changes()` compares a fixed set of meaningful fields.
  `match.resolve_and_store()` compares once per paper per batch, avoiding duplicate updates
  caused by source ordering.

No new owner decisions block Milestone 5. Live API checks, watchlist review and institution
scope remain outstanding as documented above.

## Run and review (Milestone 5)

From the repository root with the virtual environment activated, this **offline** smoke run
uses only the supplied synthetic fixtures and leaves the real database and exports unchanged:

```bash
pubmon run --dry-run --master tests/fixtures/synthetic_master.xlsx --fixtures tests/fixtures/api
```

For an offline run without workbook reconciliation:

```bash
pubmon run --dry-run --no-master --fixtures tests/fixtures/api
```

`--fixtures` is explicit: it never falls back to an API. Non-dry fixture runs keep history
and outputs under ignored `demo/`, completely separate from live `data/` and `out/`. Removing it selects live collection,
which requires environment credentials, API access and a reviewed local watchlist. Fixture
replay uses the fixture's latest arXiv update as its replay clock; it is not a live search.

To inspect real generated synthetic outputs, omit `--dry-run` and optionally add `--xlsx`:

```bash
pubmon run --no-master --fixtures tests/fixtures/api --xlsx
pubmon status --demo
pubmon import-decisions --demo demo/out/your_reviewed_file.csv
```

Each candidate row contains one `work_key`, both preprint/journal identifiers when linked,
distinct event kinds, and all field changes in its `changes` cell. Uncertain matches stay
separate with `possible_duplicate_of`. A `works_<date>.csv` snapshot includes every paper once.
CSV files include a UTF-8 BOM and `arXiv:` prefixes; optional Excel exports format IDs as text.
Repeated runs on the same day append the run ID to filenames rather than overwrite prior
review files. Existing candidate files, even if edited, are never re-saved by the application.

Fill only `decision` and `reviewer_note` in a copy of the candidate CSV, then import it.
Decisions are `accepted`, `rejected`, `not_collab`, or `merge:<target_work_key>`; invalid rows
are reported and skipped. An approved merge preserves identifiers/history and records aliases
so re-importing the old source key is harmless. Rejected candidates return only after a later
material change. A merge records identity approval; it is not a counting-policy decision.

Master inputs must have the documented headers and unique Pub IDs. Only approved columns are
accessed; ID hyperlinks are read from ZIP relationships with no editable workbook handle.
Matching uses identifiers, then authors/date for rows lacking identifiers; `Name` is display
only. If two existing master rows represent preprint and journal versions, their Pub IDs are
listed together on the single output row. Manual columns are never copied to outputs.

Real master reconciliation and reviewer decisions remain local to an approved IBM machine.
Development here uses only public metadata and synthetic data. All `data/` and `out/` files
remain ignored by Git.

The pipeline makes a consistent SQLite backup before a normal run. Dry runs use a temporary
copy of history and discard their database changes, raw archives, logs and generated rows.
Source failures are recorded as `partial` with CLI exit code 2; other sources continue.
Failed matching rolls back its whole transaction and records a failed run separately.
Files are renamed atomically before export markers are committed. A file-write failure leaves
its events pending for retry; do not review output from a run reported as failed.

Two engineering concepts:

- **Projection:** `master.read_master()` accesses an explicit allowlist of fields.
  The manual-column spy test fails if the reader accesses a protected data cell.
- **Grouping:** `export.group_by_work()` retains each audit event under one paper key.
  `candidate_rows()` converts that group to one row carrying all changes and version IDs.

Live API checks remain unrun. Offline fixture/acceptance checks do not establish real-world
recall; the Milestone 6 back-test will provide the tool for that later validation.
