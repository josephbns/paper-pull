# pubmon — research findings

Researched 12 Nov 2026. Sources are listed at the end; every API claim comes from official documentation or library source code, not live calls.

## How to read this doc

Read section A first. The build instructions themselves live in `docs/SPEC.md` (what to build) and `docs/WORK_PLAN.md` (in what order); this file is the evidence behind them. Boxes marked **Level up** are coaching notes: the professional habit behind each design choice, so you learn why, not just what.

Ten terms carry most of this doc:

| Term | Plain meaning |
| --- | --- |
| API | A website built for programs instead of people. You send a URL, it sends back data (usually JSON). |
| Rate limit | How often an API lets you call it, e.g. one request every 3 seconds. Exceed it and you get blocked. |
| DOI | A permanent ID for a published paper, like a VIN for a car, e.g. `10.1038/s41586-023-06096-3`. |
| Preprint | A paper posted publicly (e.g. on arXiv) before peer review. The journal version usually gets a different DOI. |
| Normalize | Convert records from different sources into one common shape so they can be compared. |
| Deduplicate | Decide that two records describe the same paper and keep one. |
| Fuzzy match | Comparing text that is almost the same ("Quantum-centric" vs "Quantum centric") with a similarity score. |
| Idempotent | Running the job twice gives the same result as running it once. The key property for "no repeat alerts." |
| SQLite | A whole database stored in one file. No server, nothing to install, built into Python. |
| GitHub Actions | GitHub's free robot that runs your code on a schedule (cron) in a temporary cloud computer. |

## A. Executive recommendation

**Build a small custom Python app (roughly 600–900 lines) that glues together six maintained libraries.** No existing open-source project does this job; I checked 21 projects and services, and the closest ones each miss a must-have (details in B). About 70% of the work is done by libraries; the custom 30% is exactly the part that is specific to your tracker.

**The decision in one line:** combine libraries, don't adapt a project. Use [PyAlex](https://github.com/J535D165/pyalex) (OpenAlex), [arxiv.py](https://github.com/lukasschwab/arxiv.py) (arXiv), [habanero](https://github.com/sckott/habanero) (Crossref), [RapidFuzz](https://github.com/rapidfuzz/RapidFuzz) + [IDUtils](https://github.com/inveniosoftware/idutils) (matching), and [sqlite-utils](https://github.com/simonw/sqlite-utils) (history).

### Why not adapt an existing project

- **PaperBee** is the closest match (finds papers, posts to Slack), but it dedups on DOI only, stores state in a Google Sheet that needs a Google service account, and pins a 2022 search library.
- **findpapers** has good multi-source dedup code, but its last PyPI release is from November 2022; the active code is unreleased.
- **CalAcademy publications\_finder** has the right idea (OpenAlex + institution ID + ORCID list), but it is GPL-licensed, needs MySQL, and was last touched in September 2024.
- **lit-monitor, Paper Digest, zotero-arxiv-daily** are personal reading tools built around AI ranking. Wrong job, and either heavy, paid, or copyleft.
- None of them handles the three things your tracker needs most: preprint-to-journal reconciliation, protecting manual fields, and remembering rejected candidates.

### Three design choices that keep it simple

1. **Re-pull everything, diff locally.** The collaboration's paper set is small (the program reports 50+ projects over five years). Each week, fetch the whole set and compare it with what you saw last week. This avoids "updated-since" filters, which OpenAlex now limits to paid plans, and it cannot miss a quiet update. A full re-pull is a handful of API calls; the free OpenAlex key allows about 10,000 per day.
2. **The pair rule, plus a review lane.** A paper with both an IBM- and a Cleveland Clinic-affiliated author is a high-confidence candidate; OpenAlex can filter on both institutions at once. Your tracker also counts some Clinic-only quantum papers, so a second lane keeps Clinic authors' quantum papers that lack an IBM co-author and flags them for a person to judge. arXiv has no affiliations, so there V1 starts from your existing arXiv feed query and confirms the IBM side through OpenAlex.
3. **Two security zones.** Zone 1 touches only public metadata, so it can later run in GitHub Actions. Zone 2 reads the master workbook and your review decisions, and runs only on an IBM-managed machine. The master workbook is opened read-only and is never written.

### Do this week, zero code

