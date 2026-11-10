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

## Prompt 8

Create backend/scripts/chunk_source.py: read data/processed/<id>.txt, drop every line containing ".....", and split on heading lines that are exactly "المادة <ordinal>" with at most 4 tokens; parse the Arabic ordinal to an int and attach any following "القاعدة التنفيذية للمادة X" block to that article's chunk. Text after article 73 becomes one chunk with kind "annex".
Write one JSON object per line to data/processed/chunks/<id>.jsonl: source_id, title, url, sha256 (from sources.toml and sources.lock.json, never hard-coded), kind ("article"/"annex"), article_number, heading, text, char_count.
Add pytest tests for the ordinal parser (الأولى=1, الحادية عشرة=11, العشرون=20, الثالثة والعشرون=23, الثالثة والسبعون=73) and for TOC lines being dropped. Run it on ref-01 and report chunk count, how many distinct article_number values, min and max char_count, and the char_count of chunk 62.
Save this prompt in "docs/prompts/prompts-log.md" under the next "Prompt N" heading. Do not commit and do not open a PR.

## Prompt 9

Run `python -m pytest backend/tests -q`; if anything fails, stop and report without committing.
If it passes, commit on feat/chunk-regulation with message "feat: chunk parsed sources into per-article JSONL" and push with `git push -u origin feat/chunk-regulation`.
Open a pull request into main with that title; body: what changed, and the verified numbers (74 chunks, articles 1-73, min/max char_count 65/13546, 52 tests pass), and that data/processed/chunks/ is git-ignored.
Save this prompt in "docs/prompts/prompts-log.md" under the next "Prompt N" heading. Do not merge the pull request.

## Prompt 10

Create backend/config/embeddings.toml (provider, model "text-embedding-3-small", dimensions 1536, price per 1M tokens) and backend/scripts/embed_chunks.py: read data/processed/chunks/<id>.jsonl, count tokens per chunk with tiktoken, and abort listing the article numbers if any chunk exceeds the model's 8191-token limit instead of truncating. Add openai and tiktoken to backend/requirements.txt; the key comes only from OPENAI_API_KEY in .env (git-ignored), never printed or committed, and add .env.example with the variable name.
Embed in batches and write data/processed/index/<id>.npz (float32 vectors) plus <id>.index.json with model, dimensions, vector count, chunk-file sha256, total tokens and estimated cost from the configured price.
Add pytest tests with a fake client (no network): vector count equals chunk count, dimensions match config, a re-run gives identical vectors. Run it on ref-01 and report vector count, dimensions, total tokens, estimated cost, and the token count of the largest chunk.
Save this prompt in "docs/prompts/prompts-log.md" under the next "Prompt N" heading. Do not commit and do not open a PR.

## Prompt 11

Option 1, with two changes: split only the chunks that exceed the model limit, and repeat the article heading at the start of every part so each part stands alone. Add "part" and "parts" fields to the JSONL and keep the same article_number for all parts of an article; still abort if any part stays over 8,191 tokens.
Re-chunk ref-01, then re-run embed_chunks.py and report chunk count, vector count, dimensions, total tokens, estimated cost, and the largest chunk's token count.
Save this prompt in "docs/prompts/prompts-log.md" under the next "Prompt N" heading. Do not commit and do not open a PR.

## Prompt 12

Create backend/scripts/retrieve.py: read a source's .npz vectors and .jsonl chunks, embed a query using the same model/tokenizer from embeddings.toml, and return the top-k chunks sorted by cosine similarity. The query must be normalized using the same NFKC + tatweel removal as the parser. 
Add a CLI to run a single query and output: the top-k result's article_number, its score, and a snippet of its text.
Add pytest tests with a fake client: verify that a query exactly matching a chunk's text returns that chunk at position 0 with score 1.0.
Save this prompt in "docs/prompts/prompts-log.md" under the next "Prompt N" heading. Do not commit and do not open a PR.

## Prompt 13

The retrieval scores are far too low (0.56 for an exact match), which suggests the query is not being normalized. In backend/scripts/retrieve.py, import the clean_text function from backend.scripts.parse_source and apply it to the query string before embedding it. 
Verify the fix by running the "Perfect Match" test: the score for "الحد الأدنى للمعدل المطلوب للتخرج هو 2,75" must be > 0.90.
Save this prompt in "docs/prompts/prompts-log.md" under the next "Prompt N" heading. Do not commit and do not open a PR.

## Prompt 14

The retrieval scores are far too low (0.56 for an exact match), which suggests the query is not being normalized. In backend/scripts/retrieve.py, import the clean_text function from backend.scripts.parse_source and apply it to the query string before embedding it. 
Verify the fix by running the "Perfect Match" test: the score for "الحد الأدنى للمعدل المطلوب للتخرج هو 2,75" must be > 0.90.
Save this prompt in "docs/prompts/prompts-log.md" under the next "Prompt N" heading. Do not commit and do not open a PR.

## Prompt 15

