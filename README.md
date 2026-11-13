# pubmon — publication monitor

`pubmon` finds public scientific papers connected to the IBM–Cleveland Clinic collaboration,
links preprints to journal versions, and exports **one row per paper** for human review.
Several changes to a paper stay on that same row. Uncertain matches remain separate and flagged.
The application never updates your master workbook or copies its manual decision columns.
With `--xlsx`, it also creates a **new master-format Excel file containing all collected
papers**, including history with no new events. This is separate from any existing master.

The six V1 implementation milestones are complete. Offline tests and synthetic end-to-end
checks pass; **live API access, real-world recall and two weekly validation runs are still
pending**. A successful demo does not establish that live collection finds the right papers.
See [the requirements review](docs/V1_REVIEW.md) for the evidence and remaining validation.

**New here?** Start with [docs/SETUP.md](docs/SETUP.md): accounts and keys to sign up for,
installation, setting up a QIC profile, first run, and moving the project to IBM's GitHub.

## Where the work happens

| Place | Role |
| --- | --- |
| Personal GitHub: `josephbns/paper-pull` | Stores code, documentation and synthetic/public test fixtures |
| Codex cloud | Edits and tests the checkout; runs synthetic demos and authorized public-API checks |
| Your approved IBM machine | Holds the real workbook, review notes and local reconciliation outputs |

The owner's instruction to use personal GitHub supersedes the build pack's old advice to
wait for work GitHub. It does not move the real workbook or internal data into the repository.

## 1. Install on Windows PowerShell

### Run manually on GitHub instead

In repository Settings → Secrets and variables → Actions, add repository secrets
`OPENALEX_API_KEY` and `PUBMON_EMAIL`. Do not put their values in repository files.

Open **Actions → Generate candidate Excel → Run workflow**, select `main`, type the profile
name (default `cleveland-clinic`), then click **Run workflow**. After it finishes, open that
run and download the `publication-candidates-<profile>-<run number>` artifact under **Artifacts**. Extract the ZIP and
open **`master_<date>.xlsx`** for the complete generated tracker. The candidate `.xlsx`
contains only new/changed papers. Downloads require signing in to GitHub.

Both Excel files follow one house style (`src/pubmon/xlsx_style.py`): Arial 10, navy
header row, black text for source data, blue for columns entered by hand, green for links,
thin grey rules, frozen header and first column, and landscape pages that print one page wide.
The generated master has a sortable, filtered **Publications** sheet in the approved
36-column layout, a **Sources** sheet with all authors, identifiers and version history,
and **Read me** notes. DOI/arXiv/PubMed/OpenAlex cells link to public records. It preserves
uncertain duplicates as separate flagged rows and labels correction/retraction notices.
It fills public metadata; official count, SOW, theme and other manual fields stay blank.
All authors appear in Authors. IBM Authors and CC and other Authors contain names with
matching OpenAlex IBM/partner affiliations, respectively; other authors remain in Authors.
After the original 36 columns, **Why selected**, **Discovery routes**, **Partner affiliation
authors**, institution names, separate IBM/partner watchlist matches, evidence links and
affiliation-evidence status explain each row. **Affiliation evidence** provides the matched
author, institution ID/lineage, configured profile ID and source publication link. Partner
columns refer to CCF by default and follow the configured partner profile. Name matches and
query inclusion alone never establish affiliation; missing ties remain unverified.
Evidence may come from any stored linked publication version. Review scope
flags before treating the collected set as confirmed collaboration publications.
AUTO Pub IDs are stable within a history database, but change on fresh GitHub backfills.

The workflow runs offline tests, lint/format/dependency checks, a synthetic dry run, fresh
live source tests, then `pubmon run --backfill --no-master --xlsx`. Source-test failure stops
collection. A partial collection fails the workflow; any remaining files are incomplete.
It uses only public source metadata and never reads or updates the real master workbook.
Artifacts expire after 14 days; download the ones you need. Each export creates a new file
and refuses to overwrite an existing review/master export.

Each manual run starts with fresh history, so it produces a new full backfill and can repeat
papers from earlier runs. This is initial public-source validation and Excel generation;
persistent weekly state and scheduling remain future work. The existing public profile
still needs institution/watchlist review before relying on discovery coverage.

### Install locally

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

No account, email or API key is needed for these commands. Every command needs a profile;
the first line sets it for this PowerShell window (step 3 shows how to save it in `.env`):

```powershell
$env:PUBMON_PROFILE = "cleveland-clinic"
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
| OpenAlex | Make a free account at [openalex.org](https://openalex.org/), then copy your key from [openalex.org/settings/api](https://openalex.org/settings/api) |
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

## 4. Personalize the collaboration in one profile

Each QIC has one profile file in `profiles/`. The complete Cleveland Clinic profile is
`profiles/cleveland-clinic.toml`; new QICs start from `profiles/TEMPLATE.toml.example`.
A profile holds only public criteria (institution IDs, topic terms, names of authors on
public papers), so it is committed to Git and its changes are tracked. Check one, without
calling any API, with:

```powershell
pubmon --profile cleveland-clinic check-profile
```

It prints the partner, institution IDs, people counts, topic terms and the exact arXiv
search the profile builds. Typos and missing settings stop with a message naming the
section and key. Choose the profile with `--profile <name>`, or save `PUBMON_PROFILE=<name>`
in `.env`; there is no default profile.

People are listed once each. `side = "partner"` people find papers (their names build the
arXiv search); `side = "ibm"` people only confirm papers. `tab = "backup"` sends papers found
only through that person to the generated workbook's Backup sheet. Topic terms fill the
**Quantum?** column (Yes / Maybe / No); hardware terms fill **IBM hardware (suggested)** for
papers with no IBM author.

The real master path never goes in a profile. Put it in `.env` as
`PUBMON_MASTER=C:\Research\Publications_Master.xlsx`, or pass `--master <path>`. Keep the
workbook outside the checkout on your approved machine. `--no-master` skips reconciliation.
All profiles currently require the same approved workbook column layout.

See [the setup guide](docs/SETUP.md) to create a profile for another QIC and
[the customization reference](docs/CUSTOMIZATION.md) for every setting. An existing local
`config/settings.toml` still works when no profile is named.

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

Open the candidate CSV (UTF-8 with BOM) or its optional Excel copy. The Excel copy leads with
the title, then the columns you fill in (`decision`, `reviewer_note`, in blue), with IDs last;
its Read me sheet repeats these instructions. A linked paper carries
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
Optional `workspaces/` runtime directories are also ignored.

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
