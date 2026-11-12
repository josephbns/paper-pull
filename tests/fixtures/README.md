# Test fixtures

Everything here is either synthetic or public. No internal tracker data.

## `synthetic_master.xlsx`

A fake master workbook with the exact 36-column header from `docs/MASTER_COLUMNS.md` and 11
rows. Every manual column holds the value `POISON-DO-NOT-READ`; if that string ever shows up in
program output or the database, a hard rule was broken (`test_manual_columns_never_read`).

All DOIs use the `10.5555` prefix, which Crossref uses for examples, and all arXiv IDs use
`99xxx` serial numbers that don't exist on arXiv, so nothing here can collide with a real paper.

`synthetic_master_rows.csv` says what each row is for:

| Pub ID | Case |
| --- | --- |
| SYN-0001 / SYN-0002 | A journal row and its preprint row (`Same work as` links them; titles differ by spelling) |
| SYN-0003 | arXiv-only row; a later fixture run gives it a journal DOI (`test_publication_triggers_update`) |
| SYN-0004 | No IDs, no title: matchable only by ≥ 2 shared author surnames + date within 30 days |
| SYN-0005 | arXiv cell shows only the word "arXiv"; the ID is in the hyperlink (`test_hyperlink_id_fallback`) |
| SYN-0006 | A conference talk: never in any database, must stay unmatched |
| SYN-0007 | A drafting row with no date |
| SYN-0008 | `Name` looks like a real title; a candidate with that title by other authors must **not** match (`test_master_matching_uses_ids_not_name`) |
| SYN-0009 / SYN-0010 | "Part I" / "Part II": must never merge (`test_similar_titles_not_merged`) |
| SYN-0011 | A Clinic-only paper (no IBM authors) that still belongs in the master |

Tests must never save this file. `test_master_untouched` checks its SHA-256 before and after a run.

## `golden_pairs.csv`

Eleven real, public preprint ↔ journal pairs (arXiv ID and journal DOI) from quantum-chemistry
and quantum-biomedicine papers. Use them to build realistic arXiv and journal records for the
matching tests, and later (with internet) as an integration check that OpenAlex and Crossref
link each pair. The titles are the published titles; some preprints were titled differently.

## `api/` (Milestone 3)

Hand-written synthetic OpenAlex pages, arXiv Result-shaped JSON and Atom XML, and Crossref
publication/notice responses. They exercise the installed libraries with mocked transports;
none were downloaded from a live API. Real cassettes can later be recorded into
`tests/cassettes/` using the README command. The default test run blocks network access.

## Generating a new synthetic workbook

```bash
python tests/fixtures/generate_master.py /tmp/new_synthetic_master.xlsx
```

The generator refuses existing output paths. Its 11 rows cover the same kinds of cases as
our bundled fixture; it intentionally does not reproduce the bundled workbook byte for byte.
The application never writes either workbook.

`api/crossref_updates.json` supplies synthetic correction/retraction targets for end-to-end
notice tests. Distinct synthetic OpenAlex papers have distinct IDs; only the deliberate
preprint/journal pair shares identity clues.
