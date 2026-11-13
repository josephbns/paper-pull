# pubmon V1 — technical specification

Status: V1 implemented; live validation pending · Owner: Joe · Last updated: 2026-11-12

V1 is one command, `pubmon run`, that pulls candidate papers from OpenAlex and arXiv,
enriches them by DOI from Crossref, matches them against its own history and the master
workbook, and writes `out/candidates_<YYYY-MM-DD>.csv` containing **only** new, changed or
uncertain papers, **one row per paper**. It never writes to the master workbook.

**One row per paper (owner requirement, 12 Nov).** A preprint and its journal version are
one paper: they share one row that carries both identifiers. Several changes to the same paper
in one run stay on that one row. Uncertain matches are never merged; they get their own row
with a flag pointing at the possible match. The database still keeps every individual event as
an audit trail; only the output is grouped.

---

## 1. Scope

Owner-authorized addition (2026-11-13): `--xlsx` also generates a **new**
`out/master_<date>.xlsx` from all canonical public history. Its Publications sheet uses
the 36-column master layout, with Sources and Read me sheets for provenance/limitations.
It never updates or copies the existing master. Internal/manual columns and unverified
per-author affiliation splits stay blank; all known authors appear in Authors. Uncertain
scope/duplicates and correction/retraction events stay flagged. AUTO IDs derive from
history work keys and are not existing master Pub IDs; fresh backfills assign new IDs.
Crossref's explicit preprint classification overrides publication inferred from that same
DOI on arXiv, including correction of a previously inferred published state. Separate
journal-publication evidence continues to establish published status.

Owner-authorized evidence addition (2026-11-13): the original 36 columns remain first;
selection rationale, discovery routes, partner author/institution evidence, IBM institution
evidence, separate watchlist matches, evidence links and evidence status follow them.
IBM Authors and CC and other Authors contain only OpenAlex-reported authorship affiliations
matching configured IBM/partner institution IDs or lineage. Other authors remain in Authors.
An Affiliation evidence sheet records author, side, institution name/ID, matched configured
ID, evidence basis and source publication link. Watchlist name matches, including common-name
ambiguity, remain distinct from source-reported affiliation. Query inclusion alone does not
verify either side or partnership membership. Evidence covers stored linked versions and
survives reruns without extra API calls; missing original routes are reported as unavailable.

**In V1:** three discovery lanes (§4), Crossref enrichment, identity matching (§7), SQLite
history (§5), read-only master reconciliation (§8), candidate CSV (§9), decision import (§10),
CLI (§11), offline tests (§14).

**Not in V1:** PubMed/Europe PMC, Slack, scheduling, GitHub Actions, writing Excel, LLMs,
relevance scoring, citation discovery. See `docs/WORK_PLAN.md` for when these arrive.

## 2. Hard rules

1. The master workbook is opened read-only and never saved, moved or renamed.
2. Manual columns (see `docs/MASTER_COLUMNS.md`) are never read or output.
3. Keys and emails come only from environment variables.
4. Tests run offline; recordings are scrubbed of keys.
5. Only public metadata and synthetic fixtures live in the repository.

## 3. Architecture

```
            ZONE 1 — public metadata only (laptop now; approved scheduler later)
 ┌──────────────────────────────────────────────────────────────────────────────┐
 │  OpenAlex (lanes A, B)   arXiv (lane C + weekly re-check)   Crossref (DOI)    │
 │          └──────────────┬─────────────────┘                     │            │
 │                         ▼                                       ▼            │
 │   Fetch (+retries, raw JSON saved) → Normalize → Match + dedupe → History DB  │
 └───────────────────────────────────────────────────────────────────┬──────────┘
                                                                     │ public records only
            ZONE 2 — IBM machines only (internal data)               ▼
 ┌──────────────────────────────────────────────────────────────────────────────┐
 │  Master workbook (read-only) → Reconcile → Candidates CSV → Human review      │
 │                                    ▲                              │           │
 │                                    └──── decisions (import) ──────┘           │
 └──────────────────────────────────────────────────────────────────────────────┘
```

In V1 both zones run on one machine with one command. The split exists so Zone 1 can move to a
scheduler later without moving internal data. Code for Zone 2 lives in `master.py`,
`export.py` and the decisions part of `store.py`.

## 4. Discovery lanes

