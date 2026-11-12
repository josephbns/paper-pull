# pubmon — work plan

V1 is built in six Codex sessions, one milestone each, then checked with a back-test against the real master on an IBM machine. Later versions add automation (V2), smarter discovery (V3) and controlled master integration (V4), each behind a written gate.

## V1 build milestones

| # | Milestone | Main files | Done when |
| --- | --- | --- | --- |
| 1 | Scaffold, config, models, normalization | `config.py`, `models.py`, `normalize.py` | Normalization unit tests pass; lint clean |
| 2 | History database | `store.py` | Rollback leaves the DB byte-identical; duplicate identifiers collapse to one row |
| 3 | Sources | `sources/openalex.py`, `sources/arxiv_src.py`, `sources/crossref.py`, `resolve-institutions` | Lanes A, B, C and the re-check return `Work` lists from offline fixtures; failing lanes are skippable |
| 4 | Matching and change detection | `match.py`, `diff.py` | Six matching acceptance tests pass (SPEC §14) |
| 5 | Master, export, decisions, CLI | `master.py`, `export.py`, `cli.py` | Full SPEC §14 suite passes offline; `pubmon run --dry-run` works |
| 6 | Back-test and README | `backtest`, `README.md` | A beginner can run it end to end on Windows |

Prompts for each session are in `CODEX_PROMPT.md`.

### After milestone 6 (owner, on an IBM machine, with internet)

1. Get a free OpenAlex key; set `OPENALEX_API_KEY` and `PUBMON_EMAIL`.
2. Copy `config/settings.example.toml` to `config/settings.toml`. The parent institution IDs are pre-filled (checked live 12 Nov); run `pubmon resolve-institutions "Cleveland Clinic" "IBM"` only to decide on the extra entities listed in its TODO (IBM Japan, Cleveland Clinic Abu Dhabi, etc.).
3. Record real cassettes once: `pytest --record-mode=once`. Check that no key appears in `tests/cassettes/`.
4. `pubmon run --backfill --master <path to real master>`.
5. `pubmon backtest --master <path> --since 2023-01-01`. This is the V1 gate below.
6. Run weekly for two weeks; confirm zero repeat candidates.

## Where to build this week (no GitHub)

Codex **cloud** tasks check out a GitHub repository, so they can't run until this project lives in one. Until then:

- **Recommended:** run Codex locally (CLI, IDE extension or desktop app) on this folder. Nothing leaves your machine except the prompts and code Codex sees, and the folder contains no internal data.
- **When GitHub is available:** `git remote add origin <url> && git push -u origin main` (the folder is already a git repository with one commit). Then connect the repo in Codex cloud and use the setup script `pip install -e ".[dev]"`. Leave agent internet off; tests are offline.
- **IBM's GitHub:** check whether Codex cloud can connect to it. A third-party guide (late Sep 2026) says self-hosted GitHub Enterprise Server isn't supported. If it isn't, keep using Codex locally against a clone.

## Roadmap: V1 to V4

Four stages, each gated by a measurable test; the most important gate is V1's **back-test**: run the tool over the last few years and check it finds the papers already in your master workbook. Your existing tracker is free ground truth, so use it.

|  | V1 — Functional MVP | V2 — Reliable automation | V3 — Smarter discovery | V4 — Master integration |
| --- | --- | --- | --- | --- |
| **Features** | OpenAlex + arXiv fetch; Crossref lookups; normalize, match, SQLite history; candidates CSV; read-only master check; decision import | Weekly GitHub Actions run (Zone 1 only); PubMed source; Slack weekly digest; per-source health check (alert if a source returns 0 or drops sharply) | Author watchlist by ORCID/OpenAlex author ID; simple rule-based relevance score; papers that cite known collab papers (OpenAlex `cites:` filter); threshold tuning; Europe PMC if biomedical preprints matter | "Proposed changes" workbook (new rows + field-level old→new); approval via decision column; monthly report; audit-trail export; one-time merge of the two legacy trackers with BibDedupe |
| **Depends on** | Free OpenAlex key; confirmed institution IDs; watchlist CSV; a synthetic master for tests | IBM-approved repo and runner; approved Slack webhook; NCBI key | 4+ weeks of review decisions; \~50 labeled match / non-match pairs | A stable unique ID column added to the master (e.g. `PUB-0001`) |
| **Complexity** | Medium-low | Medium | Medium | Medium-high (Excel is fragile) |
| **Main risks** | Wrong or incomplete IBM institution IDs (IBM has many lab entities) → missed papers; poorly tuned thresholds | Secrets handling; state on throwaway runners; policy approval | Candidate volume grows faster than reviewer time | Corrupting or overwriting the master; workbook column drift |
| **Tests** | 17 acceptance tests (SPEC §14) + back-test | Failure injection; dry run on synthetic data in the workflow | Precision and recall on the labeled pairs | Golden-file tests; protected columns byte-identical after round trip |
| **Gate to advance** | Back-test finds ≥ 90% of the master's published journal articles and preprints since 2023 (talks, posters and short papers excluded), every miss explained; catches every collaboration paper your current feeds surfaced since 18 Sep 2026; 2 weekly local runs with zero repeat candidates; zero wrong merges found in review | 4 consecutive scheduled runs with no manual fixes; one forced failure alerts and leaves no partial state | Reviewers accept ≥ 50% of NEW candidates over 4 weeks; recall no worse than V1 | 2 months of parallel running where tool-proposed and manual updates agree |
| **Effort (estimate)** | 3–5 days | 3–5 days | 1–2 weeks | 1–2 weeks |

