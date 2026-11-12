# pubmon

A publication monitor for the IBM–Cleveland Clinic collaboration, under development.
Final exports will have **one row per paper**, combining preprint and journal identifiers.

Milestones 1–2 provide settings, source-record models, normalization, and SQLite history.
Fetching, matching and exports are not implemented yet; `pubmon run` is not available.

## Development quick start (Python 3.11+)

```bash
cd /workspace/paper-pull
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest -q
ruff check .
ruff format --check .
pubmon --help
```

On Windows PowerShell activate with `.venv\Scripts\Activate.ps1` instead.
Tests use synthetic inputs and make no network calls. Package installation needs Internet.
No API credentials are needed for this milestone.

Settings load from `config/settings.toml`, falling back to `config/settings.example.toml`.
Paths inside TOML are relative to the project directory supplied to `load_config()`.
Credentials come from process variables, then a git-ignored `.env`; network commands will
validate them when implemented. Never commit keys, contact emails, real workbooks or outputs.

The build pack's statements that GitHub is unavailable are superseded by the owner's
instruction to use `josephbns/paper-pull`. Its bundled Git history was not imported.
See `docs/SPEC.md`, `docs/WORK_PLAN.md` and `CODEX_PROMPT.md` for the remaining milestones.
A complete beginner guide arrives in Milestone 6.

## History database (Milestone 2)

`Store` in `src/pubmon/store.py` opens `data/pubmon.db` by default. This local state remains
ignored by Git. Every write must run inside `with store.transaction():`; a failure rolls
back the entire block. Nested transactions are rejected so a helper cannot commit part of
a larger operation by accident.

The store retains paper summaries, identifiers, latest source records, audit events, runs,
and decision history. Identifier or source-identity conflicts raise `IdentifierConflict`;
the caller must send them for review rather than silently reassigning a paper's identity.
Merge decisions are recorded here; applying them arrives with decision import in Milestone 5.

Run the history tests without API access:

```bash
pytest -o addopts='' -q --disable-recording --block-network tests/test_store.py
```

Two engineering concepts to look for:

- **Atomicity:** `Store.transaction()` makes a batch of writes succeed or fail together.
  `test_interrupted_run_safe` verifies the database file is byte-identical after failure.
- **Idempotency:** `Store.upsert_identifier()` keeps one identifier row when called repeatedly.
  `Store.store_decision()` similarly avoids duplicating an unchanged review decision.
