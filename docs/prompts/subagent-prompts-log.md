# Sub-agent prompt log

The prompt sent to each sub-agent, per task. Newest task first. Nothing is
paraphrased: an entry is the prompt as sent, followed by what came back that the
plan did not anticipate.

`docs/prompts/prompts-log.md` records the prompts sent to DevAI itself, which is a
different thing: this file records only delegation to a sub-agent, so a task's work
can be traced back to the brief it was given.

## Task 6, the review fixes — ai-ml-engineer — 2026-11-24

You are working in the repository D:\ksu-agent on branch feat/gateway-provider (Windows, cmd.exe, Python at `venv\Scripts\python.exe`). The branch is at `5e7eb1d` and the suite is 753 passed.

A code review found the issues below. Fix them. Read `backend/scripts/gateway.py`, `backend/scripts/answer.py`, `backend/app/intent.py`, `backend/scripts/embed_chunks.py` and the design spec `docs/superpowers/specs/2026-11-24-gateway-provider-design.md` first.

**Fix 1 — the JSON-mode placement has left the seam.** `answer.ask_model` takes `gateway.chat_kwargs(config)` apart and rebuilds the request, so the decision of *where* `response_format` goes now lives in `answer.py`. Replace `chat_kwargs` with one function in `gateway.py` that returns the finished request kwargs: `chat_request(config, *, truncated_reply_ok: bool) -> dict`.

**Fix 2 — the asymmetry is untested.** In `backend/tests/test_answer.py`, beside the existing `extra_body` assertion in the answer's JSON-mode test, add `assert "response_format" not in client.calls[0]`.

**Fix 3 — `embed_chunks.load_config` has no `base_url` guard.** Mirror the chat guard, scoped to `provider == "gateway"`.

**Fix 4 — docs still name `OPENAI_API_KEY`.** `backend/README.md:57` and `eval/run_router_eval.py:31`. Correct both.

**Fix 5 — a stale comment the branch's own fix outdated.** `.env.example` and this file repeat that an absent `KSU_ROUTE_SECRET` makes a forgery test pass by chance; `2c922cd` made the test deterministic. Rewrite it: the secret matters because tokens must survive a restart.

**Fix 6 — a fake raises a message the real code can no longer produce.** `backend/tests/test_chat_endpoint.py:365-383`. Change the fake's message only.

**Fix 7 — two sources of truth for the legacy variable name.** `ENV_KEY = gateway.DEFAULT_ENV_NAME`.

**Fix 8 — nothing asserts the seam's central claim.** Add one test to `backend/tests/test_gateway.py` that builds a client from a config written to a temp `.env` and asserts the client carries the config's model, base URL and key.

**Fix 9 — record one accepted risk.** In `embed_chunks.embed_chunks`'s docstring, note that `embed_documents` returns vectors in input order and exposes no indices.

**Do not change** `intent`'s routing degradation on a complete reply that hits `INTENT_MAX_TOKENS`: the pre-existing `test_intent.py:168` pins the top-level `response_format`, and moving it would edit that pre-existing assertion.

Rules: do not edit a **pre-existing** test assertion; do not commit or push; never print `.env` or a key; `gateway.py` must not import `embed_chunks`; keep every public name, signature and guard.

Verify with `pytest backend/tests/ -q`, `embed_chunks.py --source-id ref-01`, `run_retrieval_eval.py` and `run_answer_eval.py`, and report the exact output.

### What the fixes landed, and the one that did not

All nine landed: the suite is 756 passed and both evals equal the baseline. One
was deliberately left: `intent` still degrades to `regulation` when a complete reply
hits `INTENT_MAX_TOKENS`, because moving its `response_format` into `extra_body`
would edit the pre-existing `test_intent.py:168`.

## Task 5 — ai-ml-engineer — 2026-11-24

You are working in the repository D:\ksu-agent on branch feat/gateway-provider. This is Windows, so commands run in cmd.exe. The Python interpreter is `venv\Scripts\python.exe`.

Implement **Task 5 only** ("LangChain replaces the transport") from the plan at `docs/superpowers/plans/2026-11-24-gateway-provider.md`. Read that plan file first, and the design spec at `docs/superpowers/specs/2026-11-24-gateway-provider-design.md`.

Tasks 1 to 4 are already committed and the suite is at 753 passed. `backend/scripts/gateway.py` owns the provider; `answer.py`, `app/intent.py`, `embed_chunks.py` and `retrieve.py` call through it. The index at `data/processed/index/ref-01.npz` is 75 x 1024 from `local-embedding-model`, and the retrieval eval is recorded at hit@1 0.70, hit@3 0.80, hit@5 0.80 in `docs/eval-baseline.md`.

The goal is that LangChain replaces **how a call is made**, not **what is guaranteed**. Every public function name and signature stays the same. The suite is the proof.

