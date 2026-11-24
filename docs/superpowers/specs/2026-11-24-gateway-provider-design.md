# Design — Gateway provider seam and re-index

Date: 2026-11-24
Status: proposed

## 1. Goal

Move the answer model and the embedding model onto the KSU API gateway
(`https://ai-gateway.seai-x.com/inference/v1`), re-index the ingested regulation
with the gateway's embedding model, and replace the hand-rolled transport with
LangChain — without losing any guarantee the current code enforces.

The corpus stays Arabic. The English corpus is deferred (see §9).

## 2. Verified facts about the gateway

Probed on 2026-11-24 with the gateway key. These are measurements, not
assumptions:

| Fact | Evidence |
| :--- | :--- |
| OpenAI-compatible shape | `GET /models` without a key answers `401 {"error":{"code":"invalid_api_key"}}` |
| `PRIMARY_MODEL` is an alias for `DeepSeek-V4.1-Flash` | same `created` 1788775686, same tokenizer repo `deepseek-ai/DeepSeek-V4.1-Flash-1017` |
| Chat model context | 1,048,576 tokens in, 65,536 out |
| `response_format: json_object` works | `finish_reason: stop`, 7 completion tokens, valid completion |
| `response_format: json_schema` is not offered | gateway metadata `structured_output: false` |
| Native tool calling is not offered | gateway metadata `tool_call: false` |
| Thinking is switchable | `reasoning_efforts: ["none","low","high","max"]` |
| Serving stack is vLLM, not DeepSeek's API | `system_fingerprint: vllm-0.1.dev21691+g622912b9b-tp8-6a83bd08` |
| An embedding model exists on the gateway | `local-embedding-model`, `capabilities: ["embedding"]`, context 32,768 |
| Embedding vectors are 1024-dimensional | one probe returned `len(data[0].embedding) == 1024` |
| Embeddings accept Arabic | the same probe's input was an Arabic question |
| Embeddings accept a batch | 4 inputs returned `data.Count == 4` |

Two consequences follow, and both shape this design:

1. `answer.py:174` and `intent.py:216` both send `response_format` with
   `type: json_schema`. The gateway does not offer structured output, so both
   must move to `json_object`. This is not a downgrade in safety: `answer.py`
   already validates the model's reply in `parse_model_answer`, which rejects a
   reply that is not the expected object, and that validation is what the citation
   contract rests on.
2. `tool_call: false` means the agent half (Phase 3) cannot use native tool
   calling. The project's existing design already avoids it — a regex fast path, a
   JSON classifier, and a signed route token. This design therefore validates
   SD-20 rather than contradicting it.

## 3. Decisions

| ID | Decision | Reason |
| :--- | :--- | :--- |
| G1 | Chat and embeddings both go through the gateway | One key, one vendor, no local model download |
| G2 | Model id is pinned as `DeepSeek-V4.1-Flash`, not `PRIMARY_MODEL` | An alias can be repointed at a different model without a repo change; the tokenizer hash proves the alias's target can drift |
| G3 | `json_object`, not `json_schema` | The gateway offers the former and not the latter |
| G4 | `reasoning_effort: "none"` on every call | Thinking mode is on by default and would break the <5 s median target (SD-03) |
| G5 | Embedding model is `local-embedding-model`, 1024 dims | Verified above; `bge-m3` would have needed a 2 GB download for the same vector length |
| G6 | The corpus stays Arabic | Arabic retrieval is measured before any language change (§9) |
| G7 | LangChain replaces the transport, not the guards | The guards have tests; the transport does not change behaviour |

## 4. Design — one seam, two config files

A new module `backend/scripts/gateway.py` owns every provider detail, so no script
names a vendor:

```python
def make_chat_client(config) -> OpenAI        # base_url, key from config.api_key_env
def chat_kwargs(config) -> dict               # response_format, extra_body
def make_embed_client(config) -> OpenAI
def embed_kwargs(config) -> dict               # dimensions only when send_dimensions
def api_key(config, env_file=DEFAULT_ENV_FILE) -> str
```

`answer.make_client`, `embed_chunks.make_client` and `retrieve.embed_query` become
thin calls into this module. Their names and signatures are unchanged, because
`backend/tests/` patches them by name (`test_retrieve.py:377`,
`test_retrieve_hybrid.py:342`) and a signature change would edit tests rather than
prove the swap.

