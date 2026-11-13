# Customize a QIC profile

Each QIC is described by one **profile**: `profiles/<name>.toml`. Profiles hold only public
criteria and are committed to Git, so every change to what the tool searches for has a
history. Private values live in a git-ignored `.env`. New users: follow
[SETUP.md](SETUP.md) first; this page is the reference for every setting.

| File | What belongs here | Shared on GitHub? |
| --- | --- | --- |
| `profiles/<name>.toml` | Partner name, OpenAlex institution IDs, dates, topic terms, people, matching thresholds, workspace | Yes (public information only) |
| `.env` | `OPENALEX_API_KEY`, `PUBMON_EMAIL`, optional `PUBMON_PROFILE`, optional `PUBMON_MASTER` | Never |

Choose the profile with `--profile <name>` (before or after the command), the
`PUBMON_PROFILE` environment variable, or `PUBMON_PROFILE` in `.env`, in that order of
priority. There is deliberately no default: running the wrong QIC's criteria would produce
plausible-looking but wrong results. `pubmon --profile <name> check-profile` validates a
profile and prints what it will do without calling any API.

Profiles are checked strictly. An unknown or misspelled key, a missing required key, or a bad
value stops the command with a message naming the section and the allowed keys.

## Settings reference

| Section | Key | Meaning |
| --- | --- | --- |
| `[qic]` | `name`, `label` | Partner name (used in labels and institution lookup) and short label |
| | `collaboration`, `ibm_name` | Optional display names; default `IBM–<name>` and `IBM` |
| | `start_date` | Ignore papers published before this date (`YYYY-MM-DD`) |
| | `workspace` | Folder for this QIC's history and outputs; never shared between QICs |
| | `onsite_hardware` | Names of the IBM system at the partner (e.g. `ibm_cleveland`). Papers with no partner author that name it count, tied as "Used on-site IBM system" |
| `[institutions]` | `ibm`, `partner` | OpenAlex institution IDs; a parent ID covers its labs through lineage |
| `[topic]` | `terms` | Specific phrases that mark a paper on-topic. Used to search OpenAlex and arXiv, and to fill **Quantum?** = Yes |
| | `broad_terms` | Optional broad words that mark **Quantum?** = Maybe when no phrase matched. Never searched |
| | `arxiv_categories` | arXiv categories that count as on-topic (search and tag), e.g. `quant-ph` |
| | `hardware_terms` | Phrases suggesting IBM hardware use; fill **IBM hardware (suggested)** for papers with no IBM author |
| `[search]` | `arxiv_window_days` | How far back weekly runs look on arXiv (default 90) |
| | `arxiv_phrases` | Extra arXiv phrases (any field) that find partner papers besides people |
| | `common_names` | Names shared by many researchers; a paper matched only by these is marked uncertain |
| | `skip_types` | OpenAlex work types to ignore (default: datasets, software, editorials and similar) |
| | `arxiv_query_override` | Expert use: a complete hand-written arXiv query replacing the generated one |
| `[matching]` | `auto_link`, `review` | Title similarity (0–100) to merge versions automatically / ask a person |
| | `year_window` | Years a journal version may differ from its preprint |
| `[[people]]` | `name`, `side` | One entry per person. `side = "partner"` finds papers; `side = "ibm"` only confirms them |
| | `aliases` | Other spellings seen on papers |
| | `orcid` | Optional ORCID ID |
| | `tab` | `"backup"` sends papers found only through this person to the Backup sheet |

Every paper gets a **Partner tie**; only these three ties reach the Publications sheet:

| Partner tie | Meaning | Sheet |
| --- | --- | --- |
| Author affiliation | A source (OpenAlex) reports a partner-affiliated author | Publications |
| Named researcher | A `partner` person from the profile is an author; no affiliation reported | Publications |
| Used on-site IBM system | No partner author, but the paper names an `onsite_hardware` system | Publications |
| Mention only / None found | The partner is only mentioned, or no link was found | Check tie |
| (backup person only) | Found only through `tab = "backup"` people | Backup |

The private master workbook path is never part of a profile. Set `PUBMON_MASTER` in `.env`
or pass `--master <path>`.

## How the arXiv search is built

The tool builds the arXiv query from the profile, so each name is written once:

```text
( au:"<each partner spelling>" OR all:"<each arxiv phrase>" )
AND ( cat:<each arxiv category> OR all:"<each topic term>" )
```

`check-profile` prints the exact query. A test pins the Cleveland Clinic query: it must keep
every clause of the original hand-written feed, and any addition must be deliberate. Use
`arxiv_query_override` only when the generated form cannot express what you need.

## How OpenAlex is searched

- **Pair search:** papers with at least one IBM-affiliated and one partner-affiliated author.
  This finds collaborations on any topic.
- **Partner + topic search:** partner papers whose title or abstract contains a topic term.
  Terms are sent in groups of five, because OpenAlex throttles searches with more operators;
  multi-word terms are quoted as exact phrases.

## Finding institution IDs

```powershell
pubmon --profile <name> resolve-institutions "Partner Name" "IBM"
```

This lists candidates and never edits files. Confirm each ID and its lineage on
[openalex.org](https://openalex.org/) before adding it.

## Older `config/settings.toml` format

Existing installs with a local `config/settings.toml` keep working when no profile is named;
the command logs a reminder to switch. Its legacy forms (`cc_institution_ids`, `query_file`,
`watchlist_file`, side `CC`) also still load. `config/settings.example.toml`,
`config/arxiv_query.txt` and `config/watchlist.example.csv` remain for those installs and the
automated tests. New setups should use profiles.

## Remaining limits

- Workbook reconciliation requires the approved 36-column master template
  (`docs/MASTER_COLUMNS.md`). A QIC with a different layout needs a reviewed column mapping.
- The lane key `clinic_quantum` keeps its historical name in stored history; it searches the
  profile's partner institutions, whatever the QIC.
- Live API validation and real-world recall checks are still pending.