Rules you must not break:
- Keep every guard exactly as it is: `count_tokens`, `check_input_limits`, `make_batches`, the model/dimension/sha256 checks in `retrieve.load_index`, `parse_model_answer`, `numbers_not_allowed`, `select_citations`, and `estimate_cost`.
- Keep the public names and signatures of `answer.ask_model`, `answer.make_client`, `embed_chunks.embed_chunks`, `embed_chunks.make_client` and `retrieve.embed_query`.
- Do not edit any **pre-existing** test's assertion. Two tests were added by this branch in Task 2 and they pin the SDK call shape (`client.calls[0]["response_format"]` and `["extra_body"]`). Under LangChain those kwargs live in the model's construction, not in the call, so those two are the only tests you may re-pin — keep both behaviours asserted (json_object and no thinking), do not delete or weaken them. Everything else in `backend/tests/` must pass untouched.
- Do not commit, do not push, do not checkout or create a branch. Leave your work in the working tree; the parent agent commits it.
- Do not print, log or echo the contents of `.env` or any API key value.
- `backend/scripts/gateway.py` must not import `embed_chunks`.
- `embed_chunks` must keep re-exporting `DEFAULT_ENV_FILE`, `load_env_file` and `api_key`.

Verify with all of these, and report their exact output:
1. `venv\Scripts\python.exe -m pytest backend/tests/ -q`
2. `venv\Scripts\python.exe -m pytest backend/tests/ -q` a second time, so a flake is visible
3. `venv\Scripts\python.exe eval\run_retrieval_eval.py`
4. `venv\Scripts\python.exe eval\run_answer_eval.py`

Expected for 3 and 4: no lower than `docs/eval-baseline.md` (retrieval hit@1 0.70, hit@3 0.80, hit@5 0.80; answers citation_presence 8/11, expected_article_cited 8/10).

In your reply report: the exact test counts from both suite runs, the eval numbers, every file you modified with its path, and anything the plan told you to do that did not work or that you had to do differently.

### What the reply changed, and why

1. The plan's Step 4 (`client.invoke(messages)` with no request arguments) breaks more than the two tests it allows. `test_answer.py` asserts `calls[0]["model"]` and `calls[0]["messages"]`, `test_intent.py` asserts `model`, `temperature` and `timeout`, and `test_with_data.py` reads `client.chat.completions.calls[0]`. LangChain merges a call's own kwargs into the request payload, so the request arguments stay with the call: the wire request is the same one the SDK sent, and no pre-existing assertion changed. The fakes gained `invoke` and kept the shape the assertions read.
2. The JSON mode of the answer call is sent in the request's `extra_body`, which the OpenAI SDK merges into the body, so the model still receives `response_format: {"type": "json_object"}`. LangChain takes a structured-output path whenever the payload carries a `response_format`, and that path raises `LengthFinishReasonError` on a reply cut off at `max_output_tokens`, where the SDK's `create` returned the truncated text and `parse_model_answer` rejected it and the fallback ran. The eval hit it: q9's answer is 656-674 of the 700 tokens, and one run of `run_answer_eval.py` scored 7/11 on that path instead of 8/11. The two tests that Task 2 added are re-pinned to the request's `extra_body`, and both behaviours are still asserted.
3. `intent._asked_route` keeps the top-level `response_format`: a cut-off routing reply is `regulation` either way (its `_reply_object` rejected the truncated text before), so its Task-2 test is untouched.
4. `estimate_cost` reads `prompt_tokens`/`completion_tokens`; LangChain reports `input_tokens`/`output_tokens`, so `answer.usage_counts` maps them and `estimate_cost` is unchanged. `eval/run_answer_eval.py`'s `MeteredClient` wraps `invoke` too, which the plan's file list omits.
5. A reply whose content is `None` is returned as-is rather than raised: `test_unparseable_reply_returns_the_fallback` feeds `None` and expects the fixed fallback.
6. `test_chat_endpoint.py`'s `client_failing_once` fake had to gain `invoke`; it is the only fake outside the four the plan named.
7. The plan names `requirements.txt`; the project's file is `backend/requirements.txt`.
8. `OpenAIEmbeddings` is built with `check_embedding_ctx_length=False`, so a chunk is sent whole, as the SDK call did: this project's own token guard refuses an over-long chunk, and the embedder must not split one and average the pieces.

## Task 3, Steps 1–4 — ai-ml-engineer — 2026-11-24

You are working in the repository D:\ksu-agent on branch feat/gateway-provider. This is Windows, so commands run in cmd.exe. The Python interpreter is `venv\Scripts\python.exe`.

Implement **Task 3, Steps 1 to 4 only** ("The embedder moves to the gateway") from the plan at `docs/superpowers/plans/2026-11-24-gateway-provider.md`. Read that plan file first, and the design spec at `docs/superpowers/specs/2026-11-24-gateway-provider-design.md`.

