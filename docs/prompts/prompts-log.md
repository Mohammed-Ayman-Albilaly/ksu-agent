## Prompt 1

Initialize git here with default branch "main" and add remote "origin" = https://github.com/Mohammed-Ayman-Albilaly/ksu-agent.git.
Create docs/prompts/prompts-log.md and append this exact prompt to it under a heading "Prompt 1".
Do not commit. Show me git status and git remote -v.

## Prompt 2

Create .gitignore for Python and Node; also ignore .env, *.zip, data/raw/, data/private/.
Create README.md: title "KSU Agent", one paragraph: phase 1 is a cited RAG assistant for KSU CCIS undergraduates, built with DevAI Desktop.
Append this exact prompt to docs/prompts/prompts-log.md under "Prompt 2".
Do not commit. Show me both files.

## Prompt 3

Create docs/DECISIONS.md: record every decision in the attached Sprint 0 file (ID, date, decision, reason, alternatives, approved by, source section), plus these changes dated 2026-11-07, approved by team and supervisor:
D1: scope narrowed from all KSU majors to CCIS undergraduates (time; sources must be verifiable). D2: REF-01 replaced by the current undergraduate regulation with executive rules, version 2, on dar.ksu.edu.sa (the 1436H copy is outdated). D3: repo is public. D4: DevAI Desktop builds the code; VS Code only for reading and review.
Use only the file and this message; if a field is unknown write "not stated", never guess. Append this prompt to docs/prompts/prompts-log.md under "Prompt 3".
Do not commit. Show me the file.

## Prompt 4

i need you to create a python script inside /backend that download regulation from: https://dar.ksu.edu.sa/sites/dar.ksu.edu.sa/files/users/user980/excutive_regulations_2.pdf
and save it in `data/row` which is ignored by git and record with it the following: URL, the download date and file's hash.
have the script read the URL from a sources list in a file not hard-coded

## Prompt 5

Create backend/scripts/parse_source.py: for a source id in backend/config/sources.toml, read its PDF from data/raw, extract text page by page with pypdf (install it, add backend/requirements.txt), apply Unicode NFKC and remove tatweel (U+0640), then write data/processed/<id>.txt with "[[page N]]" markers and <id>.meta.json (source id, sha256 from the lock file, page count, char count). Add data/processed/ to .gitignore.
Take all paths from the existing config and lock files; no hard-coded source id, URL or filename. Add pytest tests for the cleaning function in backend/tests/ (tatweel removed, NFKC applied, page order kept).
Run `python backend/scripts/parse_source.py --source-id ref-01` and report the page count, the size of both output files, and the first 15 lines of the .txt.
Save this prompt in "docs/prompts/prompts-log.md" under the next "Prompt N" heading. Do not commit and do not open a PR.

## Prompt 6

Replace pypdf with PyMuPDF in backend/scripts/parse_source.py: open the PDF with `import pymupdf` (not `fitz`) and read each page with `page.get_text()`, keep NFKC + tatweel removal and the same data/processed outputs and meta.json. Swap the dependency in backend/requirements.txt and delete all pypdf code.
Add a pytest case asserting the cleaned text contains no Arabic presentation forms (U+FE70–U+FEFF) and no U+0640, and that "[[page N]]" markers stay in page order.
Re-run `python backend/scripts/parse_source.py --source-id ref-01` and report the page count plus the counts of "المعدل التراكمي", "الإنذار", "حرمان", "2,75", "علوم الحاسب" in data/processed/ref-01.txt.
Save this prompt in "docs/prompts/prompts-log.md" under the next "Prompt N" heading. Do not commit and do not open a PR.

## Prompt 7

Run `python -m pytest backend/tests -q`; if any test fails, stop and report the failures without committing.
If all pass, commit everything on the current branch feat/parse-regulation with message "feat: parse and clean source PDFs into data/processed" and push with `git push -u origin feat/parse-regulation`.
Open a pull request into main titled "feat: parse and clean source PDFs into data/processed"; body: what changed, and the verified numbers (63 pages; counts 15, 3, 3, 3, 2) plus that data/processed is git-ignored.
Save this prompt in "docs/prompts/prompts-log.md" under the next "Prompt N" heading. Do not merge the pull request.
