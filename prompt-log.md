# Prompt log

The prompt sent to each sub-agent, per task. Newest task first. Nothing is
paraphrased: an entry is the prompt as sent, followed by what came back that the
plan did not anticipate.

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
5. `test_route_token.py` is flaky for a reason unrelated to this branch: an
   absent `KSU_ROUTE_SECRET` mints a random key per process, and flipping the
   token's last character decodes to the identical signature for about 6% of keys.
   The variable is now in `.env.example` and `.env`.
6. `app/intent.py` sends `json_object` but no `reasoning_effort`, so the
   classifier still thinks. That belongs to Task 2 and the plan did not name it.