The retrieval scores are far too low (0.56 for an exact match), which suggests the query is not being normalized. In backend/scripts/retrieve.py, import the clean_text function from backend.scripts.parse_source and apply it to the query string before embedding it. 
Verify the fix by running the "Perfect Match" test: the score for "الحد الأدنى للمعدل المطلوب للتخرج هو 2,75" must be > 0.90.
Save this prompt in "docs/prompts/prompts-log.md" under the next "Prompt N" heading. Do not commit and do not open a PR.

## Prompt 16

Keep the query clean_text call in backend/scripts/retrieve.py. Create eval/questions_regulation.json with these 10 items, each {id, question, expected_articles, note}: q1 "كم نسبة الغياب اللي تمنعني من دخول الاختبار النهائي؟" -> [25,26]; q2 "اذا غبت عن الفاينل بعذر كيف أقدم على اختبار بديل؟" -> [32]; q3 "أقدر أأجل الترم كامل؟" -> [54]; q4 "أبغى أنسحب من مقرر، وش الشروط؟" -> [56]; q5 "كم إنذار يجيني قبل ما أفصل من الجامعة؟" -> [58]; q6 "انقطعت عن الدراسة سنة، كيف أرجع؟" -> [60]; q7 "أبغى أحول من تخصص لتخصص ثاني داخل الكلية" -> [38]; q8 "كم المعدل المطلوب عشان أتخرج؟" -> [62]; q9 "درست مقرر برا الجامعة، كيف يعادلونه؟" -> [37]; q10 "الدراسة فصلين ولا ثلاثة، وفيه صيفي؟" -> [8].
Create eval/run_retrieval_eval.py: for each question call the retriever, take top 5, print the rank of the expected article per question, then hit@1, hit@3 and hit@5 over all 10.
Add pytest tests with a fake retriever so the scoring logic is covered offline. Run the script on ref-01 and report hit@1, hit@3, hit@5 and every question that missed at k=5.
Save this prompt in "docs/prompts/prompts-log.md" under the next "Prompt N" heading. Do not commit and do not open a PR.

## Prompt 17

Run `python -m pytest backend/tests -q`; if anything fails, stop and report.
If it passes, commit on fix/retrieve-normalization with message "feat: normalize queries and measure retrieval hit@k" and push with `git push -u origin fix/retrieve-normalization`.
Open a pull request into main with that title; body: what changed, the measured numbers (hit@1 0.50, hit@3 0.80, hit@5 0.80), and that q3 and q5 miss because of dialect-vs-legal wording.
Save this prompt in "docs/prompts/prompts-log.md" under the next "Prompt N" heading. Do not merge the pull request.

## Prompt 18

Add backend/config/chat.toml (model default gpt-4o-mini, temperature 0, max_output_tokens 700, price_per_1m_input/output) and backend/scripts/answer.py: retrieve top-k, put ONLY those articles in the prompt with their article number, heading and url, and ask for an Arabic answer that cites the article numbers; if the retrieved articles do not support an answer, return exactly the fallback text that says the information is not available in the regulation and refers the student to عمادة القبول والتسجيل, with an empty citations list.
Add POST /chat in the FastAPI app matching docs/api-contract.md ({message, session_id} -> {answer, citations:[{title, article, url}]}), returning 422 for an empty message or one over 1000 characters, and reading the key from .env only (never logging it).
Add pytest tests with a fake LLM and fake retriever: an answerable question returns citations, and an unsupported question returns the fallback with no citations. Then run the endpoint against 3 real questions and report the answers and citations.
Save this prompt in "docs/prompts/prompts-log.md" under the next "Prompt N" heading. Do not commit and do not open a PR.

## Prompt 19

In backend/scripts/parse_source.py, reverse every maximal run of Arabic-Indic digits (U+0660-U+0669) and then map them to ASCII 0-9, because the PDF extraction reverses them: ٪٥٧ must become 75 and ٢٤٤١ must become 1442. Leave ASCII digit runs such as 2,75 untouched.
Add tests: '٪٥٧'->'75', '٢٤٤١'->'1442', '4,5٠'->'4,50', and '2,75' unchanged. Then re-run parse, chunk and embed for ref-01 and report: every percentage value found (all must be in 10,15,20,25,30,40,50,60,75) and the number of Arabic-Indic digits left (must be 0).
Save this prompt in "docs/prompts/prompts-log.md" under the next "Prompt N" heading. Do not commit and do not open a PR.

## Prompt 20

Run python -m pytest backend/tests -q; if anything fails, stop and report.
If it passes, commit on the current branch with message "feat: answer with citations, digit-order fix" and push with git push -u origin HEAD.
Open a pull request into main; body: what changed, the numbers before and after the digit fix (21 reversed percentages and 57% for attendance, now 75% and zero Arabic-Indic digits), hit@k 0.50/0.80/0.80, and that q3 and q5 still miss.
Save this prompt in "docs/prompts/prompts-log.md" under the next "Prompt N" heading. Do not merge the pull request.
