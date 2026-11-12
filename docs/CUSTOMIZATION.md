# Customize CCF or another QIC

Use **one collaboration profile**, `config/settings.toml`, for partner-specific behavior.
Keep private credentials/contact details in `.env`, outside the shareable profile. Both local
files are ignored by Git; their blank/public templates are committed for new users.

| File | What belongs here |
| --- | --- |
| `config/settings.toml` | Collaboration names, institution IDs, dates, keywords, arXiv query, watchlist, matching thresholds, workspace and master path |
| `.env` | `OPENALEX_API_KEY` and `PUBMON_EMAIL` |

This is one place for collaboration customization plus one private credentials file. The
application never saves keys or actual contact email addresses into the shareable template.
Environment variables override `.env`; cloud secret/runtime settings can supply the same names.
The API domains belong in the cloud network allowlist, not in either credential field.

## First setup

On a new local checkout, create the files without replacing any existing settings:

```powershell
if (!(Test-Path config/settings.toml)) { Copy-Item config/settings.example.toml config/settings.toml }
if (!(Test-Path .env)) { Copy-Item .env.example .env }
notepad config/settings.toml
notepad .env
```

In the private `.env`, fill the key and your own API contact email:

```dotenv
OPENALEX_API_KEY=your_openalex_key_here
PUBMON_EMAIL=your_contact_email_here
```

Do not commit that file or paste the key into chat. For the current owner's cloud checkout,
the supplied contact email has been filled privately; it is absent from GitHub. New local
clones do not receive ignored private files, so set the email/key on each machine or use
secure environment settings. Only OpenAlex needs a key for these public API requests.

## The current CCF profile

`config/settings.example.toml` is a complete public CCF starting profile. It includes the
existing arXiv query verbatim and the original public Clinic author names. No CSV or separate
query-file edit is needed for the new profile. Add confirmed public IBM authors and review
common-name ambiguity; their names are not guessed automatically.

| Section | Customize |
| --- | --- |
| Top-level dates | `start_date`, `arxiv_window_days` |
| `[collaboration]` | `name`, `partner_name`, `partner_label`, `ibm_name` |
| `[storage]` | `workspace`: history, backups, logs, raw responses, outputs and demo history root |
| `[openalex]` | IBM and `partner_institution_ids`, `quantum_terms`, `skip_types` |
| `[arxiv]` | Inline multiline `query`, inline `watchlist`, `common_names` |
| `[matching]` | `auto_link`, `review`, `year_window` |
| `[master]` | Local `path`, or override with `--master` |

Institution lookup can use the names already in your profile:

```powershell
pubmon resolve-institutions
```

This only lists candidates. Confirm the institution IDs/scope and edit the profile yourself.
The watchlist uses `side = "IBM"` or `side = "PARTNER"`; `arxiv_name` is the exact public name
used for arXiv matching, and optional `orcid` is a string. The entire query is explicit and is
never regenerated from labels, preventing silent changes to a proven search.

## Reuse for another QIC

Copy the complete template into that QIC's local `config/settings.toml`, then change its
collaboration names/label, verified partner institution IDs, dates, complete query and public
author list. Use a **separate workspace** before collecting that QIC's records:

```toml
[storage]
workspace = "workspaces/my-qic"
```

Paths for configuration files and the master remain relative to the project directory;
`storage.workspace` controls runtime history/output location only. With the example above,
live history is `workspaces/my-qic/data/pubmon.db`, live outputs are under
`workspaces/my-qic/out/`, and synthetic replay is under `workspaces/my-qic/demo/`.
`status`, decision import and back-testing use the same workspace automatically.

Changing a partner does not erase or filter previous history. Use a fresh workspace for each
QIC, or a separate project checkout; do not reuse CCF's database for another partner.
Private environment credentials are project/process-specific; use separate private `.env`
files or environment bindings if different deployments need different contacts or keys.

## Compatibility and remaining limits

Existing profiles using `openalex.cc_institution_ids`, `arxiv.query_file`, or
`arxiv.watchlist_file` still load. Legacy watchlist side `CC` is accepted as `PARTNER`.
Specify either inline query/watchlist or its legacy file reference, not both; ambiguous
settings fail explicitly. Existing CCF storage defaults to the checkout root, preserving its
current database/output paths.

The persisted lane key `clinic_quantum` and internal compatibility field `cc_institution_ids`
remain for old history/tests, but discovery uses the configured partner's institution IDs.
They do not restrict collection to Cleveland Clinic.

Workbook reconciliation still requires the current approved 36-column template and its
manual-field protections. Supporting a QIC's different workbook layout requires a reviewed
mapping change; changing the partner profile alone does not add arbitrary column layouts.
One-row-per-paper output and protected-field rules apply to every profile.

Live API validation and real-world recall remain pending; passing a synthetic profile test
is not validation of another QIC's institution scope, authors or query.