`chat.toml` gains `base_url`, `api_key_env`, `json_mode` and `reasoning_effort`.
`embeddings.toml` gains `base_url`, `api_key_env`, `send_dimensions` and moves
`provider` to `gateway`.

`.env` holds the key and nothing else:

```
LLM_API_KEY=
```

`api_key` keeps its default `env_name="OPENAI_API_KEY"` so
`test_embed_chunks.py:223` still passes, and `make_client` passes
`config.api_key_env` explicitly.

## 5. Slice 1 — the gateway swap and the re-index

One slice, because the chat swap and the embedding swap are the same edit: one
module, two config files, one re-index.

Changes:

- `backend/config/chat.toml`: `provider = "gateway"`, `base_url`, `model =
  "DeepSeek-V4.1-Flash"`, `api_key_env = "LLM_API_KEY"`, `json_mode =
  "json_object"`, `reasoning_effort = "none"`, prices from the gateway.
- `backend/config/embeddings.toml`: `provider = "gateway"`, `base_url`, `model =
  "local-embedding-model"`, `dimensions = 1024`, `api_key_env = "LLM_API_KEY"`,
  `send_dimensions = false`, `price_per_1m_tokens = 0.0`.
- `backend/scripts/gateway.py`: new, as in §4.
- `answer.ask_model`: `response_format` and `extra_body` from `chat_kwargs`.
- `intent.classify`: same.
- `embed_chunks.embed_chunks`: `dimensions` and `encoding_format` only when
  `send_dimensions`; the returned length is already validated at line 278, so a
  model that ignores the parameter is caught rather than trusted.
- `embed_chunks.api_key`: `env_name` parameter, default unchanged.
- `.env.example`: `LLM_API_KEY=`.
- Re-index: `python backend/scripts/embed_chunks.py --source-id ref-01`.

Gate — all of these must hold before slice 2:

1. `pytest backend/tests/` passes.
2. `eval/run_answer_eval.py` scores no lower than the recorded baseline.
3. `eval/run_retrieval_eval.py` scores no lower than the recorded baseline.
4. The re-index writes 75 vectors of 1024 dimensions, and
   `retrieve.load_index` accepts it (it refuses a model or dimension mismatch
   already, at lines 390–411).

Gate 2 is the one that answers the Arabic question. If retrieval drops, the
embedder is the suspect and not the language, because the corpus did not change.

## 6. Slice 2 — LangChain replaces the transport

Only after slice 1 is green. LangChain replaces how a call is made, not what is
guaranteed:

| Kept | Why |
| :--- | :--- |
| `count_tokens`, `check_input_limits`, `make_batches` | A truncated chunk would be embedded and cited as the whole article |
| `load_index`'s model, dimension and sha256 checks | Searching a stale index returns confident nonsense |
| `parse_model_answer`, `numbers_not_allowed`, `select_citations` | The citation contract |
| `estimate_cost` | The cost log |
| Every public function signature | The tests are the proof |

`ChatOpenAI(base_url=..., model=..., temperature=0)` and
`OpenAIEmbeddings(base_url=..., model=..., dimensions=1024)` replace the direct
SDK calls. `chat_kwargs` becomes the `model_kwargs`.

Gate — `pytest backend/tests/` passes with **no test file edited**. A test that
needs editing means behaviour changed, and that is the moment to stop and look.

## 7. Out of scope

- The English corpus. Deferred until slice 1's gate 3 measures Arabic retrieval
  with a stronger embedder. The English source is a bilingual HTML page, not a PDF,
  and it omits the executive-rules annex; `parse_source.py` is
  PyMuPDF-only. That is a larger slice with its own design.
- Native tool calling, which the gateway does not offer.
- A reranker (SD-16).
- pgvector (SD-17).

## 8. Risks

| Risk | Handling |
| :--- | :--- |
| One key governs both chat and retrieval | Accepted: the project holds its own gateway key, independent of DevAI, so a DevAI update cannot revoke it |
| `json_object` returns a reply that is not the schema | `parse_model_answer` already rejects it; the fallback answer runs |
| `local-embedding-model` ignores `dimensions` | The response length is validated at line 278 |
| The embedding tokenizer is unavailable | `cl100k_base` counts approximately; `max_input_tokens` is set to 8192 against a 32,768 limit |
| The index is a build artifact (`data/processed/` is git-ignored) | The colleague re-runs ingestion; gate 4 proves the index matches the chunks |
| The gateway is a single point of failure for chat and retrieval | Accepted; recorded here rather than discovered later |