Every lane respects `start_date` from settings (default `2021-01-01`). The collaboration's
paper set is small, so lanes A and B **re-pull everything since `start_date` every run** and
diff locally. Do not use OpenAlex `from_updated_date` / `from_created_date`; those filters
need a paid plan.

| Lane | Source | Query | Confidence | Why it exists |
| --- | --- | --- | --- | --- |
| A `pair` | OpenAlex | works with ≥1 author affiliated with an IBM institution **and** ≥1 with a Cleveland Clinic institution | high | Core definition of a collaboration paper |
| B `clinic_quantum` | OpenAlex | works with a Cleveland Clinic affiliation **and** a quantum term in title/abstract | review | The tracker counts some Clinic-only quantum papers with no IBM author |
| C `arxiv_feed` | arXiv | the query built from the profile's partner people, phrases and topic terms (it keeps every clause of the owner's original feed) | review unless an IBM watchlist author is present | Fastest source for preprints |

### Lane A — OpenAlex pair query

```python
import pyalex
from pyalex import Works

pyalex.config.api_key = os.environ["OPENALEX_API_KEY"]
pyalex.config.email = os.environ["PUBMON_EMAIL"]
pyalex.config.max_retries = 3  # default is 0 — do not skip this
pyalex.config.retry_backoff_factor = 0.5

q = (
    Works()
    .filter(authorships={"institutions": {"lineage": [ibm_id, cc_id]}})  # list → "+" → AND
    .filter(from_publication_date=start_date)
)
for page in q.paginate(per_page=200, n_max=None):
    ...
```

- A Python list in a PyAlex filter is joined with `+`, which OpenAlex treats as AND for the
  same attribute (verified in PyAlex source, `_flatten_kv`). **Verified live on 12 Nov 2026:**
  `authorships.institutions.lineage:I1341412227+I1316902750` with
  `from_publication_date:2021-01-01` returned 92 works, so a full re-pull is one or two pages.
- Settings may hold several IDs per side. Run one query per (IBM id × CC id) pair and union
  results by OpenAlex ID.
- Compare the number of works fetched with `meta.count` of the first page. If they differ,
  mark the lane failed for this run (§12).

### Lane B — OpenAlex Clinic + quantum

```python
q = (
    Works()
    .filter(authorships={"institutions": {"lineage": cc_id}})
    .search_filter(
        title_and_abstract=" OR ".join(settings.quantum_terms)
    )  # title_and_abstract.search
    .filter(from_publication_date=start_date)
)
```

- Terms come from the profile's `[topic] terms` (older format: `quantum_terms`). OpenAlex
  rate-limits searches with more than five boolean operators, so terms are sent in groups of
  at most five (one query per group and partner ID, results combined by OpenAlex ID), with
  multi-word terms quoted as exact phrases (`term_searches()` in `sources/openalex.py`).
- Set `ibm_confirmed = True` only if an IBM institution ID appears among the work's
  authorships; otherwise `False`. Never drop a work for lacking IBM.
- **Do not use the `search=` parameter.** It searches full text: on 12 Nov 2026 it returned
  246 Clinic works for "quantum", about half unrelated (clinical papers, datasets, software).
- `TODO(owner)`: confirm `title_and_abstract.search` works with one live call in milestone 3.
  Sanity check: the count should be well under 246. If the filter is rejected, use
  `title.search` instead.

### Lane C — arXiv feed

```python
import arxiv

client = arxiv.Client(page_size=100, delay_seconds=3, num_retries=3)  # arXiv: ≤1 request / 3 s
search = arxiv.Search(
    query=query_from_file,
    sort_by=arxiv.SortCriterion.LastUpdatedDate,
    sort_order=arxiv.SortOrder.Descending,
)
```

- Weekly run: stop paging once a result's `updated` date is older than `arxiv_window_days`
  (default 90).
