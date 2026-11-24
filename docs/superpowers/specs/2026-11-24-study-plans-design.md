# Design — Study plans and the academic calendar as structured sources

Date: 2026-11-24
Status: proposed

## 1. Goal

Answer two classes of question the regulation corpus cannot: "what courses are in level 5
of the Software Engineering plan" and "when does the final exam period start this term".

Both are **structured data**, so neither is ingested as RAG chunks. SD-19 says dates and
prerequisites are served from tables, not from similarity search, and this design follows it.

## 2. What the sources actually are

Researched on 2026-11-24 against `ccis.ksu.edu.sa` and `dar.ksu.edu.sa`.

| Program | Page | Form | Verdict |
| :--- | :--- | :--- | :--- |
| All bachelor programs | `/ar/bsc` | HTML index | the entry point: names every program |
| CE — هندسة الحاسب | `/ar/ce/new-bsc-program` | **HTML table**, 10 levels | parse directly |
| IS — نظم المعلومات | `/ar/node/1202` | **HTML table**, 8 levels | parse, but see §6 |
| CS — علوم الحاسب | `cs.ksu.edu.sa/ar/cs/bsc-program` | PDF (student handbook) | parse the PDF |
| SWE — هندسة البرمجيات | `/ar/se/se-bsc-program` | PDF, 2023 | parse the PDF |
| IT — تقنية المعلومات | `/ar/it/bsc-program` | PDF, 2024 and 2026 | parse the PDF |
| AI | minor only | **PNG image** | out of scope |
| Course catalogue | `/en/cs/cs-prog-guides` | HTML per course | prerequisites across courses |

**Verified, not assumed:** the SWE 2023 PDF was downloaded and read with `pymupdf`. It is
9 pages of real text, not a scan, and page 4 carries the table with the columns
`Course Code | Course Title | Credit Hours | Pre-requisites | Co-Requisites`, under
`YEAR 1 / LEVEL (SEMESTER) 1`, with a `Total 16 CH` per level. The extraction path works.

**The machine-readable route:** the CCIS Drupal site exposes an open JSON:API at
`https://ccis.ksu.edu.sa/ar/jsonapi` (200, `application/vnd.api+json`). Two endpoints matter:
`file/document?filter[filename][value]=plan` returns every plan file with its URL, MIME type,
byte size and upload date (37 hits), and `node/page/<uuid>?fields[node--page]=body` returns the
CE and IS tables as HTML inside a JSON string. `path_alias` is 403, so pages are enumerated by
title or by file, never by alias.

## 3. Design

A new module `backend/scripts/plans.py`, and a new ingestion step that writes one JSON table
per program:

```
data/processed/plans/<program>.json
{ "program": "swe", "source_url": "...", "language": "en", "retrieved_at": "...",
  "levels": [ { "level": 1, "courses": [ { "code": "MATH 101", "title": "...",
  "credits": 3, "prerequisites": [] } ] } ] }
```

Four steps, each independently testable:

1. **Fetch** — `fetch_plans.py` reads `backend/config/plans.toml`, which names each program,
   its source URL, its form (`html_table` or `pdf`) and the page it was published on. The URL lives
   in config, never in a script, the way `sources.toml` already works.
2. **Parse** — `parse_plan.py` turns one source into the JSON above. Two parsers: an HTML table
   parser that reads `body.value` from JSON:API for CE and IS, and a PDF parser using the existing
   `pymupdf` for CS, SWE and IT. A course row with no code or no credits is an error that names
   the level, never a silently dropped row.
3. **Load** — `plans.load(program)` returns the table, and refuses a table whose `source_url`
   is absent or whose levels are empty.
4. **Answer** — `plans_answer.py` answers a plan question from the table, with no model call for a
   listing ("what is in level 5") and one model call only to phrase a comparison. Every course row
   cited names its `source_url`.

The reasoning side reuses `app/facts.py`'s shape: the numbers come from the table, the model only
explains them, and no number is ever computed by the model.

## 4. The calendar

`https://dar.ksu.edu.sa/ar/current` is the same shape of problem: a table of dated rows. It is
`html_table`, stored as `data/processed/calendar.json` with `{ "label": "...", "start": "...",
"end": "..." }` per row, and a date question is answered from it. A question that asks for a date
the table does not carry returns the fallback, never a guess.

## 5. What this deliberately does not do

- The AI minor: its structure is published only as a PNG screenshot, so its course list is not
  extractable. It is out of scope until a text source exists.
- Level-by-level study plans are not embedded: a student asking "what is in level 5" gets the table's
  rows, not a similarity search over prose.
- No reranker, no pgvector. 75 chunks of regulation plus a few hundred plan rows do not need either.

## 6. The one thing to verify before ingesting

The IS Arabic plan at `/ar/node/1202` looks **older** than the 2024-2026 PDFs other departments
publish: its course codes are in Arabic-Indic digits (`١١١عال`, `١٤٠تقن`) and it lists 8 levels plus
summer training, while IT publishes a 2026 PDF. It sits on the same site as newer files, so the two may
disagree. It must be checked against the current plan before it becomes a source, and the check recorded in
the table's metadata rather than assumed.

## 7. Risks

| Risk | Handling |
| :--- | :--- |
| A plan is revised and the JSON is stale | `retrieved_at` in every table, and a fetch that records the file's upload date |
| The PDF is a scan, not text | `parse_plan.py` fails on an empty page and names it, rather than writing an empty level |
| The IS plan is the older edition | checked in §6 before ingestion, not after |
| A course code appears in two plans with different credits | the table is per program, so no cross-program sum is ever taken |
