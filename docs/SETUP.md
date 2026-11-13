# Setup guide: from zero to your first run

This guide is for anyone at IBM setting up `pubmon` for a Quantum Innovation Center (QIC):
the Cleveland Clinic team, or a colleague adapting it to another QIC. It assumes no coding
background. Commands are for Windows PowerShell; Mac/Linux differences are noted.

Steps 1–4 happen once per computer. Step 5 happens once per QIC. Steps 6–7 are routine.

## 1. Sign up for the accounts and keys

| What | Where to get it | Cost | Why `pubmon` needs it |
| --- | --- | --- | --- |
| GitHub account | [github.com/signup](https://github.com/signup), or your IBM GitHub access (see step 8) | Free | Download the code; run collections in the cloud with GitHub Actions |
| Python 3.11 or newer | [python.org/downloads](https://www.python.org/downloads/) | Free | Runs the program |
| Git | [git-scm.com/downloads](https://git-scm.com/downloads) | Free | Copies the code to your computer and back |
| OpenAlex account and API key | Make an account at [openalex.org](https://openalex.org/), then copy your key from [openalex.org/settings/api](https://openalex.org/settings/api) | Free daily allowance | OpenAlex is the main source of papers and author affiliations |
| A contact email | Your own address | — | OpenAlex and Crossref ask callers to identify themselves; nothing is sent to it |
| A text editor (optional) | [code.visualstudio.com](https://code.visualstudio.com/) | Free | Easier than Notepad for editing profiles |

You do **not** need accounts for arXiv, Crossref or ORCID. arXiv and Crossref are read
without a key. ORCID IDs (unique researcher IDs) can be looked up at
[orcid.org](https://orcid.org/) without signing in. A PubMed key from NCBI is planned for a
later version and is not needed yet.

When installing Python on Windows, tick **"Add python.exe to PATH"** on the first screen.

Treat the OpenAlex key like a password: never paste it into a file that goes on GitHub,
into chat, or into an email. If it leaks, make a new one at openalex.org/settings/api; the
old one stops working immediately.

## 2. Copy the code to your computer

Open PowerShell (Start menu → "PowerShell") and run, one line at a time:

```powershell
git clone https://github.com/josephbns/paper-pull.git    # use your team's copy once moved
Set-Location paper-pull
py -3 -m venv .venv                                       # Mac/Linux: python3 -m venv .venv
.\.venv\Scripts\Activate.ps1                              # Mac/Linux: source .venv/bin/activate
python -m pip install -e ".[dev]"
pubmon --help
```

`.venv` is a **virtual environment**: a private copy of Python for this project, so its
libraries do not clash with anything else on your computer. Each time you open a new
PowerShell window, `Set-Location` into the folder and run the `Activate.ps1` line again.

If PowerShell refuses to run `Activate.ps1`, skip it and type `.\.venv\Scripts\pubmon.exe`
wherever this guide says `pubmon`.

## 3. Store your private settings

Private values live in a file named `.env` in the project folder. Git ignores it, so it never
reaches GitHub. Create it from the blank example:

```powershell
Copy-Item .env.example .env
notepad .env
```

Fill in:

```dotenv
OPENALEX_API_KEY=paste-your-key-here
PUBMON_EMAIL=you@example.com
PUBMON_PROFILE=cleveland-clinic
PUBMON_MASTER=C:\Research\Publications_Master.xlsx
```

- `PUBMON_PROFILE` is the profile used when a command does not say `--profile`.
- `PUBMON_MASTER` is optional: the path to your real master workbook. `pubmon` only ever
  reads it. Keep that workbook outside the project folder.

## 4. Try it offline (no key needed)

These commands replay recorded sample data, so they work before your key is set up:

```powershell
pubmon --profile cleveland-clinic run --dry-run --master tests/fixtures/synthetic_master.xlsx --fixtures tests/fixtures/api
pubmon --profile cleveland-clinic run --backfill --no-master --fixtures tests/fixtures/api --xlsx
```

The second command writes sample files under `demo/out/`. Open the `master_<date>.xlsx` file
to see the layout you will get from a real run.

## 5. Set up a profile for your QIC

A **profile** is one settings file in `profiles/` that describes one QIC: its institution,
its researchers, and the topic. It contains only public information, so it is shared on
GitHub, and every change to it is recorded in the project's history. The Cleveland Clinic
profile, `profiles/cleveland-clinic.toml`, is complete and is the best example to read.

To start a new QIC:

1. **Copy the blank template.** Use lowercase and hyphens in the name:

   ```powershell
   Copy-Item profiles/TEMPLATE.toml.example profiles/my-qic.toml
   notepad profiles/my-qic.toml
   ```

2. **Name the partner and choose a workspace.** Fill in `[qic]`. If the partner hosts an IBM
   system, list its names in `onsite_hardware` (Cleveland Clinic: `ibm_cleveland`). `workspace` is the folder
   for this QIC's history and outputs, such as `"workspaces/my-qic"`. Never share a workspace
   between QICs: the history database would mix their papers.

3. **Find the partner's OpenAlex institution ID.** Run:

   ```powershell
   pubmon --profile my-qic resolve-institutions "Partner University Name" "IBM"
   ```

   It prints candidate IDs (they start with `I`) and changes nothing. Check the candidates on
   [openalex.org](https://openalex.org/) by searching the institution name. Prefer the parent
   institution: its ID covers its labs and hospitals through OpenAlex's "lineage". Put the
   chosen ID in `[institutions] partner`. The IBM parent ID is already filled in.

4. **List the people.** Add one `[[people]]` entry per researcher, once each.
   - `side = "partner"` people **find** papers: their names build the arXiv search.
   - `side = "ibm"` people only **confirm** papers. Do not search for IBM people: that would
     pull in every quantum paper they write, with or without the partner.
   - `aliases` holds other spellings seen on papers (middle initials, hyphens, accents).
   - `tab = "backup"` sends papers found only through that person to a separate Backup tab.
   - Only list names that already appear on public collaboration papers (`docs/SECURITY.md`).

5. **Set the topic.** `[topic] terms` are specific phrases that make a paper on-topic. Avoid a
   bare word like "quantum" there: it also matches "quantum dots". Put broad words in
   `broad_terms` instead; they mark papers "Maybe" for a person to decide.

6. **Check the profile.** This calls no API and prints exactly what the profile will do,
   including the arXiv search it builds:

   ```powershell
   pubmon --profile my-qic check-profile
   ```

   A typo or missing setting stops with a message naming the section and key. That is on
   purpose: a silently ignored setting could, for example, write into another QIC's history.

## 6. Run a real collection

On your own computer, with your key in `.env`:

```powershell
pubmon --profile my-qic run --backfill --no-master --xlsx    # first run: everything since start_date
pubmon --profile my-qic run --xlsx                           # later runs: recent changes
pubmon --profile my-qic status
```

Use `--master <path>` (or `PUBMON_MASTER` in `.env`) instead of `--no-master` to compare with
your existing master workbook; it is opened read-only. Outputs appear in the workspace's
`out/` folder. `master_<date>.xlsx` holds every paper; `candidates_<date>.xlsx` holds only new
or changed papers. The workbook's **Read me** sheet explains every column.

## 7. Run it on GitHub instead (optional)

GitHub Actions can run the collection in the cloud, so nothing needs installing:

1. In the repository on GitHub: **Settings → Secrets and variables → Actions → New repository
   secret**. Add `OPENALEX_API_KEY` and `PUBMON_EMAIL` (one secret each). Secrets are hidden,
   even from people who can see the code.
2. **Actions → Generate candidate Excel → Run workflow**. Type the profile name (for example
   `cleveland-clinic`) and click **Run workflow**.
3. When it finishes, open the run and download the artifact under **Artifacts**. Files are
   kept for 14 days.

The cloud run never sees your real master workbook, so it always uses `--no-master`.

## 8. Move the project to IBM's GitHub and share it

Do this once the project is in a good state. Check IBM's policy and your manager's guidance
first: `docs/SECURITY.md` explains why IBM-internal information must not be kept on a
personal GitHub account. The repository itself holds only public data, but the move keeps
the code under IBM's control.

1. **Get access.** Ask IT or your manager how your team gets repositories on IBM's GitHub,
   and which organization this should live in.
2. **Create an empty repository there.** Do not add a README or license on the creation
   page; the history comes from this copy.
3. **Push the full history from your computer:**

   ```powershell
   git remote add work <URL of the new repository>
   git push work --all
   git push work --tags
   ```

   `git remote` gives a repository a short name. `origin` stays your personal copy; `work`
   is the IBM copy. Later, make `work` the default with
   `git remote rename origin personal` and `git remote rename work origin`.
4. **Recreate the secrets** in the new repository (step 7.1). Secrets never copy over.
5. **Check that GitHub Actions runs there.** Company GitHub setups sometimes restrict
   Actions; if the workflow will not start, ask IT which runners are allowed.
6. **Share.** Add teammates under **Settings → Collaborators and teams**, and point them to
   this guide. Each person makes their own `.env` and their own OpenAlex key; keys are never
   shared.
7. **Update the links.** Replace `josephbns/paper-pull` in this guide and the README with the
   new location. Then decide whether to archive or make private the personal copy.

## If something goes wrong

| Message | Meaning and fix |
| --- | --- |
| `Choose a profile with --profile <name>` | No profile was named; add `--profile <name>` or `PUBMON_PROFILE` to `.env` |
| `Unknown key(s) [...] in [section]` | A setting name is misspelled; the message lists the allowed names |
| `Missing environment variables: OPENALEX_API_KEY` | `.env` is missing or not filled in (step 3) |
| `Profile 'x' not found` | The file `profiles/x.toml` does not exist; the message lists available profiles |
| A run ends with status `partial` | A source was down; nothing was deleted. Run again later |

More detail on each setting: [CUSTOMIZATION.md](CUSTOMIZATION.md). How the program decides
which papers to collect: [SPEC.md](SPEC.md).
