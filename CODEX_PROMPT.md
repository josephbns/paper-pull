# Prompts for Codex

Paste one prompt per Codex session, in order. After each session: read Codex's summary,
run `pytest -q` yourself, skim the new code, and only then paste the next prompt. If a session
goes wrong, say what's wrong in the same session rather than starting over.

Codex reads `AGENTS.md` automatically when it is at the project root. The prompts still
point at it, because being explicit costs nothing.

---

## Session 1 — Kickoff: scaffold, config, models, normalization

```
You are building "pubmon", a small Python tool. Before writing any code, read, in order:
AGENTS.md, docs/SPEC.md, docs/WORK_PLAN.md, docs/SECURITY.md, docs/MASTER_COLUMNS.md.
docs/SPEC.md is the source of truth. Follow every hard rule in AGENTS.md.

Then implement Milestone 1 only:
1. src/pubmon/ package skeleton matching SPEC §11 (empty modules with docstrings are fine
   for later milestones).
2. config.py: load config/settings.toml (fall back to config/settings.example.toml) and the
   env vars OPENALEX_API_KEY and PUBMON_EMAIL (support a git-ignored .env). Return a frozen
   dataclass. Missing env vars are an error only for commands that call the network.
3. models.py: the Work dataclass and enums from SPEC §5.
4. normalize.py: normalize_ids(), normalize_title(), surname() exactly as SPEC §7 describes.
5. Unit tests for normalize.py covering: DOI case and prefixes ("https://doi.org/..."),
   arXiv version suffixes and "arXiv:" prefixes, LaTeX in titles ("$Δ$ADAPT-VQE",
   "\textsf{SU}(2)"), accented names ("Jędrzej", "Flöther"), suffixes ("Merz Jr").
6. docs/CHANGELOG.md with a first entry; a README.md stub (full README comes in Milestone 6).

Do not write any network code yet. Stop when `pytest -q` and `ruff check .` pass, then
give the end-of-milestone summary described in AGENTS.md.
```

## Session 2 — History database

```
Read AGENTS.md and docs/SPEC.md §5, §6 and §12. Implement Milestone 2: store.py.
- The SQLite schema in SPEC §5 via sqlite-utils, created idempotently.
- A transaction() context manager: everything inside commits together or rolls back.
- Functions to upsert identifiers and source records, find a work_key by any identifier,
  write events, list unexported events, mark events exported, record runs, and store and
  read decisions.
- Tests: rollback on an exception leaves the database byte-for-byte unchanged
  (test_interrupted_run_safe); inserting the same identifier twice keeps one row; events
  marked exported are not listed again.
Stop when tests and lint pass, then summarize.
```

## Session 3 — Sources (OpenAlex, arXiv, Crossref)

```
Read AGENTS.md and docs/SPEC.md §4, §7 and §12. Implement Milestone 3: sources/openalex.py,
sources/arxiv_src.py, sources/crossref.py, and the `pubmon resolve-institutions` command.
- Lane A, lane B, lane C and the weekly arXiv re-check exactly as SPEC §4 describes,
  each returning list[Work] with lane, confidence, ibm_confirmed and matched_names set.
- The work-type rules in SPEC §4 "Work types": skip_types are skipped and counted; errata and
  retractions are kept aside for linking to their original paper, never returned as papers.
- Pagination completeness check for OpenAlex (fetched count vs meta.count).
- Retries per SPEC §12. A failing lane raises a LaneFailed error that the caller can log
  and skip.
- No internet in tests. Write small hand-made JSON fixtures in tests/fixtures/api/ shaped
  like real responses (OpenAlex works list with meta, arXiv Atom entries via arxiv.Result
  objects, a Crossref work with update-to and relation). Use pytest-recording markers so
  real cassettes can be recorded later with `pytest --record-mode=once`, and configure it
  to filter the api_key query parameter and the Authorization header.
- Leave TODO(owner) where real institution IDs or names are needed.
Stop when tests and lint pass, then summarize. Include in the summary the exact command I
should run on my laptop, with internet, to record real cassettes.
```