Create a free OpenAlex account and save a weekly **email alert** on the two-institution search. OpenAlex alerts are free, support daily/weekly/monthly schedules, and need no code ([OpenAlex alerts docs](https://help.openalex.org/api/alerts/)). It becomes your safety net while V1 is built.

### What I'd kill

- **LLM relevance filtering, vector search, Semantic Scholar, Slack** in V1. Each adds a key, a failure mode, or a cost before the basics are proven.
- **Writing to the master workbook,** ever, from code. The tool proposes; a person decides.
- **Europe PMC for quantum preprints.** It indexes arXiv only for COVID-19 full text, so it adds nothing for quantum work.

**Effort estimate:** V1 is about 3–5 focused days with Codex, including tests. V1–V4 together are roughly 4–6 weeks of part-time work. These are estimates, not measurements.

> **Level up: glue code.** Senior engineers judge a design partly by what they did *not* have to write. Every line you write is a line you must test, debug and maintain. Your job here is to write the thin layer that only you can write (your matching rules, your tracker's columns) and borrow everything else.

## B. Open-source comparison

Eight libraries are worth reusing as-is; no complete application is worth adopting. Every row below was verified on 12 Nov 2026: versions and licenses from PyPI, activity (where a last-commit date is shown) by cloning the repo and reading its git history, and key functions by reading the source. All are Python, free, and pip-installable, so all run locally or in GitHub Actions. Open-issue counts could not be checked (the GitHub API was not reachable from my research environment).

### Ranked: use these

| # | Project | What it actually does | License | Latest release · last commit | Verdict |
| --- | --- | --- | --- | --- | --- |
| 1 | [PyAlex](https://github.com/J535D165/pyalex) | OpenAlex client: filters, cursor paging, API key, retries | MIT | 0.21 (Feb 2026) · Feb 2026 | **Reuse, core.** Set `config.max_retries` (default is 0). Quiet for 9 months; thin wrapper, low risk. |
| 2 | [arxiv.py](https://github.com/lukasschwab/arxiv.py) | arXiv client with the required 3-second delay and retries built in | MIT | 4.0.2 (Oct 2026) · Oct 2026 | **Reuse, core.** Results expose `doi` and `journal_ref`, the preprint-to-journal clues. |
| 3 | [habanero](https://github.com/sckott/habanero) | Crossref client; `mailto` puts you in the faster "polite pool" | MIT | 2.9.2 (Jun 2026) · Oct 2026 | **Reuse** for DOI lookups (journal, dates, retractions, preprint relations). |
| 4 | [RapidFuzz](https://github.com/rapidfuzz/RapidFuzz) | Fast fuzzy text similarity scores | MIT | 3.14.6 (Aug 2026) | **Reuse** for title matching. Crossref's own preprint matcher uses it. |
| 5 | [IDUtils](https://github.com/inveniosoftware/idutils) | Detects and normalizes DOI, arXiv ID, PMID, ORCID, ROR | BSD-3 | 1.7.1 (Oct 2026) · Oct 2026 | **Reuse** so identifiers compare cleanly. |
| 6 | [sqlite-utils](https://github.com/simonw/sqlite-utils) | Easy upserts into SQLite, plus a CLI to inspect the database | Apache-2.0 | 4.2.1 (Aug 2026) · Oct 2026 | **Reuse** for history storage. |
| 7 | [tenacity](https://github.com/jd/tenacity) | Retry-with-backoff decorator for flaky HTTP calls | Apache-2.0 | 9.2.1 (Oct 2026) | **Reuse** around any call without built-in retries. |
| 8 | [pytest-recording](https://github.com/kiwicom/pytest-recording) | Records real API responses once, replays them offline in tests | MIT | 0.14.1 (Nov 2026) | **Reuse** for tests that need no internet and no internal data. |
| 9 | [BibDedupe](https://github.com/CoLRev-Environment/bib-dedupe) | Batch dedup of bibliographic tables; exports "maybe" pairs for human review | MIT | 0.11.0 (Nov 2025) · Nov 2026 | **Adapt** for the one-time merge of your two Excel trackers. No preprint logic in its source, and it is batch-only, so not for weekly runs. |
| 10 | [Biopython Bio.Entrez](https://github.com/biopython/biopython) | PubMed E-utilities client | Biopython (BSD-style) | 1.88 (Aug 2026) | **Reuse in V2** when PubMed is added. |

### Reference only: read, don't depend on

| Project | Why it's interesting | Why not adopt | Verdict |
| --- | --- | --- | --- |
| [findpapers](https://github.com/jonatasgrosman/findpapers) | Multi-source search with a sensible two-pass dedup (DOI first, then title + compatible year, preprint-aware) | PyPI release 0.6.7 dates from Nov 2022; the active Aug 2026 code is an unreleased rewrite | **Reference.** Read `_deduplicate_and_merge` in `findpapers/runners/search_runner.py`. |
| [PaperBee](https://github.com/theislab/paperbee) | Closest end-to-end match: keyword search, Slack posting, optional LLM filter | DOI-only dedup; state lives in a Google Sheet behind a service account; pins findpapers 0.6.7 | **Reference** for Slack message format in V2. |
| [publications\_finder](https://github.com/calacademy-research/publications_finder) | Institution tracker: OpenAlex ROR filter plus an ORCID watchlist | GPL-3.0, MySQL + Docker, last commit Sep 2024 | **Reference** for design; don't copy code. |
| [zotero-arxiv-daily](https://github.com/TideDra/zotero-arxiv-daily) | Clean example of a scheduled GitHub Actions paper digest | AGPL-3.0 (strong copyleft), LLM ranking of arXiv only | **Reference** for workflow shape only. |
| [semanticscholar](https://github.com/danielnsilva/semanticscholar) | Citation and related-paper discovery | Not needed until V3 | **Defer to V3.** |

### Rejected

| Project | Finding | Verdict |
| --- | --- | --- |
| [lit-monitor](https://pypi.org/project/lit-monitor/) | One PyPI release (0.11.0, Jun 2026); its GitHub source was not publicly reachable; pulls in a vector DB, sentence-transformers, FastAPI and an LLM stack; built for one person's Zotero/Obsidian | **Avoid** |
| [Paper Digest](https://www.paperdigest.org/frequently-asked-questions/) | Commercial SaaS; full daily digest is paid (from $10.99/month); no API or CSV export documented. The PyPI package `paper-digest` is unrelated (an arXiv-to-Markdown converter). | **Avoid** |
| [ArxivDigest](https://github.com/AutoLLM/ArxivDigest) | Last commit Jul 2023 | **Avoid** |
| [pyEuropePMC](https://github.com/JonasHeinickeBio/pyEuropePMC) | Very active (4.8.0, Nov 2026; \~295 commits in 6 months), so APIs churn | **Defer;** call Europe PMC's REST API directly if ever needed |
| [paperscraper](https://github.com/jannisborn/paperscraper) | Keyword dumps of PubMed/arXiv/bioRxiv/ChemRxiv to files; no incremental state | **Avoid** for this job |
| [dedupe](https://github.com/dedupeio/dedupe), [Splink](https://github.com/moj-analytical-services/splink) | Machine-learning record linkage for millions of rows | **Avoid;** overkill for hundreds of papers |

> **Level up: reading a dependency like a pro.** Before trusting a library, check four things: license (can IBM use it?), last release date (is it alive?), who maintains it (one person or a team?), and how it fails (does it retry, or crash?). PyAlex's default of zero retries is the kind of detail you only find by reading the source, and it would have caused your first mystery failure.

## C. Data source comparison

**MVP stack: OpenAlex and arXiv for discovery, Crossref for lookups by DOI.** Only three sources find papers independently: OpenAlex (by institution), arXiv (fastest for preprints) and PubMed (fast for biomedical journals). Everything else mostly enriches or duplicates them. OpenAlex is the backbone because it is the only free source that can filter on IBM and Cleveland Clinic affiliations in one query.

| Source | Role here | Access and limits (checked 12 Nov 2026) | Incremental polling | Preprint ↔ journal linking | Phase |
| --- | --- | --- | --- | --- | --- |
| [OpenAlex](https://help.openalex.org/api/authentication/) | **Discovery backbone.** Filter works by both institutions; carries DOI, PMID, arXiv, ORCID, ROR. | Free account key gives $1/day of usage. A filtered list call costs $0.10 per 1,000 ([costs](https://help.openalex.org/access/example-costs/)), so about 10,000 per day; lookups by ID are free. 30 requests/s with a key, 10 without. Cursor paging past page 1 needs a key. | "Updated since" filters now need a paid plan ([filtering](https://help.openalex.org/api/filtering/)). Re-pull the full set and diff locally instead. | Strong. Merges preprint and journal versions into one work with several locations, each tagged submitted/accepted/published ([locations](https://help.openalex.org/data/locations/)). Not perfect, so keep your own matcher. | **V1** |
| [arXiv API](https://info.arxiv.org/help/api/tou.html) | **Fastest preprint discovery**, by author watchlist. | Free, no key. Max one request every 3 seconds, one connection at a time. Metadata is CC0. | Sort by last-updated date; stop at the last date seen. | Authors may add `doi` and `journal_ref` after publication; often missing. | **V1** |
| [Crossref](https://crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/) | **Enrichment by DOI:** journal, dates, retractions and corrections. Weak for discovery (affiliations are sparse). | Free, no key. Public pool: 5 requests per interval, 1 at a time. Add `mailto` for the polite pool: 10 per interval, 3 at a time. | `from-update-date` filter is free. | Publisher-deposited `has-preprint` / `is-preprint-of` relations; many are missing ([Crossref](https://crossref.org/blog/discovering-relationships-between-preprints-and-journal-articles/)). arXiv DOIs are DataCite, so not covered. Retractions appear in `update-to` ([Crossref](https://www.crossref.org/blog/retraction-watch-retractions-now-in-the-crossref-api/)). | **V1** (lookups only) |
| [PubMed E-utilities](https://www.ncbi.nlm.nih.gov/books/NBK25497/) | Early biomedical discovery; affiliation search; PMIDs. | Free. 3 requests/s without a key, 10 with a free NCBI key. Register `tool` and `email`; run big jobs nights or weekends. | Entry-date range on `esearch`. | None for arXiv. Misses physics and CS venues. | **V2** (you already have its RSS → Slack) |
| [Europe PMC](https://academic.oup.com/nar/article/52/D1/D1668/7442539) | Biomedical preprints (bioRxiv, medRxiv, ChemRxiv, 31 servers) with links to published versions. | Free REST API. | Date filters in queries. | Good for biomedical preprints. **arXiv only for COVID-19 full text,** so useless for quantum preprints. | **V2, optional** |
| [Semantic Scholar](https://semanticscholar.org/product/api) | Citation and related-paper discovery. | Anonymous calls share one pool across all users and get throttled; a free key starts at 1 request/s. | Limited. | `externalIds` maps DOI, arXiv and PMID. | **V3** |

**Also considered:** bioRxiv, medRxiv and ChemRxiv mint Crossref DOIs, so OpenAlex and Crossref already reach them. DBLP covers computer-science venues that OpenAlex also covers. ORCID author-work lists are useful for V3 watchlists. OpenAIRE overlaps OpenAlex and was not evaluated in depth.

**Watch-out:** OpenAlex changed its access model twice this year. A January 2026 announcement made keys mandatory from 13 Feb ([OpenAlex users group](https://groups.google.com/g/openalex-users/c/rI1GIAySpVQ)); current docs again allow keyless use on a small budget. Get a free key anyway, and re-check limits before you depend on them.

> **Level up: discovery vs enrichment.** Pros separate "where do I *find* things?" from "where do I *look up details*?" Discovery sources need broad, cheap queries. Enrichment sources need fast lookups by ID. Mixing the two roles is how systems end up slow and expensive.

## C2. Your current arXiv and PubMed feeds

**Reuse your arXiv query unchanged as V1's arXiv configuration, with four fixes; keep the PubMed feed as your Slack alert until V2.** The arXiv query already encodes months of judgment about who and what to watch; rewriting it would throw that away. I could not run either feed from my research environment (both sites block automated fetches from it), so this review is of the query text, not its results.

**What the arXiv query does today:** (15 Cleveland Clinic-side researchers, with a spelling variant for one, OR "Cleveland Clinic" anywhere in the text) AND (the quant-ph category OR one of 16 quantum terms), newest submissions first, up to 200 results.

| # | Issue | Why it matters | Fix | When |
| --- | --- | --- | --- | --- |
| 1 | Sorted by **submission** date | A paper that later gains a journal DOI or a new version never resurfaces, so preprint → journal updates are missed | Sort by last-updated date, and each week re-fetch every known arXiv ID in batches (`id_list`) to read new `doi` / `journal_ref` values | V1 |
| 2 | No IBM-side names | The pair rule can't run on arXiv; some hits may be Clinic papers without IBM | Add the IBM co-authors who appear on collaboration papers. Until then, tag arXiv hits "IBM unconfirmed" and let OpenAlex confirm | V1 |
| 3 | A few names are common enough to collide with other quantum researchers | False positives | Mark hits matched only by a common name as `uncertain`; switch to ORCID or OpenAlex author IDs in V3 | V1 |
| 4 | `all:ibm_cleveland` | Looks like a tag rather than text that appears in papers, so it probably matches nothing | Run it alone once; drop it if it returns zero | Now |

Two parts are worth keeping as they are. The topic clause gates everything, which risks missing a collaboration paper that uses none of the 16 terms; but without it, Clinic authors' non-quantum papers would flood the feed, and OpenAlex's institution query is the recall backstop. Test any extra terms (for example, method names your SOWs use) against the V1 back-test before adding them. The all-fields "Cleveland Clinic" term only catches abstracts and comments, because arXiv rarely stores affiliations, but it is harmless.

**PubMed feed:**

- The RSS link points to a saved search ID and hides the actual query, so code can't reuse it. Copy the search string from the saved search in PubMed (My NCBI → Saved Searches); that string becomes the V2 E-utilities query.
- `limit=15` caps each fetch at 15 items. Fine for Slack if fewer than 15 matches arrive between checks; a bigger burst is silently cut. E-utilities has no such cap.
- I'd skip reading this RSS feed in V1. The back-test will show whether PubMed finds papers OpenAlex misses, which tells you whether a PubMed lane is worth building at all.

**Free test data:** both feeds date from about 18 Sep 2026 (per the PubMed feed's name and creation stamp). Add to V1's gate: the tool must catch every collaboration paper the two feeds surfaced since then.

> **Level up: migrate, don't replace.** A working system encodes decisions nobody wrote down. Port it unchanged first, prove the new system catches at least everything the old one did (a parallel run), then improve one change at a time so you can tell which change helped.


## C3. Master workbook: what profiling the real trackers changed

The master keeps Publications-ALL's 13 columns first, then the Cleveland Clinic quantum list's 18 columns, then 5 new ones (`docs/MASTER_COLUMNS.md`). A trial merge of sanitized copies of the two trackers, done outside this repository, changed four parts of the plan. No tracker data is included here.

| Finding | Plan change |
| --- | --- |
| Publications-ALL had no DOI, arXiv or PubMed columns, and `Name` is a composed label ("Venue: nickname, date"), not the paper's title | Match the master on its ID columns, then on shared author surnames + date. Never on `Name` |
| The Cleveland Clinic quantum list stored IDs only inside hyperlinks behind the words "arXiv", "PubMed", "DOI" | The merged master stores IDs as text; the tool reads hyperlink targets as a fallback |
| The tracker counts some Clinic-only quantum papers that list no IBM authors | The IBM + Clinic pair rule can't be the only gate: lane B (Clinic + quantum) and the arXiv lane feed a review band |
| The existing arXiv author query returns collaborators' entire careers, back to 2011 | Every lane enforces a `start_date` (default 2021-01-01), including the first backfill |
| Some papers listed as preprints have since appeared in journals, and some works appear as both a preprint row and a journal row | Exactly the updates V1 must detect; the weekly arXiv re-check and `Same work as` column exist for this |
| Many master rows are talks, posters and short papers | Rarely indexed anywhere; they stay manual, and the back-test covers journal articles and preprints only |

> **Level up: profile the data before you design the code.** One hour with the real spreadsheets changed the matching key, the relevance rule and the test gate. Professionals call this data profiling, and it is the cheapest bug-prevention there is.

## D. Proposed system architecture

Data moves one way: public sources feed a history database, and the only thing that crosses into the internal zone is public records. Nothing flows back into the master workbook.

```
            ZONE 1 — public metadata only (laptop now; approved scheduler later)
 ┌──────────────────────────────────────────────────────────────────────────────┐
 │  OpenAlex (lanes A, B)   arXiv (lane C + weekly re-check)   Crossref (DOI)    │
 │   Fetch (+retries, raw JSON saved) → Normalize → Match + dedupe → History DB  │
 └───────────────────────────────────────────────────────────────────┬──────────┘
                                                                     │ public records only
            ZONE 2 — IBM machines only (internal data)               ▼
 ┌──────────────────────────────────────────────────────────────────────────────┐
 │  Master workbook (read-only) → Reconcile → Candidates CSV → Human review      │
 │                                    ▲──── decisions (import) ──────┘           │
 └──────────────────────────────────────────────────────────────────────────────┘
```

Zone 1 handles only public metadata, so it can move to a scheduler in V2 without moving any internal data. Zone 2 reads the master (read-only) and your past decisions, and the reviewer's decisions loop back so a rejected paper stays rejected. In V2 a Slack digest reads the same candidates file; it adds no new data path.


## Uncertainties and sources

Nothing here was tested against the live APIs: my research environment could not reach OpenAlex or arXiv, so every API claim comes from official documentation and library source code. The first V1 session should confirm the items below.

### Open questions to verify

- [x] **Two-institution OpenAlex filter.** Verified live 12 Nov: `lineage:I1341412227+I1316902750` since 2021 returns 92 works, among them collaboration papers already in the trackers, at least one quantum preprint missing from both, and items that are not papers (a dataset, an erratum, conference abstracts), which led to the work-type rules in SPEC §4.
- [x] **Which OpenAlex IDs represent IBM.** Resolved 12 Nov: parent `I1341412227` covers the IBM Research labs through `lineage`; IBM Japan, Ltd. and IBM Research and Development Inc. sit outside it. Cleveland Clinic's parent is `I1316902750`; Abu Dhabi, Akron General and London sit outside it.
- [ ] **OpenAlex indexing lag** for new papers (not measured; the weekly full re-pull is designed to absorb it).
- [ ] **Matching thresholds** (95 / 85, year window −1 to +3) are starting points borrowed from Crossref's approach, not tuned on your papers.
- [ ] **IBM approval** for Codex cloud and a Slack webhook, and whether Codex can work with IBM's GitHub once it is back up.
- [ ] **GitHub's free private-repo allowance** is stated as $12/month; "about 2,000 minutes" is my arithmetic at the Linux rate.
- [ ] **Codex cloud needs a github.com repository.** A third-party guide checked against Codex docs in late September 2026 says GitLab and self-hosted GitHub Enterprise Server aren't supported ([flaviocopes.com](https://flaviocopes.com/codex-cloud.md)); OpenAI's environment docs describe tasks checking out "your repo" ([Codex cloud environments](https://learn.chatgpt.com/docs/environments/cloud-environment)). Confirm whether IBM's GitHub is reachable from Codex cloud before planning on it.
- [ ] **lit-monitor and paper-digest** GitHub sources were not publicly reachable (private, renamed or deleted). Open-issue counts for all repos were not checked.

- [ ] **The PubMed saved-search query string**, for the V2 E-utilities lane.

### Sources (opened 12 Nov 2026)

APIs and platforms:

- [OpenAlex: authentication and rate limits](https://help.openalex.org/api/authentication/) · [pricing](https://help.openalex.org/access/pricing/) · [example costs](https://help.openalex.org/access/example-costs/) · [alerts](https://help.openalex.org/api/alerts/) · [filtering](https://help.openalex.org/api/filtering/) · [locations and versions](https://help.openalex.org/data/locations/)
- [OpenAlex users group: API keys required starting Feb 13](https://groups.google.com/g/openalex-users/c/rI1GIAySpVQ)
- [Crossref: REST API access and rate limits](https://crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/) · [preprint–article relationships](https://crossref.org/blog/discovering-relationships-between-preprints-and-journal-articles/) · [retractions in the API](https://www.crossref.org/blog/retraction-watch-retractions-now-in-the-crossref-api/)
- [arXiv API terms of use](https://info.arxiv.org/help/api/tou.html) · ["Legacy arXiv API" question](https://groups.google.com/g/arxiv-api/c/nC24V9g7skA)
- [NCBI E-utilities usage guidelines](https://www.ncbi.nlm.nih.gov/books/NBK25497/)
- [Europe PMC in Nucleic Acids Research, 2024](https://academic.oup.com/nar/article/52/D1/D1668/7442539) · [Europe PMC preprint versions (Infodocket)](https://www.infodocket.com/2020/03/04/how-does-europe-pmc-handle-multiple-versions-a-preprint/)
- [Semantic Scholar API](https://semanticscholar.org/product/api)
- [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions) · [schedule event](https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows) · [dependency caching](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching)
- [Codex cloud: agent internet access](https://learn.chatgpt.com/docs/cloud/internet-access)
- [Git scraping pattern (Simon Willison)](https://simonwillison.net/2020/Oct/9/git-scraping/)
- [Paper Digest FAQ](https://www.paperdigest.org/frequently-asked-questions/)
- [Cleveland Clinic newsroom, June 2026 forum](https://newsroom.clevelandclinic.org/2026/06/15/cleveland-clinic-and-ibm-forum-highlights-advancements-in-ai-and-quantum-computing-for-healthcare-research)

Code: every repository in section B with a last-commit date was cloned and its git history, license file and relevant modules read; lit-monitor's published package was downloaded and inspected; versions and release dates came from each project's [PyPI](https://pypi.org/) record.