The gate numbers are proposed starting targets, not industry standards. Adjust them after the first back-test shows what is realistic.

> **Level up: gates, not dates.** Pros advance a project when evidence says the current stage works, not when the calendar says so. A gate written down in advance ("≥ 90% recall on the back-test") stops you from building V3 features on top of a V1 that quietly misses papers.


## Risk register

The most dangerous failure is the silent one: a paper the system never finds, because nobody notices an absence. Rows are ordered by priority; 13 of 19 must be handled in V1, and most of those are handled by the design itself rather than extra code.

| # | Risk | What goes wrong | Simplest mitigation | When |
| --- | --- | --- | --- | --- |
| 1 | Query too narrow (missing or wrong affiliations; IBM appears as many institution entities) | Papers silently missed | Filter on every confirmed IBM and Cleveland Clinic institution ID via `lineage`; arXiv watchlist as a second net; back-test against the master; OpenAlex email alert as cross-check | V1 |
| 2 | Preprint and journal versions not linked (different DOIs, retitled) | Double rows, double-counted publications | Identifier clues first (arXiv `doi`/`journal_ref`, OpenAlex locations, Crossref relations), then the fuzzy rule with year window; uncertain cases go to a person | V1 |
| 3 | Two different papers wrongly merged | A publication vanishes from the count | Strict auto-link rule (≥ 95, author, year, identical numbers); 85–95 never auto-merged; dedicated test | V1 |
| 4 | Master workbook or manual fields overwritten | Loss of SOW attribution and official-count decisions | Read-only open; no write path exists in code; SHA-256 test | V1 |
| 5 | Repeat notifications after a failed or re-run job | Reviewer fatigue, distrust | `exported_in_run` flag; one transaction; temp-file-then-rename export | V1 |
| 6 | Rejected candidates resurface | Same noise every week | `decisions` table; resurface only on a material change | V1 |
| 7 | Interrupted run corrupts history | Lost or inconsistent state | One transaction per run; copy `pubmon.db` to a backup before each run; raw snapshots kept | V1 |
| 8 | Rate limits or outages | A failed source looks like "no new papers" | arxiv.py's 3 s delay; tenacity retries; Crossref `mailto`; record failed sources in `runs`; never treat absence as deletion | V1 |
| 9 | Incomplete pagination | Missing tail of results | Cursor paging with `n_max=None`; compare fetched count with the API's reported total; fail the source on mismatch | V1 |
| 10 | Missing or conflicting DOIs | Crashes or false merges | DOI optional; many identifiers per work; normalize with IDUtils; conflicts → `POSSIBLE_DUPLICATE` | V1 |
| 11 | Delayed indexing across sources | Paper appears weeks late | Weekly full re-pull catches late arrivals; arXiv covers speed | V1 (by design) |
| 12 | Excel fragility (renamed columns, auto-converted IDs) | Bad matches or wrong IDs | Column map in config; check headers on load and fail loudly; write `arXiv:` prefix | V1 |
| 13 | Credential or data leakage | Keys or internal data exposed | Keys only in environment variables; `data/` and `out/` git-ignored; Zone 2 stays on IBM machines; synthetic fixtures | V1 |
| 14 | Author-name ambiguity on arXiv (e.g. "Wang, J") | False positives | Pair rule where IBM names exist; hits matched only by a common name marked uncertain | V1 partial; ORCID IDs in V3 |
| 15 | API or access-model changes (OpenAlex changed twice in 2026; arXiv calls its query API "legacy") | Fetch breaks or costs change | One adapter module per source; recorded-response tests; zero-result health alert | V1 adapters; V2 alert |
| 16 | State lost on throwaway GitHub runners | Everything looks new every week | Commit state back to the repo (git-scraping pattern) or store it in an approved location; never rely on Actions cache (evicted after 7 days unused) | V2 |
| 17 | Scheduled runs delayed, dropped or auto-disabled | Silent gaps | Off-peak minute; manual `workflow_dispatch` button; "no successful run in 8 days" alert | V2 |
| 18 | OpenAlex work IDs change when duplicates merge | Known paper looks new | Never key on OpenAlex ID alone; re-resolve by DOI or arXiv ID | V2 |
| 19 | Broad keyword searches | Flood of false positives | No keyword-only discovery; keywords only rank pair-rule results | V3 |