- `pubmon run --backfill`: sort by `SubmittedDate` descending, then stop once `published`
  is older than `start_date`. Sorting by last update here could stop at an old recently
  updated paper before reaching newer papers. (The current
  query pulls collaborators' whole careers; the start date is what keeps old papers out.)
- For each hit, record which watchlist names matched its authors (`matched_names`). If every
  matched name is listed in `arxiv.common_names`, set `confidence = uncertain`.
- `ibm_confirmed = True` only if an IBM-side watchlist name matched.

### Weekly arXiv re-check

Every run, re-fetch every arXiv ID already in the database with
`arxiv.Search(id_list=[...])` in batches of 100. This is how a preprint that later gains a
`doi` or `journal_ref` gets noticed; sorting alone does not surface metadata edits.

### Work types

The live pair query returns more than papers. Handle types (OpenAlex `type`) like this:

| Type | Handling |
| --- | --- |
| `article`, `preprint`, `review`, `conference-paper`, `letter`, `book-chapter` | Normal papers |
| `conference-abstract` | Normal, but `confidence = review` (the master tracks some, not all) |
| `erratum`, `retraction` | **Never a new paper.** Find the original through Crossref `update-to` on the notice's DOI and write a `CORRECTION` or `RETRACTED` event on the original's row. If the original can't be found, log it and skip |
| `dataset`, `software`, `paratext`, `peer-review`, `grant`, `supplementary-materials`, `editorial`, `report`, `other` | Skip and count in the run log (`skip_types` in settings) |

### Crossref enrichment

For DOIs that are new or whose source record changed:
`habanero.Crossref(mailto=EMAIL).works(ids=doi)`. Read `container-title`, `published`,
`type`, `update-to` (retractions/corrections) and `relation` (`has-preprint`,
`is-preprint-of`). Wrap in tenacity retries. A missing DOI is normal, not an error.

## 5. Data model

### `Work` (one normalized record from one source)

| Field | Type | Notes |
| --- | --- | --- |
| `source` | str | `openalex` / `arxiv` / `crossref` |
| `source_id` | str | OpenAlex W-id, arXiv id, or DOI |
| `lane` | str | `pair` / `clinic_quantum` / `arxiv_feed` / `recheck` |
| `title`, `title_norm` | str | `title_norm` per §7 |
| `pub_date`, `year` | str, int | ISO date |
| `type` | str | `preprint` / `article` / `proceedings` / `other` |
| `venue` | str \| None | |
| `doi`, `arxiv_id`, `pmid`, `openalex_id` | str \| None | normalized (§7) |
| `extra_dois` | list[str] | other DOIs seen (e.g. OpenAlex locations) |
| `journal_ref` | str \| None | arXiv only |
| `authors` | list[dict] | `name`, `orcid`, `institution_ids` |
| `ibm_confirmed` | bool | |
| `matched_names` | list[str] | arXiv lane only |
| `confidence` | str | `high` / `review` / `uncertain` |
| `is_retracted` | bool | |
| `raw_hash` | str | SHA-256 of the raw JSON |

### SQLite (`data/pubmon.db`, via sqlite-utils)

`works.state_json` retains the canonical normalized paper state; `source_records.normalized_json`
retains each source version for author/title comparisons. They are separate from untouched raw
response JSON. Both are nullable additive columns so pre-matching databases migrate without
losing rows or identifiers. Legacy records acquire normalized snapshots when re-fetched.

```sql
works(work_key TEXT PRIMARY KEY,      -- uuid4
      title TEXT, year INT, venue TEXT, type TEXT, status TEXT,   -- status: preprint | published
      ibm_confirmed INT, best_confidence TEXT,
      first_seen TEXT, last_changed TEXT, state_json TEXT)  -- canonical normalized state
identifiers(scheme TEXT, value TEXT, work_key TEXT,
      PRIMARY KEY (scheme, value))    -- schemes: doi, arxiv, pmid, openalex. Enforces one record per paper.
source_records(source TEXT, source_id TEXT, work_key TEXT, lane TEXT,
      fetched_at TEXT, raw_json TEXT, raw_hash TEXT, normalized_json TEXT,
      PRIMARY KEY (source, source_id))
events(event_id INTEGER PRIMARY KEY, run_id TEXT, work_key TEXT,
      kind TEXT,                      -- NEW | UPDATED | LINKED_PREPRINT | POSSIBLE_DUPLICATE | CORRECTION | RETRACTED
      field TEXT, old TEXT, new TEXT, created_at TEXT,
      exported_in_run TEXT NULL)
decisions(work_key TEXT, decision TEXT, decided_at TEXT, note TEXT)
      -- decision: accepted | rejected | not_collab | merge:<work_key>     (Zone 2)
runs(run_id TEXT PRIMARY KEY, started_at TEXT, finished_at TEXT,
      status TEXT, counts_json TEXT)  -- per-lane counts and failures
work_aliases(alias TEXT PRIMARY KEY, work_key TEXT REFERENCES works(work_key)) -- approved merges
```

## 6. Pipeline for `pubmon run`

1. Copy `data/pubmon.db` to `data/pubmon.db.bak`. Create a `run_id` (UTC timestamp).
2. **Fetch** lanes A, B, C and the arXiv re-check. Save raw responses to
   `data/raw/<run_id>/<lane>.json`. A lane that fails after retries is logged, recorded in
   `runs`, and skipped; its absence never marks works as deleted.
3. **Normalize** to `Work` (§7).
4. **Enrich** with Crossref (§4).
5. **Resolve and store — one transaction for the whole step.** For each `Work`, find its
   `work_key` (§7), upsert identifiers and the source record, and diff material fields
   against what is stored. Material fields: `doi`, `venue`, `pub_date`, `type`, `status`,
   `is_retracted`, `journal_ref`. Write events. A preprint gaining a journal version writes
   `LINKED_PREPRINT` and an `UPDATED` event for `status`.
6. **Reconcile with the master** (skip with `--no-master`; §8).
7. **Suppress** events for works whose latest decision is `rejected` or `not_collab`, unless
   a material field changed after the decision date.
8. **Export** unexported, unsuppressed events, **grouped into one row per work** (§9): write to
   a temp file, `os.replace` it into place, **then** set `exported_in_run` on every event that
   went into a row. A crash before the rename means the next run re-exports the same events.
   Nothing is lost and nothing repeats. Also write the full snapshot `out/works_<date>.csv`.
9. Log a one-screen summary: counts per lane and per event kind, failures, output path.

## 7. Identity matching

### Normalization

- DOI: `idutils.normalize_doi`, lowercased.
- arXiv: `idutils.normalize_arxiv`, then strip any `vN` suffix and any `arXiv:` prefix.
- PMID: `idutils.normalize_pmid`.
- OpenAlex: keep the `W…` id only (drop the URL prefix).
- `title_norm`: Unicode NFKD → ASCII, lowercase, strip LaTeX (`$…$`, `\textsf{}`) and HTML
  tags, replace punctuation with spaces, collapse whitespace.
- Author surname: last token of the normalized name, ignoring suffixes (`jr`, `sr`, `ii`, `iii`).

### Resolution order (first rule that fires wins)

1. **Shared identifier.** Any of the work's identifiers already in `identifiers` → that
   `work_key`.
2. **Link clues.** arXiv `doi` field; DOI parsed from arXiv `journal_ref` when present;
   `extra_dois` from OpenAlex locations; Crossref `has-preprint` / `is-preprint-of`.
   Any clue pointing at a known identifier → that `work_key`.
3. **Fuzzy title.** Compare `title_norm` with `rapidfuzz.fuzz.token_sort_ratio` against works
   from the same ±4 years.
   - **Auto-link** only if score ≥ `auto_link` (default 95) **and** first-author surnames match
     or ≥ 2 surnames are shared **and** (later year − earlier year) is between −1 and +3
     **and** the sets of numbers in both original titles are identical. Extract numbers before
     removing punctuation so `1.2` and `2.1` cannot become the same token set; include Roman
     `Part I` / `Part II` labels in the guard.
   - Score in [`review`, `auto_link`) (default 85–95): create a new work and write
     `POSSIBLE_DUPLICATE` pointing at the near match. **Never auto-merge in this band.**
4. Otherwise: new work, `NEW` event.

A stable provider source identity also anchors re-fetched records with no external IDs.
Contradictory IDs, link clues pointing to different works, or multiple qualifying fuzzy
matches require review; never silently merge the existing identities or transfer their IDs.
High title similarity that fails an author/year/number guard is also kept separate for review.

Compare the canonical before/after state once per paper after the whole batch. Prefer
published metadata (Crossref, then OpenAlex, then arXiv) and retain known nonempty metadata
when responses omit it. A stale preprint must not downgrade a known journal publication.
The fuzzy year window means journal year minus preprint year; for equal publication types,
use absolute year distance. No scoring thresholds are changed by these clarifications.

Thresholds live in `config/settings.toml`. They are starting points (borrowed from
Crossref's own preprint matcher), not tuned values.

## 8. Master workbook (read-only)

The header row is fixed; see `docs/MASTER_COLUMNS.md` for all 36 names in order.

- Open with `load_workbook(path, read_only=True, data_only=True)`. Validate that every
  expected header is present; if not, fail with a message naming the missing columns.
- Read **only**: `Name`, `Type of Paper`, `Publication or Conference (short name)`,
  `Pub Status`, `Date of Publication`, `IBM Authors`, `CC and other Authors`, `Title`,
  `Status`, `arXiv`, `PubMed`, `DOI`, `OpenAlex ID`, `Pub ID`, `Same work as`.
- ID cells are text. If a cell's text is only a label (`arXiv`, `PubMed`, `DOI`, `—`), read
  the ID from the cell's hyperlink target instead. In read-only mode openpyxl does not load
  hyperlinks, so read sheet hyperlink attributes and ZIP relationship targets directly.
  This avoids opening a normal workbook that would materialize manual cells; no save path
  exists in the reader.
- **Matching a candidate to a master row:**
  1. Any shared DOI, arXiv ID or PMID → match (`match_method = id`).
  2. Else, for rows with no IDs: ≥ 2 shared author surnames (from `IBM Authors` +
     `CC and other Authors`, comma-separated) **and** `Date of Publication` within 30 days
     (`match_method = authors+date`).
  3. Else no match.
- **Never match on `Name`.** It is a composed label (`"Venue: nickname, date"`), not the
  paper's title.
- Rows whose `Type of Paper` is a talk, poster or short paper are rarely indexed anywhere;
  that is expected.

## 9. Candidate file

### Candidates: `out/candidates_<YYYY-MM-DD>.csv` — one row per paper

UTF-8 with BOM (opens cleanly in Excel). **Exactly one row per `work_key`** that has
unexported, unsuppressed events. Columns, in order:

```
candidate_id, work_key, events, lanes, confidence, ibm_confirmed, title, pub_date, status,
venue, type, doi, arxiv_id, pmid, openalex_id, versions, first_author, n_authors,
matched_names, changes, possible_duplicate_of, master_pub_id, match_method, sources,
first_seen, link, decision, reviewer_note
```

| Column | Rule |
| --- | --- |
| `candidate_id` | `<run_id>-<first 8 chars of work_key>` |
| `events` | Distinct event kinds for this paper, in a fixed order: `NEW, LINKED_PREPRINT, UPDATED, CORRECTION, RETRACTED, POSSIBLE_DUPLICATE` |
| `lanes` | Every lane that found the paper this run, e.g. `pair; arxiv_feed` |
| `confidence` | The most cautious of the paper's values (`uncertain` < `review` < `high`) |
| `status` | `preprint` or `published` |
| `doi` / `arxiv_id` | The journal DOI and the preprint's arXiv ID **on the same row** when both exist |
| `versions` | Plain-language history, e.g. `arXiv:2411.09861 (preprint, 2024-11-15) → 10.1021/acs.jctc.5c00114 (J. Chem. Theory Comput., 2025-07-08)` |
| `changes` | Every material-field change this run, `; `-separated, e.g. `status: preprint → published; venue: arXiv → J. Chem. Theory Comput.; doi: (none) → 10.1021/…` |
| `possible_duplicate_of` | For `POSSIBLE_DUPLICATE`: the near match's `work_key`, title and IDs. The two papers are **not** merged |
| `master_pub_id` | Matching master row's Pub ID, or blank |

- Write arXiv IDs as `arXiv:2401.12340` (plain `2401.12340` becomes a number in Excel and
  loses the trailing zero). Write DOIs as plain text.
- `decision` and `reviewer_note` are blank for the reviewer to fill in.
- Same-day reruns retain prior review files and add the run ID to new filenames.
- Multiple existing master version rows can be listed together in `master_pub_id` on one
  output paper row; an ambiguous authors/date fallback does not pick an arbitrary row.
- Optionally (`--xlsx`) also write the same rows to an `.xlsx` with ID columns formatted as
  text. This is a new file, never the master.

The optional Excel review copy (`--xlsx`) holds the same columns in reading order
(`export.REVIEW_ORDER`: title first, `decision`/`reviewer_note` early, IDs last) with real
dates and Yes/No; decision import matches headers by name, so order does not matter.

### Snapshot: `out/works_<YYYY-MM-DD>.csv` — every paper, one row each

Every work in the database, same columns as the candidate file minus `events`, `changes`,
`decision` and `reviewer_note`, plus `latest_decision`. This is the full picture for the
back-test and for comparing with the master; it contains public metadata plus Pub IDs only.

## 10. Decision import

`pubmon import-decisions <reviewed.csv>` reads `work_key`, `decision`, `reviewer_note`
from a reviewed candidate file. Valid decisions: `accepted`, `rejected`, `not_collab`,
`merge:<work_key>` (a person confirming a `POSSIBLE_DUPLICATE`; the two works then share one
`work_key` and one row from then on). Invalid values are reported and skipped; nothing else
changes. Re-importing the same file is harmless (idempotent).

## 11. Modules and CLI

```
src/pubmon/
  cli.py              argparse: run | check-profile | resolve-institutions | import-decisions | status | backtest
  config.py           older settings.toml + env vars → frozen dataclass
  profile.py          profiles/<name>.toml → strict checks → the same Settings dataclass
  models.py           Work dataclass, enums
  sources/openalex.py fetch_pair(), fetch_clinic_quantum(), lookup_institutions()
  sources/arxiv_src.py fetch_feed(), recheck(ids)
  sources/crossref.py enrich(doi) -> dict
  normalize.py        normalize_ids(), normalize_title(), surname()
  match.py            resolve(work, store) -> MatchResult
  diff.py             material_changes(old, new) -> list[Change]
  store.py            schema, transaction(), upserts, events, decisions, runs
  master.py           read_master(path) -> list[MasterRow]; match_master(...)
  export.py           group_by_work(events); write_candidates(); write_snapshot()
  pipeline.py         collection, matching, notices, reconciliation and output orchestration
  decisions.py        local decision import and explicit approved identity merges
  backtest.py         read-only history/master recall report
  log.py              logging setup with run_id
```

Commands (each needs a profile: `--profile NAME`, `PUBMON_PROFILE`, or an existing local
`config/settings.toml`; there is no default):

- `pubmon check-profile` — validates the profile and prints what it will search for. No API calls.
- `pubmon run [--dry-run] [--backfill] [--no-master] [--master PATH] [--xlsx] [--fixtures PATH]`
  `--fixtures` is explicit offline synthetic replay, never an implicit API fallback.
  Replay history/outputs live under ignored `demo/`; `status --demo` and
  `import-decisions --demo` select that isolated history.
  `--dry-run` does everything except committing the transaction and writing the CSV.
- `pubmon resolve-institutions "Cleveland Clinic" "IBM"` — prints OpenAlex institution
  candidates (id, display name, ROR, country, works_count, lineage) for a person to confirm.
  It does not edit config. IBM appears as several lab entities; check whether one parent ID
  covers them through `lineage`.
- `pubmon import-decisions <reviewed.csv>`
- `pubmon status` — last 10 runs with status and counts.
- `pubmon backtest --master PATH [--since 2023-01-01] [--demo]` — after a backfill, reports which
  master rows of type journal article, preprint or review (status Published or Accepted) are in
  the database, matched by IDs then authors+date. Prints recall, lists misses by Pub ID, and
  writes `out/backtest_<date>.csv`. Read-only on both master and history; no API calls.
  The report includes eligible/matched/missing/ambiguous rows and explicit exclusions for
  unsupported types/statuses, missing dates and dates before the inclusive cutoff. Recall is
  tracker-row recall, so two legacy version rows may match one paper; it is not an official
  publication total. Empty eligible scope yields null recall. `--demo` uses isolated replay
  history/output paths, and existing reports are never overwritten.

## 12. Errors, retries, logging

- Network: arxiv.py's built-in delay and retries; PyAlex `max_retries=3`; tenacity
  (`wait_exponential`, `stop_after_attempt(5)`) around Crossref. Retry on 429 and 5xx only.
- A lane that still fails is recorded in `runs.counts_json` as `{"lane": "...", "status": "failed", "error": "..."}` and the run continues with the other lanes. The run's status becomes `partial`.
- Any exception inside step 5 rolls back the whole transaction; the run is marked `failed`.
- Logs go to `data/logs/<run_id>.log` and the console.

## 13. Configuration

Each QIC is one profile, `profiles/<name>.toml`, holding only public criteria; see
`docs/CUSTOMIZATION.md` for every key and `docs/SETUP.md` for onboarding. `profile.py` checks
it strictly (unknown keys, missing keys and bad values stop the command) and translates it
into the same `Settings` object the older format produces.

- `[qic]`: names, `start_date`, `workspace` (a separate history root per QIC), and
  `onsite_hardware` (names of the IBM system at the partner).
- `[institutions]`: OpenAlex `ibm` and `partner` institution IDs.
- `[topic]`: `terms` (search + **Quantum?** = Yes), `broad_terms` (**Quantum?** = Maybe, never
  searched), `arxiv_categories`, `hardware_terms` (**IBM hardware (suggested)**).
- `[search]`: arXiv window, extra arXiv phrases, `common_names`, `skip_types`, optional
  `arxiv_query_override`.
- `[matching]`: thresholds as before.
- `[[people]]`: each person once, with `side` (`partner` finds papers, `ibm` only confirms),
  `aliases`, optional `orcid`, and `tab` (`backup` routes papers found only through them to the
  Backup sheet).

The generated master's Publications sheet holds only papers with a partner author tie (OpenAlex
partner affiliation, or a profile partner person by name). On-site-hardware-only papers go to
Hardware only; partner mentions and unlinked papers go to Check tie; backup-only papers to Backup
(`evidence.partner_tie`, `master_export.SHEETS`).

The arXiv query is generated from partner people, phrases, categories and topic terms. IBM
people are excluded from the search because their names would pull in quantum papers
without the partner. `tests/test_profile.py` pins the Cleveland Clinic query to every clause
of the original hand-written feed, so additions are deliberate. OpenAlex topic searches are
sent in groups of at most five terms, with multi-word terms quoted.

Private values come from environment variables or a git-ignored `.env`: `OPENALEX_API_KEY`,
`PUBMON_EMAIL`, optional `PUBMON_PROFILE` and `PUBMON_MASTER` (the real master path, never in a
profile). The older `config/settings.toml` format (with its legacy keys) still loads when no
profile is named. Workbook reconciliation remains tied to the approved header template.

## 14. Acceptance tests (all must pass offline)

| Test name | Proves |
| --- | --- |
| `test_rerun_is_idempotent` | Two runs on the same recorded responses: the second exports zero candidates |
| `test_cross_source_same_paper` | The same paper from OpenAlex and arXiv becomes one work, one candidate |
| `test_preprint_links_to_journal` | An arXiv preprint and its journal version (different DOIs, slightly changed title) become one work with a `LINKED_PREPRINT` event |
| `test_publication_triggers_update` | A known preprint gaining a journal DOI on re-check produces one `UPDATED` candidate |
| `test_similar_titles_not_merged` | "…Part I" vs "…Part II", and a pair at 88% similarity, stay separate (the latter flagged `POSSIBLE_DUPLICATE`) |
| `test_missing_doi_ok` | Works without a DOI are processed without errors |
| `test_rate_limit_and_outage` | 429 and 503 are retried; a lane that keeps failing is skipped and logged; its works are not marked gone |
| `test_interrupted_run_safe` | An exception mid-step-5 leaves the database byte-for-byte as before the run |
| `test_rejected_not_resurfaced` | A rejected work does not reappear unless a material field changes |
| `test_master_untouched` | The synthetic master's SHA-256 is identical before and after a run |
| `test_master_matching_uses_ids_not_name` | A candidate matches its master row by DOI/arXiv/PMID or authors+date, never by `Name` |
| `test_hyperlink_id_fallback` | A master ID cell containing only the word "arXiv" with a hyperlink yields the arXiv ID |
| `test_manual_columns_never_read` | Reading the master never touches the manual columns (assert via a spy or by giving them poison values) |
| `test_start_date_enforced` | Backfill ignores arXiv results first published before `start_date` |
| `test_one_row_per_paper` | A preprint (lane C) and its journal version (lane A) found in the same run produce exactly one candidate row carrying both `arxiv_id` and `doi` |
| `test_multiple_changes_one_row` | A known paper with three material-field changes in one run produces one row whose `changes` lists all three |
| `test_errata_not_new_papers` | An `erratum` work becomes a `CORRECTION` event on its original paper's row, never a row of its own; `dataset`/`software` works are skipped |

Fixtures: `tests/fixtures/synthetic_master.xlsx` (exact header row, fake rows covering every
case above) and `tests/fixtures/golden_pairs.csv` (public preprint ↔ journal ID pairs). See
`tests/fixtures/README.md`.

## 15. Definition of done for V1

`pytest -q` green, `ruff check .` clean, `pubmon run --dry-run --master
tests/fixtures/synthetic_master.xlsx` completes, and the README lets a beginner run it end to
end on Windows. The owner then runs the **back-test** described in `docs/WORK_PLAN.md`.
