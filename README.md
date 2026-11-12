# pubmon

A publication monitor for the IBM–Cleveland Clinic collaboration, under development.
Final exports will have **one row per paper**, combining preprint and journal identifiers.

Milestone 1 provides settings, source-record models, and normalization. Fetching, matching,
history and exports are not implemented yet; `pubmon run` is not available.

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