> **Level up: design out risk before coding around it.** Notice how many mitigations are structural: a unique constraint, a read-only file handle, a transaction. Structural fixes can't be forgotten. Defensive `if` statements can.


## Deployment, security and testing

**Run V1 on your IBM laptop; build it in Codex with synthetic data; move only the public-metadata half to a scheduler in V2, after IBM approves where it runs.** A weekly job of this size uses a few minutes of compute, so cost is never the constraint. Policy is.

### Where to run it

| Option | Runs with laptop off? | Cost | Security fit | Use it for |
| --- | --- | --- | --- | --- |
| Local Windows (Task Scheduler) on your IBM laptop | No (laptop must be on; set "run as soon as possible after a missed start") | Free | Best: all data stays on an IBM-managed device | V1, and Zone 2 permanently |
| Codex cloud | Not a scheduler; needs a github.com repository | Included in your plan | Agent internet is off by default; setup scripts can still install packages. If you turn it on, allow only the API domains and GET-only methods ([Codex docs](https://learn.chatgpt.com/docs/cloud/internet-access)). Never upload the master. | Building and testing with synthetic data |
| GitHub Actions, private repo | Yes | Personal free plan includes $12/month of compute, about 2,000 Linux minutes; public repos are free ([GitHub billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)) | Public metadata only (Zone 1), and only after approval. Runs can be delayed or dropped at busy times; public repos auto-disable schedules after 60 idle days ([GitHub docs](https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows)) | V2 Zone 1 |
| IBM's GitHub (temporarily down as of 12 Nov 2026) | Yes | Already paid for | IBM's own platform, so the cleanest approval path for code and state. Check whether Codex can connect to it; if not, run Codex locally on a clone | V2 home. Until it's back, keep the code local and skip a personal repo |

### What may go where

| Data | Examples | Allowed outside IBM? |
| --- | --- | --- |
| Public scholarly metadata | Titles, authors, affiliations, DOIs, dates fetched from public APIs | Yes |
| Derived public state | The SQLite history of public records and match links | Yes, once the repo location is approved |
| Partnership-internal | Master workbook, SOW attribution, official-count decisions, review decisions and notes | **No.** Zone 2, IBM machines only |
| Gray zone | The watchlist of collaborators | Use only names already on public collaboration papers; otherwise treat as internal |

Keys (OpenAlex, NCBI, Slack webhook) live only in environment variables or the CI's secret store, never in files. Decide which email goes in API `mailto` headers; a team mailbox avoids tying the tool to one person.

### Testing toolkit

- **pytest + pytest-recording.** Record each source's real public responses once into "cassettes" and replay them offline forever. Configure it to strip `api_key` query parameters and `Authorization` headers so keys never land in test files.
- **A synthetic master workbook,** generated by a script in `tests/fixtures/`, with fake rows that mimic real columns. Real data never enters the repo.
- **Free ground-truth pairs:** arXiv records whose authors filled in `doi` and `journal_ref` are confirmed preprint-to-journal pairs. Collect 20–50 from public quantum papers for the matching tests.
- **Failure injection:** make the HTTP layer return 429, 503 or a half page, and raise an exception mid-run, to prove retries and rollback.
- **BibDedupe's benchmark datasets** (`load_example_data`) for a sanity check on the title-matching rule.
- **Benchmark to beat:** Crossref's own preprint matcher reports precision 0.99 and recall 0.95 on 3,000 pairs ([Crossref](https://crossref.org/blog/discovering-relationships-between-preprints-and-journal-articles/)). Treat that as the ceiling, not the bar for V1.

> **Level up: test the contract, not the internet.** Tests that call live APIs fail for reasons that have nothing to do with your code. Recording real responses once gives you realistic data with none of the flakiness, and makes the whole suite runnable on a plane.


## Open questions for the owner

- Counting policy when a preprint and its journal version both have rows (decide before V4 reports counts).
- Which papers found only on the Cleveland Clinic quantum list belong in the master (scope).
- IBM-side names for the arXiv watchlist, so the arXiv lane can confirm IBM co-authorship.
- Names on the watchlist that are common enough to collide with other researchers (`arxiv.common_names`).
- The PubMed saved-search query string, for the V2 PubMed lane.
- IBM approval for Codex, GitHub hosting and (V2) a Slack webhook.