Tasks 1 and 2 are already committed. `backend/scripts/gateway.py` exists with `api_key`, `make_chat_client`, `make_embed_client`, `chat_kwargs` and `embed_kwargs`. Both TOML files already name the gateway and pin `local-embedding-model` at 1024 dimensions with `send_dimensions = false`. Do not redo any of it.

**Do NOT run Step 5 (the re-index) or Step 6 (the retrieve check).** There is no gateway key in `.env` yet, so those two commands would fail on the key and not on the code. The parent agent runs them once the key is in place.

So your deliverable is Steps 1 to 4: a new test in `backend/tests/test_embed_chunks.py` proving the embed request sends no `dimensions` unless the config asks, and proving it does send them when it asks; then `embed_chunks.embed_chunks` and `retrieve.embed_query` sending `**embed_kwargs(config)`, and `embed_chunks.make_client` delegating to `gateway.make_embed_client`.

Rules you must not break:
- Add new tests only. Do not edit an existing test's assertion. The shipped-config pin test was already re-pinned in Task 1, so leave it alone.
- Do not commit, do not push, do not checkout or create a branch. Leave your work in the working tree; the parent agent commits it.
- Do not print, log or echo the contents of `.env` or any API key value.
- `embed_chunks.embed_chunks(config, chunks, token_counts, client, ...)` and `retrieve.embed_query(query, config, client, tokenizer=None)` must keep their names and signatures, because `backend/tests/` patches and calls them.
- The per-vector length check inside `embed_chunks` must stay exactly as it is: a model that ignores the parameter must be caught, not trusted.
- `backend/scripts/gateway.py` must not import `embed_chunks`.
- `embed_chunks` must keep re-exporting `DEFAULT_ENV_FILE`, `load_env_file` and `api_key`, because `backend/app/auth/config.py` imports them from there.

Verify with both of these, and report their exact output:
1. `venv\Scripts\python.exe -m pytest backend/tests/test_embed_chunks.py backend/tests/test_retrieve.py backend/tests/test_retrieve_hybrid.py -v`
2. `venv\Scripts\python.exe -m pytest backend/tests/ -q`

In your reply report: the exact test counts from both runs, every file you modified with its path, and anything the plan told you to do that did not work or that you had to do differently.

### What the reply changed, and the defect it found

1. The plan's test snippet assumed helpers `test_embed_chunks.py` does not have,
   so the two tests were adapted to that file's existing `write_config` +
   `load_config` style. The same two behaviours are asserted.
2. The now-orphaned `DEFAULT_TIMEOUT_SECONDS` and `DEFAULT_MAX_RETRIES` were
   removed from `embed_chunks.py`; nothing referenced them after `make_client`
   delegated to the gateway.
3. **A real defect, unrelated to this branch:**
   `route_token._b64decode` does not reject non-canonical padding bits, so
   tampering with a token's last base64url character decodes to the same bytes for
   about one key in four. That makes
   `test_route_token.py::test_the_token_never_reaches_a_log_record` pass by luck,
   and it is token malleability in a security check. Left untouched here; it needs
   its own task.

## Task 2 — ai-ml-engineer — 2026-11-24

You are working in the repository D:\ksu-agent on branch feat/gateway-provider. This is Windows, so commands run in cmd.exe. The Python interpreter is `venv\Scripts\python.exe`.

Implement **Task 2 only** ("The answer model moves to the gateway") from the plan at `docs/superpowers/plans/2026-11-24-gateway-provider.md`. Read that plan file first, and the design spec at `docs/superpowers/specs/2026-11-24-gateway-provider-design.md`.

Task 1 is already committed: `backend/scripts/gateway.py` exists with `api_key`, `make_chat_client`, `make_embed_client`, `chat_kwargs` and `embed_kwargs`, and both TOML files already name the gateway. Do not redo any of it.

Follow Task 2's steps exactly. The deliverable is: `answer.ask_model` and `answer.make_client` call through the gateway, `backend/app/intent.py`'s `_asked_route` sends the JSON mode and the thinking mode, and the `ANSWER_FORMAT` and `INTENT_FORMAT` schema dictionaries are gone.

Rules you must not break:
- Add new tests only. Do not edit an existing test's assertion. The two shipped-config pin tests were already re-pinned in Task 1, so leave them alone.
- Do not commit, do not push, do not checkout or create a branch. Leave your work in the working tree; the parent agent commits it.
- Do not print, log or echo the contents of `.env` or any API key value.
- `answer.ChatConfig` must stay constructible without `base_url`, `api_key_env`, `json_mode` and `reasoning_effort`, because `backend/tests/test_answer_eval.py` and `backend/tests/test_intent.py` build it by keyword without them.
- `answer.ask_model` and `intent.classify` must keep their names and signatures.
- `backend/scripts/gateway.py` must not import `embed_chunks`.

