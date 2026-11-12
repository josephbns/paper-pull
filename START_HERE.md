# START HERE — pubmon build pack

This folder is everything Codex needs to build V1 of the publication monitor: the research,
the specification, the work plan, the prompts, config templates and synthetic test data. It
contains **no internal data**, so it is safe to give to Codex.

## What's in the pack

| File | What it is | Who reads it |
| --- | --- | --- |
| `START_HERE.md` | This page | You |
| `CODEX_PROMPT.md` | Six prompts, one per Codex session | You paste them |
| `AGENTS.md` | Standing rules Codex reads automatically | Codex |
| `docs/SPEC.md` | What to build — the source of truth | Codex, you |
| `docs/WORK_PLAN.md` | Milestones, V1–V4 roadmap, gates, risks, where to run it | You, Codex |
| `docs/RESEARCH.md` | Why: libraries, data sources, findings, sources | You |
| `docs/MASTER_COLUMNS.md` | The master's 36 columns and what the code may touch | Codex |
| `docs/SECURITY.md` | What data may go where | You, Codex |
| `config/*.example.*`, `config/arxiv_query.txt` | Settings templates and your existing arXiv feed query | Codex, you |
| `tests/fixtures/` | Synthetic master workbook and public preprint ↔ journal pairs | Codex |
| `pyproject.toml`, `.gitignore`, `.env.example` | Project setup | Codex |

## If Codex already read the plan PDF

This pack supersedes section H of the plan doc. Put these files at the **root** of the repository
Codex works in, then tell Codex: "AGENTS.md and docs/SPEC.md replace section H of the PDF;
follow them." The spec adds the one-row-per-paper output, the verified institution IDs, the
review lane and the work-type rules.

## This week: no GitHub

**Codex cloud can't run yet.** Cloud tasks check out a GitHub repository, so they need this
folder to be on GitHub first. Two options until then:

1. **Codex on your machine (recommended this week).** Unzip the folder, open it with the Codex
   CLI, IDE extension or desktop app, and paste the Session 1 prompt from `CODEX_PROMPT.md`.
   Use an IBM machine only if Codex is approved for IBM work; the pack itself holds only public
   and synthetic material.
2. **Wait for GitHub** and start in the cloud then.

## Later: moving to GitHub and Codex cloud

The folder is already a git repository with one commit.

```bash
git remote add origin <your-repo-url>
git push -u origin main
```

Then in Codex cloud: create an environment for the repo, set the setup script to
`pip install -e ".[dev]"`, leave agent internet **off** (all tests are offline), and paste the
next session's prompt. Before relying on IBM's GitHub, check that Codex cloud can connect to
it (see the open question in `docs/RESEARCH.md`).

## Your checklist

- [ ] Read `docs/WORK_PLAN.md` "V1 build milestones" (2 minutes).
- [ ] Look over `config/arxiv_query.txt` and `config/watchlist.example.csv`. They contain the
      researcher names from your existing arXiv feed. Remove any you don't want in a repo.
- [ ] Run Session 1. After each session: read the summary, run `pytest -q`, skim the code, then
      paste the next prompt.
- [ ] After Session 6, on an IBM machine with internet: follow "After milestone 6" in
      `docs/WORK_PLAN.md` (OpenAlex key, institution IDs, backfill, back-test).

## Never put these in this folder

The real master workbook or any copy of it, candidate files from real runs, review decisions,
SOW or counting information, API keys. `.gitignore` blocks the usual paths, but check
`git status` before every commit.
