# pubmon — publication monitor

`pubmon` finds public scientific papers connected to the IBM–Cleveland Clinic collaboration,
links preprints to journal versions, and exports **one row per paper** for human review.
Several changes to a paper stay on that same row. Uncertain matches remain separate and flagged.
The application never updates your master workbook or copies its manual decision columns.

The six V1 implementation milestones are complete. Offline tests and synthetic end-to-end
checks pass; **live API access, real-world recall and two weekly validation runs are still
pending**. A successful demo does not establish that live collection finds the right papers.
See [the requirements review](docs/V1_REVIEW.md) for the evidence and remaining validation.

## Where the work happens

| Place | Role |
| --- | --- |
| Personal GitHub: `josephbns/paper-pull` | Stores code, documentation and synthetic/public test fixtures |
| Codex cloud | Edits and tests the checkout; runs synthetic demos and authorized public-API checks |
| Your approved IBM machine | Holds the real workbook, review notes and local reconciliation outputs |

The owner's instruction to use personal GitHub supersedes the build pack's old advice to
wait for work GitHub. It does not move the real workbook or internal data into the repository.

## 1. Install on Windows PowerShell

Install Python **3.11 or newer** from [python.org](https://www.python.org/downloads/windows/).
Enable the installer option that adds Python to PATH. Install Git if needed from
[git-scm.com](https://git-scm.com/downloads/win). Then open PowerShell:

```powershell
git clone https://github.com/josephbns/paper-pull.git
Set-Location paper-pull
py -3 --version
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
pubmon --help
```

These clone commands are for a first local checkout. In an existing checkout, open that
folder instead. If PowerShell blocks activation, use `.\.venv\Scripts\python.exe` in place
of `python` and `.\.venv\Scripts\pubmon.exe` in place of `pubmon`; changing system execution
policy is not required. Development checks ran on Linux; native Windows execution is not yet
verified.

For a new terminal later, reopen this folder and activate the same virtual environment.
No database server, web server, Node.js or extra service needs starting.

## 2. Try a fully offline demo first

No account, email or API key is needed for these commands:

```powershell
pubmon run --dry-run --master tests/fixtures/synthetic_master.xlsx --fixtures tests/fixtures/api
pubmon run --backfill --no-master --fixtures tests/fixtures/api --xlsx
pubmon status --demo
pubmon backtest --demo --master tests/fixtures/synthetic_master.xlsx --since 2023-01-01
```

The first command leaves no persistent database or output files. The next commands use
ignored `demo/data/` and `demo/out/`, completely separate from live `data/` and `out/`.
`--fixtures` never falls back to an API. Fixture replay uses the fixture's last update date
as its replay clock, rather than pretending to be a current live search.

The supplied API fixture corpus intentionally covers different records from the synthetic
master workbook. Its demo back-test can report zero recall; that demonstrates miss reporting,
not a measurement of live discovery quality. Unit tests also use a controlled history with
known matches to verify the recall calculation.

## 3. Get the live API information when ready

| Source | What you need |
| --- | --- |
| OpenAlex | Sign in at [openalex.org](https://openalex.org/) and obtain your API key from your account |
| arXiv | No registration or key for the query API |
| Crossref | No key for these public requests; provide a contact email |

`PUBMON_EMAIL` is a contact address used in scholarly API requests. It is not an Outlook
login, and the application does not read your mailbox or require an Outlook password.

Set process variables in PowerShell without putting the literal key into command history:

```powershell
$pubmonKey = Read-Host "OpenAlex API key" -AsSecureString
$env:OPENALEX_API_KEY = [System.Net.NetworkCredential]::new("", $pubmonKey).Password
$env:PUBMON_EMAIL = Read-Host "API contact email"
Remove-Variable pubmonKey
```

These variables last for the current PowerShell session. Alternatively, copy `.env.example`
to a local `.env` and edit it privately; `.env` is ignored by Git. Existing process variables
have priority over `.env`. Never put real values in `.env.example`, Python code or GitHub commits.

In Codex cloud, use the environment's secret field for `OPENALEX_API_KEY` and runtime variable
field for `PUBMON_EMAIL`. The required **network domains**, which are not keys, are:

```text
api.openalex.org
export.arxiv.org
api.crossref.org
```

Their allowlist and credential requirements have been saved as a configuration draft, not
verified as applied. Review/save them in environment settings and publish the updated
configuration when ready. Do not paste a key into chat. Live validation was deferred by the
owner until mailbox/account setup is available.

## 4. Prepare your local settings and watchlist

Copy the public templates only if local files do not already exist:

```powershell
if (!(Test-Path config/settings.toml)) { Copy-Item config/settings.example.toml config/settings.toml }
if (!(Test-Path config/watchlist.csv)) { Copy-Item config/watchlist.example.csv config/watchlist.csv }
```

Open `config/settings.toml` in a text editor. It holds the start date, institution IDs,
matching thresholds, query/watchlist paths and optional master path. Edit the existing
`[master]` section rather than adding a duplicate section. Credentials stay in
process variables or `.env`. For a Windows master path, a TOML literal string avoids
backslash escaping:

```toml
[master]
path = 'C:\Research\Publications_Master.xlsx'
```

Keep the real workbook outside the checkout, on your approved machine. Paths in settings
are relative to the project directory unless absolute. `--master` overrides the configured
path; `--no-master` explicitly skips workbook reconciliation.

The institution IDs in the template come from the build pack. Confirm their scope with:

```powershell
pubmon resolve-institutions "Cleveland Clinic" "IBM"
```

This prints candidates with IDs, ROR, country, work counts and lineage. It never edits
settings automatically. Decide whether the additional IBM/Clinic entities listed in the
settings TODO belong; do not guess replacement IDs.

Review `config/watchlist.csv`: columns are `name,side,orcid,arxiv_name`, with side `IBM` or
`CC`. The example has Clinic-side names; add approved public IBM-side author names to enable
IBM confirmation on arXiv. Put collision-prone names in `arxiv.common_names` in settings.
The existing query in `config/arxiv_query.txt` is used verbatim.

## 5. Run the first live backfill

After credentials and API access are ready, run this on the approved machine with your real
master. The path below is an example; select your actual local file:

```powershell
$pubmonMasterPath = Read-Host "Local master workbook path"
pubmon run --backfill --master $pubmonMasterPath --xlsx
pubmon status
```

`--backfill` searches from the configured `start_date`, initially `2021-01-01`. The normal
run creates a consistent SQLite backup, records source failures explicitly, and writes
candidate CSV, optional Excel, and full-work snapshot paths in its summary.

Live history is `data/pubmon.db`; raw responses and logs are under `data/raw/` and `data/logs/`.
No missing source result deletes known history. A `partial` run returns exit code 2; inspect
its source counts and logs before treating the collection as complete.

For a live rehearsal, add `--dry-run`. It still calls APIs but uses a disposable copy of
history, discarding database changes, logs, raw archives and exports. A live dry-run needs
credentials; the explicitly offline demo in section 2 does not.

## 6. Review one row per paper

Open the candidate CSV (UTF-8 with BOM) or its optional Excel copy. A linked paper carries
both its journal DOI and arXiv ID. `events` lists distinct event kinds, `changes` includes all
material changes, and `versions` describes source versions. A possible duplicate stays on
its own row with `possible_duplicate_of`; it is not silently merged.

The full `works_<date>.csv` snapshot contains every paper once, including rejected papers.
Multiple existing master version rows can appear together in `master_pub_id` on one paper
row. That is reconciliation information, not an official publication count.

Copy the candidate CSV before reviewing it, then fill only `decision` and `reviewer_note`.
Keep `work_key`, identifiers and headers unchanged. If using Excel, save the reviewed copy
as **CSV UTF-8**, not an Excel workbook, before importing it.

| Decision | Effect |
| --- | --- |
| `accepted` | Remember acceptance |
| `rejected` | Suppress repeats until a later material change |
| `not_collab` | Same suppression for an out-of-scope paper |
| `merge:<target_work_key>` | Explicitly approve combining this paper with that existing identity |
| Blank | Leave the decision unchanged |

Import the reviewed copy:

```powershell
$pubmonReviewedCsv = Read-Host "Path to reviewed CSV copy"
pubmon import-decisions $pubmonReviewedCsv
```

For synthetic reviews use `pubmon import-decisions --demo PATH`. Re-importing unchanged
reviews is harmless. Invalid rows are reported with their row numbers and skipped. Merges
preserve identifiers and events, with aliases for old reviewed keys.

A same-day rerun uses a run-suffixed output filename, preserving prior review files. Files
are renamed atomically before event export markers are committed. Do not review output from
a run reported as failed; those events remain pending for retry. Apply any desired tracker
updates by hand; the application never saves the master workbook.

## 7. Measure recall with the back-test

After a backfill, on the approved machine:

```powershell
pubmon backtest --master $pubmonMasterPath --since 2023-01-01
```

This makes **no network requests**. It opens the workbook and history read-only, reports
recall and misses (Pub ID and Name), and writes a new `out/backtest_<date>.csv` without
replacing an existing report. It does not import decisions, change history or save the master.

Eligible rows have type `Peer Reviewed Journal`, `Open Publication` or `Review Paper`, status
`Published` or `Accepted`, and a complete publication date on/after `--since` (inclusive).
Other rows stay in the report with an exclusion reason. Missing dates are explicit exclusions.
Matches use DOI/arXiv/PMID, then two shared author surnames plus a date within 30 days only
for master rows without IDs. `Name` is display-only. Ambiguous matches are reported as misses.

`recall = found eligible rows / all eligible rows`. If no rows are eligible, recall is null,
not 100%. Two legacy preprint/journal rows may both match one paper, so this is **tracker-row
recall**, not a deduplicated publication total or a manual counting decision.

The proposed V1 validation gate is at least 90% recall on the scoped real master since 2023,
every miss explained, coverage of papers surfaced by current feeds, two weekly runs with no
repeat candidates, and no wrong merges found during review. Running the command successfully
does not mean the gate is met; the command reports results even below 90%.

## 8. Run weekly

In the same configured environment:

```powershell
pubmon run --master $pubmonMasterPath --xlsx
pubmon status
```

OpenAlex re-pulls the configured period each run. arXiv normally looks back 90 days by update
time and rechecks every known arXiv ID for a newly added DOI/journal reference. Review and
import decisions again. Scheduling, Slack and GitHub Actions are V2 work; V1 is run manually.

## 9. Run development checks

```powershell
python -m pytest -o addopts='' -q --block-network
ruff check .
ruff format --check .
python -m pip check
```

Tests use synthetic data and public ID pairs. The default pytest configuration blocks network.
Three optional source-recording checks are skipped until real cassettes exist. To explicitly
record public API responses after access is ready:

```powershell
python -m pytest tests/test_source_recordings.py --record-mode=once
```

Recordings remove API-key/contact query parameters and authorization/User-Agent headers.
Inspect cassettes for secrets before committing. Afterwards they replay offline. All API
access was still blocked/unconfigured at the last live attempt; offline tests do not replace
live validation.

## 10. Keep these out of GitHub

Never commit real workbooks, raw/live history, review decisions or notes, generated outputs,
keys or contact emails. `.gitignore` covers `.env`, local settings/watchlists, `data/`, `out/`,
`demo/`, and spreadsheets except synthetic fixtures. Check `git status --short` before a commit.
Use only public or synthetic fixtures in this repository and in cloud development.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Missing environment variables | Set the key/contact email in this terminal; use environment settings in cloud |
| Proxy tunnel `403` | Apply the required API domain allowlist; it is separate from GitHub access |
| Missing watchlist | Copy and review the example; the app will not guess missing names |
| Missing master columns | Check the documented header row; do not rename tracker columns automatically |
| No history for back-test | Run a committed backfill first; a dry-run does not create history |
| Partial run | Inspect `pubmon status` and the run log; a source outage is not an empty search |
| Zero candidates on rerun | Expected if nothing material changed; the full snapshot still includes known papers |

For Linux/cloud shells, activate with `source .venv/bin/activate`; the `pubmon` commands are
the same. Each cloud task already has an isolated checkout; no Git worktree is needed.
See [SPEC](docs/SPEC.md), [work plan](docs/WORK_PLAN.md), [security](docs/SECURITY.md),
[column rules](docs/MASTER_COLUMNS.md), and [changelog](docs/CHANGELOG.md) for details.