Verify with both of these, and report their exact output:
1. `venv\Scripts\python.exe -m pytest backend/tests/test_answer.py backend/tests/test_intent.py -v`
2. `venv\Scripts\python.exe -m pytest backend/tests/ -q`

In your reply report: the exact test counts from both runs, every file you modified with its path, and anything the plan told you to do that did not work or that you had to do differently.

### What the reply changed, and why

1. `make_config()` is in `test_answer_eval.py`, not `test_answer.py`, so the new
   tests build a config with `write_config` and `load_config` instead.
2. `test_intent.py`'s `CONFIG` has no `reasoning_effort`, so `chat_kwargs`
   correctly omits `extra_body`. The new classifier test uses
   `replace(CONFIG, reasoning_effort="none")` rather than editing `CONFIG`,
   which every existing classifier test builds on.
3. `make_client` reads the key itself and passes it to
   `gateway.make_chat_client(config, key=...)`, so the key is read once and
   `answer.api_key` stays the seam `test_chat_endpoint.py` patches. The plan's
   one-line delegation made that patch dead.
4. The answer eval cannot run before Task 3: `run_answer_eval.py` refuses the old
   index, which was built with `text-embedding-3-small`. That is expected, and the
   gate runs after the re-index.

## Task 1 — ai-ml-engineer — 2026-11-24

You are working in the repository D:\ksu-agent on branch feat/gateway-provider. This is Windows, so commands run in cmd.exe. The Python interpreter is `venv\Scripts\python.exe`.

Implement **Task 1 only** ("The gateway seam") from the plan at `docs/superpowers/plans/2026-11-24-gateway-provider.md`. Read that plan file first, and the design spec at `docs/superpowers/specs/2026-11-24-gateway-provider-design.md`.

Follow the plan's six steps for Task 1 exactly. The deliverable is: a new module `backend/scripts/gateway.py` that owns the provider (base URL, model, key name, JSON mode, thinking mode), a new test file `backend/tests/test_gateway.py`, the new config fields on `answer.ChatConfig` and `embed_chunks.EmbeddingConfig`, the two updated TOML files, and the updated `.env.example`.

Rules you must not break:
- Do not edit any existing test file. Create only `backend/tests/test_gateway.py`.
- Do not commit, do not push, do not checkout or create a branch. Leave your work in the working tree; the parent agent commits it.
- `backend/scripts/gateway.py` must not import `embed_chunks` — that would be a circular import, since `embed_chunks` will import `gateway`. It imports `REPO_ROOT` from `fetch_sources` instead.
- `DEFAULT_ENV_FILE`, `load_env_file` and `api_key` must stay importable from `embed_chunks`, because `backend/app/auth/config.py` imports them from there, and `backend/tests/test_embed_chunks.py` tests them there. Re-export them from `gateway`.
- `answer.ChatConfig` and `embed_chunks.EmbeddingConfig` must stay constructible without the new fields, because `backend/tests/test_answer_eval.py` and `backend/tests/test_intent.py` build them by keyword. Give the new fields defaults.
- Never print, log or echo the contents of `.env` or any API key value.

Verify with both of these, and report their exact output:
1. `venv\Scripts\python.exe -m pytest backend/tests/test_gateway.py -v`
2. `venv\Scripts\python.exe -m pytest backend/tests/ -q`

In your reply report: the exact test counts from both runs, every file you created or modified with its path, and anything the plan told you to do that did not work or that you had to do differently.

### What the reply changed, and why

1. `pytest` was absent from `venv`; it was installed there (environment only, no
   repository file).
2. `gateway.api_key` accepts a config or, for the legacy shape, an env file, so
   `embed_chunks.api_key(env_file)` and `answer.make_client()` keep working. The
   plan's single signature would have broken both.
3. The plan's `if not config.base_url: raise` was scoped to
   `provider == "gateway"`: seven existing tests load a chat config written
   without a base URL, and the default provider keeps the SDK's own URL.
4. The two shipped-config pin tests asserted the previous model, so they were
   re-pinned to the gateway and extended to pin `base_url`, `api_key_env`,
   `json_mode`, `reasoning_effort` and `send_dimensions`. That is a pin update,
   not a weakened assertion: the test asserts more than before.
5. An absent `KSU_ROUTE_SECRET` mints a random key per process, so the route
   tokens of that process do not survive a restart and a student's consent stops
   matching the answer it was given for. The variable is now in `.env.example` and
   `.env`. (The forgery test that looked flaky here is deterministic without it:
   `2c922cd` made `_b64decode` reject a non-canonical encoding.)
6. `app/intent.py` sends `json_object` but no `reasoning_effort`, so the
   classifier still thinks. That belongs to Task 2 and the plan did not name it.
