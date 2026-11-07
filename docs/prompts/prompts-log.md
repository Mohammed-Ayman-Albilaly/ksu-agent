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
