# AGENTS.md — instructions for coding agents (Codex)

## What this project is

`pubmon` finds scientific publications from the IBM Quantum – Cleveland Clinic Discovery
Accelerator collaboration in public databases (OpenAlex, arXiv, Crossref), remembers what it
has already seen, and writes a weekly review file containing only new, changed or uncertain
records. A person reviews that file and updates the master Excel tracker by hand.

Read these before writing code, in this order:

1. `docs/SPEC.md` — the V1 specification. **It is the source of truth.**
2. `docs/WORK_PLAN.md` — milestones and acceptance gates.
3. `docs/SECURITY.md` — what data may and may not enter this repository.
4. `docs/MASTER_COLUMNS.md` — the master workbook's exact header row.

`docs/RESEARCH.md` explains why the design looks the way it does. Read it when a choice in
the spec seems odd.

## Hard rules (never break these)

1. **Never write to, move, rename or re-save the master Excel workbook.** Open it with
   `openpyxl.load_workbook(path, read_only=True, data_only=True)`. No code path may save it.
2. **Never read or output the manual columns** listed in `docs/MASTER_COLUMNS.md` (count,
   SOW, theme, qubits, involvement labels). Skip them when reading the master.
3. **No secrets in files.** API keys and contact emails come from environment variables
   (`OPENALEX_API_KEY`, `PUBMON_EMAIL`, later `NCBI_API_KEY`), optionally loaded from a
   git-ignored `.env`.
4. **Tests run fully offline.** Use recorded responses (pytest-recording / VCR cassettes) or
   small hand-written JSON fixtures. Strip `api_key` query parameters and `Authorization`
   headers from every recording.
5. **No real internal data in this repo.** Only public metadata and the synthetic fixtures
   in `tests/fixtures/`. If you need an example master, use `tests/fixtures/synthetic_master.xlsx`.
6. **Dependencies are fixed** (see `pyproject.toml`). Do not add LLMs, vector databases, web
   frameworks, pandas, ORMs or extra services. Ask before adding anything.
7. **Do not invent** institution IDs, author names, column names or thresholds. Leave a
   clearly marked `TODO(owner):` and list it in your summary.
8. **One milestone per session.** Stop when the milestone's acceptance checks pass, and
   summarize (see "Finishing a milestone").

## Commands

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest -q                                              # all tests, offline
ruff check . && ruff format --check .                  # lint + format check
pubmon run --dry-run --master tests/fixtures/synthetic_master.xlsx
```

## Code style

The owner is learning to code and will read every line.

- Plain, explicit code over clever code. Functions under ~40 lines.
- Type hints everywhere; a one-line docstring on every public function.
- Comments explain *why*, not *what*.
- `src/` layout, package `pubmon`. One module per responsibility (see `docs/SPEC.md` §11).
- Use `logging`, never `print`, except for the CLI's final summary. Put the `run_id` on every
  log line.
- All database writes go through `store.py`. All network calls go through `sources/*`.
- Dates are ISO strings (`YYYY-MM-DD`) inside the program; convert only at the edges.
- IDs are always strings. arXiv IDs never carry a version suffix (`2401.12340`, not `2401.12340v2`).

## Testing conventions

- Tests live in `tests/`, one file per module (`test_match.py`, …).
- Cassettes live in `tests/cassettes/`. Record with `pytest --record-mode=once` only when
  internet is available; until then, use hand-written JSON in `tests/fixtures/api/`.
- The acceptance tests named in `docs/SPEC.md` §14 must exist with exactly those names.

## Finishing a milestone

End every session with a short summary containing:

1. What you built (files and one line each).
2. How the owner runs and checks it (exact commands).
3. Test results (`pytest -q` output tail) and lint status.
4. Open `TODO(owner):` items and any spec ambiguity you hit.
5. **What to learn from this milestone:** two or three engineering concepts the code
   demonstrates (for example idempotency, transactions, adapters), each in two plain sentences,
   pointing at the file and function where it happens.

Also append a dated entry to `docs/CHANGELOG.md`.
