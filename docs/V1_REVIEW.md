# V1 requirements review

Reviewed against SPEC §2 (hard rules) and §14 (acceptance cases), 2026-11-12.

**Implementation is complete; operational validation is not.** Offline tests, including the
CLI workflow and back-test reporting, pass with synthetic/public fixtures. Three optional
live-recording checks are skipped. API access/credentials, real-master recall, current-feed
coverage and two weekly live runs remain outstanding. Windows commands are documented but
were not executed on a native Windows host.

## Hard rules — SPEC §2

| Requirement | Implementation | Evidence |
| --- | --- | --- |
| Master opened read-only; never saved, moved or renamed | [master.read_master](../src/pubmon/master.py), [backtest.run_backtest](../src/pubmon/backtest.py); hyperlink relationship reading avoids an editable workbook handle | `test_master_untouched`, `test_one_row_per_paper`, `test_backtest_inputs_unchanged_and_reports_not_overwritten` |
| Manual columns never read or output | `master.ALLOWED`, [export.COLUMNS](../src/pubmon/export.py), `backtest.COLUMNS` | `test_manual_columns_never_read` spies on cell access; `test_backtest_reports_known_rows_misses_and_exclusions` checks poison is absent |
| Keys/emails only through runtime configuration | [config.load_config](../src/pubmon/config.py); credentials excluded from settings representations | `test_credentials_required_only_for_network`, `test_dotenv_process_precedence_and_no_secret_repr`; no real credential values in the repo |
| Tests offline; recordings scrub credentials | [pytest configuration](../pyproject.toml), [vcr_config](../tests/conftest.py) | Full suite runs with `--block-network`; `test_cassette_filters_credentials_before_writing`. Actual public API recordings remain unrun |
| Only public metadata/synthetic fixtures in repository | [.gitignore](../.gitignore), [fixtures](../tests/fixtures/README.md), isolated `demo/` mode | Staged-file inspection; `test_demo_replay_never_creates_live_history`. Uploaded real workbook remains outside the checkout |

## Acceptance cases — SPEC §14

These names are verified as present and executed in the offline suite, not merely listed.
Tests named below live in [test_match](../tests/test_match.py),
[test_pipeline](../tests/test_pipeline.py), [test_master](../tests/test_master.py),
[test_store](../tests/test_store.py), and [test_arxiv](../tests/test_arxiv.py).

| Required test | Implementation | Supporting check / scope |
| --- | --- | --- |
| `test_rerun_is_idempotent` | [match.resolve_and_store](../src/pubmon/match.py), [pipeline.run](../src/pubmon/pipeline.py), export markers | Also `test_rerun_exports_zero_candidates_and_preserves_review_file` verifies CSV-level reruns |
| `test_cross_source_same_paper` | Identifier resolution and shared work key in `match` | Pipeline `test_one_row_per_paper` confirms combined output |
| `test_preprint_links_to_journal` | DOI clues, retained identifiers, `LINKED_PREPRINT` | Different preprint/journal DOIs in synthetic metadata; public golden IDs are additional offline cases |
| `test_publication_triggers_update` | `diff.canonical_state`, material-field changes | arXiv DOI/journal metadata changes publication state without a second paper |
| `test_similar_titles_not_merged` | Guarded RapidFuzz title comparison | Part I/II, 88%-similar review-band titles; additional decimal, author, year and ambiguity cases |
| `test_missing_doi_ok` | Optional IDs plus stable source identity | Same DOI-less source reruns as one work |
| `test_rate_limit_and_outage` | Source retries, safe lane errors, partial-run recording | Synthetic 429/503 responses and persistent failure; no real service availability claimed |
| `test_interrupted_run_safe` | [Store.transaction](../src/pubmon/store.py), atomic matching batch | Database bytes unchanged after interrupted matching; pipeline failure recording tested separately |
| `test_rejected_not_resurfaced` | [eligible_events](../src/pubmon/export.py), local decisions | Later material changes can resurface a rejection; old pending events remain suppressed |
| `test_master_untouched` | Read-only workbook path | SHA-256 equality before/after read; pipeline/back-test also verify unchanged inputs |
| `test_master_matching_uses_ids_not_name` | Identifier match, then authors/date fallback | `Name` used only for display |
| `test_hyperlink_id_fallback` | ZIP relationship resolution in `master` | Label-only arXiv cell yields its linked identifier |
| `test_manual_columns_never_read` | Explicit field projection | Spy rejects any protected data-cell value access |
| `test_start_date_enforced` | arXiv submission-date backfill ordering/cutoff | No pre-start publication included |
| `test_one_row_per_paper` | Group pending events by work key | Journal DOI and preprint arXiv ID in one CSV/Excel row |
| `test_multiple_changes_one_row` | Grouped event/change formatting | Three changed fields in one candidate row |
| `test_errata_not_new_papers` | Notice separation and original-paper linking | Correction/retraction events attach to original; dataset/software skipped |

## Milestone 6 additions

| Capability | Implementation | Evidence |
| --- | --- | --- |
| Back-test eligibility and inclusive date filter | [backtest._exclusion](../src/pubmon/backtest.py) | `test_backtest_reports_known_rows_misses_and_exclusions`, `test_backtest_since_cutoff_is_inclusive`, `test_missing_date_is_excluded_and_accepted_reviews_are_eligible` |
| Identifier and authors/date recall | `backtest.compare` delegates matching to `master.match_master` | Five found tracker rows out of nine in a controlled synthetic history; preprint/journal rows can share one work key |
| Ambiguous/missing evidence does not inflate recall | `backtest.compare` | `test_backtest_ambiguous_history_is_not_counted_as_found`, `test_empty_eligible_scope_does_not_claim_perfect_recall`, `test_empty_existing_history_reports_zero_recall` |
| Back-test never modifies history | `Store(read_only=True)` uses SQLite read-only URI and skips migration | `test_readonly_history_rejects_writes`, `test_backtest_inputs_unchanged_and_reports_not_overwritten`, `test_backtest_reads_legacy_history_without_migrating` |
| Missing history/configuration fails clearly | CLI `backtest` preflight | `test_backtest_missing_history_and_bad_date_leave_no_outputs`, `test_backtest_cli_uses_demo_history_without_credentials` |
| Windows beginner workflow | [README](../README.md) | Commands reviewed; Linux CLI equivalents exercised. Native Windows execution remains unverified |

## Interpretation and remaining validation

- Back-test recall counts eligible **master rows**, not unique publication totals. No manual
  official-count/SOW/theme/involvement column is read. Reports include exclusions and misses;
  missing dates do not disappear silently. Zero eligible rows yields null recall.
- Matching rollback is byte-identical for the matching transaction. A failed full CLI run
  still records its failure in run metadata, as SPEC §12 requires; that metadata can change
  the database file independently of the rolled-back paper updates.
- Atomic output replacement precedes export-marker commits. A failed run's files should not
  be reviewed; pending events are retried. Existing review files are retained, not overwritten.
- Offline fixtures verify behavior, not discovery completeness. The 11 public ID pairs use
  synthetic surrounding metadata; they are not evidence of live cross-source relation coverage.
- TODO(owner): apply the saved API network/credential settings when ready, verify the Clinic
  title/abstract query and institution scope, and review IBM/common-name watchlist entries.
- On the approved owner machine: perform the real backfill/back-test, explain misses, compare
  current feeds, and observe two weekly runs with no repeats or wrong merges before advancing
  to V2. A report below 90% still completes; the human validation gate remains unmet.
