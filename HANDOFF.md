# Handoff — KSU Agent

State at 2026-11-24. Everything below is committed and merged to `main` unless it says otherwise.

## Where the project stands

Two halves. The RAG half (Phase 1) is complete and runs entirely on the KSU gateway. The agent
half (Phase 3, writing to Edugate) has not started.

| Area | State |
| :--- | :--- |
| Ingestion → chunk → embed → hybrid retrieve → cited answer | done |
| Auth (register/login/logout/me, cookie sessions) | done |
| Intent router (regex → classifier → signed route token) | done |
| Reasoning (facts computed in code, templates for verdicts) | done |
| Chrome MV3 extension (Edugate + LMS readers) | done, fixtures only |
| Frontend chat, consent card, citations, i18n | done |
| Chat memory (last 6 turns, server stores none) | done |
| Saudi dialect for the explanation, formal for the quote | done |
| Study plans as tables (SWE, CE) | done, not yet wired to chat |
| Streaming the answer as it arrives | **not started** |
| Academic calendar | **not started** |
| Phase 3 — writing to Edugate | **not started** |
| Reranker (SD-16), pgvector (SD-17), CI, Docker | open |

Verified now: `pytest backend/tests/` 795 passed, `vitest run` 43 passed, `tsc --noEmit` clean,
`run_retrieval_eval.py` hit@1 0.70 / hit@3 0.80 / hit@5 0.80, `run_answer_eval.py` 8/11 and 8/10.

## Decisions already made, do not re-litigate

- The gateway is `https://ai-gateway.seai-x.com/inference/v1`, model `DeepSeek-V4.1-Flash` pinned by
  name (never the `PRIMARY_MODEL` alias), embedder `local-embedding-model` at 1024 dimensions.
- `json_object`, never `json_schema`: the gateway does not offer structured output.
- `reasoning_effort: none` on every call, or latency doubles.
- The corpus stays **Arabic**. A stronger embedder moved hit@1 from 0.60 to 0.70 with the corpus
  untouched, so the language was never the reason retrieval was weak. The English corpus is deferred.
- Study plans and dates are **tables**, not RAG chunks (SD-19).
- The dialect rule applies to the model's explanation only. Verdict templates are written in code and
  are still formal Arabic.
- Streaming keeps the JSON contract: the client buffers until `"answer":` and renders from there.

## What to do next, in order

### 1. Wire the study plans into the chat (slice 2)

The tables and loader exist: `backend/scripts/plans.py` (`load`, `level`, `course`, `prerequisites`),
data at `data/processed/plans/<id>.json`, sources in `backend/config/plans.toml`.

What is missing is the route. A question like "وش متطلب MATH 101" or "وش مستوى ٥ في هندسة البرمجيات"
must reach the plan table instead of retrieval. Add a `plan` route to `app/intent.py` beside the existing
`reason:<kind>` routes, answer a listing with **no model call** (the table already has the rows), and cite
`program_url`. A plan whose `stale_risk` is true must refuse to answer, or answer with the warning.

### 2. The academic calendar

Same shape, new source. `https://dar.ksu.edu.sa/ar/current` is server-rendered and carries four `<table>`
elements of dated rows (verified 2026-11-24). Store `data/processed/calendar.json` as
`{label, start, end}` rows, answer a date question from it, and return the fallback for a date the table
does not carry — never a guess. Design section 4 of the study-plans spec covers it.

### 3. Streaming

The user chose to keep the JSON contract and buffer on the client until `"answer":` appears. That needs an
SSE endpoint on the backend that streams the model's tokens, and a client that parses the accumulating
buffer. `answer.ask_model` currently returns the whole reply; LangChain's `client.stream(...)` replaces
`client.invoke(...)` for that path only, and `parse_model_answer` still validates the finished object.

### 4. Then the agent half (Phase 3)

Read the constraint first: the gateway reports `tool_call: false`, so LangGraph cannot use `bind_tools`. The
existing design already avoids native tool calling — regex, a JSON classifier, and a signed route token —
and the agent must follow the same shape: a node returns JSON naming the tool, not a tool call.
Registration is a write, so it needs a confirmation step and a saved copy for rollback.

## Traps found the hard way

- `main` is protected: a direct `git push` is rejected. Every change goes through a branch and a PR.
- The three `origin/feat/frontend-*` branches look unmerged but their content is in `main` via squash
  merges. `git diff main <branch>` shows only deletions. They can be deleted.
- `node_modules` had no dev dependencies, so `vitest` was missing. `npm install` in `frontend/` fixes it.
- Node defines an experimental global `localStorage` that is undefined without `--localstorage-file` and
  shadows jsdom's. `frontend/vitest.setup.ts` installs an in-memory store; without it all 39 tests fail.
- `echo` in cmd writes Arabic in the console codepage, not UTF-8. A request body built that way reaches
  the API as mojibake and the answer is a fallback. Build JSON bodies with Python, not `echo`.
- Arabic-Indic digits in pymupdf output are in visual order and must be reversed;
  `parse_source.fix_arabic_digits` does that. JSON:API HTML is in logical order and must **not** be reversed.
- The whole frontend suite and the backend suite are green, so a failure is almost always the change, not the
  environment.
