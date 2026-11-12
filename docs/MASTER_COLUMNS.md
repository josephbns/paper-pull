# Master workbook columns

The master is one sheet with one header row and these 36 columns, in this order. Base columns
come from the Publications-ALL tracker; the next 18 come from the Cleveland Clinic quantum
papers list; the last 5 are new. `tests/fixtures/synthetic_master.xlsx` uses exactly these
headers with fake rows.

**Access** says what `pubmon` may do:

- **Read** — read for matching and display. Never written.
- **Never read** — manual decisions. The code must not open, copy or output these values.
- **Not used in V1** — ignored for now; a later version may propose values.

| # | Column | Group | Access | Notes |
| --- | --- | --- | --- | --- |
| 1 | Name | Base | Read (display only) | Composed label "Venue: nickname, date". **Never used for matching.** |
| 2 | Include in official count? | Base | Never read | Manual counting decision |
| 3 | Type of Paper | Base | Read | Seen: Peer Reviewed Journal, Open Publication, Review Paper, Conference Paper, Conference Short Paper, Conference Presentation, Conference Poster, Conference Workshop Paper, blank |
| 4 | Publication or Conference (short name) | Base | Read | Free text venue |
| 5 | Pub Status | Base | Read | Seen: Published, Accepted, Submitted, Under Review, Drafting, Withdrawn, blank |
| 6 | Date of Publication | Base | Read | Excel date; blank when unknown |
| 7 | IBM Authors | Base | Read | Comma-separated full names; some include a native-script name in parentheses |
| 8 | CC and other Authors | Base | Read | Comma-separated full names; spacing after commas is inconsistent |
| 9 | Official # (from SOW Tracking) | Base | Never read | Manual |
| 10 | SOW Tracking | Base | Never read | Manual |
| 11 | Impact Factor or Journal | Base | Never read | Manual (numbers) |
| 12 | Theme (manual) | Base | Never read | Manual |
| 13 | # qubits HW | Base | Never read | Manual |
| 14 | Most Recent Publication date | CC list | Not used in V1 | Date; sometimes the arXiv date |
| 15 | Title | CC list | Read | Real paper title; may carry a hyperlink |
| 16 | Authors | CC list | Not used in V1 | First author + count only ("X et al. (+5)") |
| 17 | Involvement | CC list | Never read | Manual label |
| 18 | CCF Authors | CC list | Never read | Manual |
| 19 | Hub Members | CC list | Never read | Manual |
| 20 | Other Institutions | CC list | Never read | Manual; mixes partners, "No IBM" and funding vehicles |
| 21 | Engine | CC list | Never read | Manual |
| 22 | Algorithm | CC list | Never read | Manual |
| 23 | Circuit | CC list | Never read | Manual |
| 24 | Status | CC list | Read | Preprint / Published |
| 25 | Journal | CC list | Not used in V1 | Some values truncated |
| 26 | A&A Involvement? | CC list | Never read | Manual |
| 27 | R2U Involvement | CC list | Never read | Manual |
| 28 | Date for arXiv | CC list | Not used in V1 | Date |
| 29 | arXiv | CC list | Read | arXiv ID as text, no version suffix. Older files may hold only the word "arXiv" with the ID in the hyperlink — read the hyperlink then |
| 30 | PubMed | CC list | Read | PMID as text; same hyperlink caveat |
| 31 | DOI | CC list | Read | DOI as text, lowercase; same hyperlink caveat |
| 32 | Pub ID | New | Read | Stable key `PUB-0001`…; assigned once, never reused |
| 33 | OpenAlex ID | New | Read | `W…` id; blank until proposed |
| 34 | Same work as | New | Read | Pub ID of the other version (preprint ↔ journal) of the same work |
| 35 | Merge source | New | Not used in V1 | Which tracker the row came from |
| 36 | Review flag | New | Not used in V1 | Short note for reviewers |

The header row as one line (copy-paste safe):

```
Name|Include in official count?|Type of Paper|Publication or Conference (short name)|Pub Status|Date of Publication|IBM Authors|CC and other Authors|Official # (from SOW Tracking)|SOW Tracking|Impact Factor or Journal|Theme (manual)|# qubits HW|Most Recent Publication date|Title|Authors|Involvement|CCF Authors|Hub Members|Other Institutions|Engine|Algorithm|Circuit|Status|Journal|A&A Involvement?|R2U Involvement|Date for arXiv|arXiv|PubMed|DOI|Pub ID|OpenAlex ID|Same work as|Merge source|Review flag
```