## Session 4 — Matching and change detection

```
Read AGENTS.md and docs/SPEC.md §6 step 5 and §7. Implement Milestone 4: match.py and diff.py,
and wire step 5 of the pipeline (resolve and store, one transaction).
- Resolution order: shared identifier → link clues → fuzzy title rule → new.
- Fuzzy rule with every guard in SPEC §7 (score, authors, year window, identical numbers).
- POSSIBLE_DUPLICATE for the review band; never auto-merge there.
- Material-field diff and the events it produces, including LINKED_PREPRINT.
- Use tests/fixtures/golden_pairs.csv (public preprint ↔ journal ID pairs) to build realistic
  test records, plus synthetic near-miss titles for the negative cases.
- Acceptance tests: test_cross_source_same_paper, test_preprint_links_to_journal,
  test_publication_triggers_update, test_similar_titles_not_merged, test_missing_doi_ok,
  test_rerun_is_idempotent.
Stop when tests and lint pass, then summarize.
```

## Session 5 — Master reconciliation, export, decisions, CLI

```
Read AGENTS.md and docs/SPEC.md §6, §8, §9, §10, §11 and docs/MASTER_COLUMNS.md. Implement
Milestone 5: master.py, export.py, `pubmon import-decisions`, `pubmon status`, and the full
`pubmon run` command with --dry-run, --backfill, --no-master, --master and --xlsx.
- Master is read-only; validate headers; read only the allowed columns; hyperlink fallback
  for ID cells; match by IDs, then authors+date; never by Name.
- Export ONE ROW PER PAPER (SPEC §9): group events by work_key; a preprint and its journal
  version share one row with both IDs; all changes to a paper go in its `changes` cell;
  POSSIBLE_DUPLICATE gets its own row with `possible_duplicate_of`, never a merge. Also write
  the out/works_<date>.csv snapshot.
- Export with temp-file-then-rename, then mark events exported.
- Use tests/fixtures/synthetic_master.xlsx. Never save it.
- Remaining acceptance tests from SPEC §14: test_rate_limit_and_outage,
  test_rejected_not_resurfaced, test_master_untouched,
  test_master_matching_uses_ids_not_name, test_hyperlink_id_fallback,
  test_manual_columns_never_read, test_start_date_enforced, test_one_row_per_paper,
  test_multiple_changes_one_row, test_errata_not_new_papers.
Stop when the full SPEC §14 suite passes offline and
`pubmon run --dry-run --no-master` works against fixtures, then summarize.
```

## Session 6 — Back-test command and beginner README

```
Read AGENTS.md, docs/SPEC.md and docs/WORK_PLAN.md (V1 gate). Implement Milestone 6.
1. `pubmon backtest --master PATH --since 2023-01-01`: after a backfill run, report which
   master rows of Type "Peer Reviewed Journal", "Open Publication" or "Review Paper" with
   Pub Status "Published" or "Accepted" were found in the database (by IDs, then
   authors+date) and which were not. Print recall, list the misses with Pub ID and Name, and
   write out/backtest_<date>.csv. Read-only on the master, as always.
2. README.md for a beginner on Windows: install Python, create the venv, install, get a free
   OpenAlex key, set env vars in PowerShell, fill config, run resolve-institutions, first
   backfill, weekly run, how to review the CSV and import decisions, how to run the
   back-test, and what never to commit.
3. A final review pass: re-read SPEC §2 and §14 and list each requirement with the file and
   test that satisfies it.
Stop when tests and lint pass, then summarize.
```

---

## If Codex gets stuck

- "Re-read docs/SPEC.md section N and tell me where your code differs from it."
- "List every TODO(owner) in the repo with file and line."
- "Explain this function to me as if I'm learning Python, then suggest one simplification."
