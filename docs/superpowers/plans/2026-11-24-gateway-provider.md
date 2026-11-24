# Gateway Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: load the `executing-plans` skill to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the answer model and the embedding model onto the KSU API gateway, rebuild the vector index at 1024 dimensions, and replace the hand-rolled transport with LangChain without losing a single guarantee the current code enforces.

**Architecture:** One new module, `backend/scripts/gateway.py`, owns every provider detail — base URL, model, key name, JSON mode and thinking mode. The four scripts that call a provider (`answer.py`, `intent.py`, `embed_chunks.py`, `retrieve.py`) call into it instead of building an SDK client. Two TOML files carry the non-secret settings; `.env` carries only the key. The public function names and signatures never change, because `backend/tests/` patches them by name and the suite is the proof that behaviour did not change.

**Tech Stack:** Python 3.13, FastAPI, `openai` 2.54 (OpenAI-compatible gateway over vLLM), `numpy`, `pytest`; LangChain (`langchain-core`, `langchain-openai`) in the final task only.

**Spec:** `docs/superpowers/specs/2026-11-24-gateway-provider-design.md`

## Global Constraints

- Gateway base URL: `https://ai-gateway.seai-x.com/inference/v1`
- Chat model id, pinned exactly: `DeepSeek-V4.1-Flash` — never `PRIMARY_MODEL`, which is an alias whose target can drift.
- Embedding model id: `local-embedding-model`, 1024 dimensions.
- `response_format` is `{"type": "json_object"}` — never `json_schema`, which the gateway does not offer.
- `reasoning_effort` is `"none"` on every chat call — thinking mode is on by default.
- The key is read from the environment variable the config names, never logged, printed, returned, or committed.
- Every commit updates `prompt-log.md` with the prompt sent to each sub-agent in that task.
- No existing test file is edited to make a change pass. A new test is added; an existing assertion is not weakened.

## Review Focus

- A chunk over the embedding model's input limit: `check_input_limits` must still abort before anything is embedded, because `cl100k_base` only approximates the gateway model's tokenizer.
- A reply that is valid JSON but not the answer object: `parse_model_answer` must still reject it and the fallback answer must still run.
- A gateway that ignores `dimensions`: the returned vector length must still be checked against the config, not trusted.
- A stale index after a model change: `load_index` must still refuse it rather than search it.
- An absent key: the error must name the variable and the app must answer 503, never a traceback.

---

### Task 1: The gateway seam

**Files:**
- Create: `backend/scripts/gateway.py`
- Create: `backend/tests/test_gateway.py`
- Create: `prompt-log.md`
- Modify: `backend/config/chat.toml`
- Modify: `backend/config/embeddings.toml`
- Modify: `backend/scripts/answer.py:55-...` (`ChatConfig`, `load_config`)
- Modify: `backend/scripts/embed_chunks.py` (`EmbeddingConfig`, `load_config`, re-exports)

**Interfaces:**
- Consumes: `fetch_sources.REPO_ROOT`
- Produces: `gateway.DEFAULT_ENV_FILE`, `gateway.load_env_file(path) -> dict[str, str]`, `gateway.api_key(config, env_file=DEFAULT_ENV_FILE) -> str`, `gateway.make_chat_client(config, env_file=DEFAULT_ENV_FILE)`, `gateway.make_embed_client(config, env_file=DEFAULT_ENV_FILE)`, `gateway.chat_kwargs(config) -> dict`, `gateway.embed_kwargs(config) -> dict`
- Produces on `answer.ChatConfig`: `base_url: str`, `api_key_env: str`, `json_mode: str`, `reasoning_effort: str`, all with defaults so `answer.ChatConfig(**values)` in `test_answer_eval.py:96` and `test_intent.py:27` still constructs.
- Produces on `embed_chunks.EmbeddingConfig`: `base_url: str`, `api_key_env: str`, `send_dimensions: bool`, all with defaults.
- `embed_chunks` keeps re-exporting `DEFAULT_ENV_FILE`, `load_env_file` and `api_key`, because `app/auth/config.py:10` imports them from there.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_gateway.py
"""The gateway seam: one place that knows the provider, its key name and its limits."""

import pytest

import gateway
from embed_chunks import EmbeddingConfig


def chat_config(**overrides):
    values = {
        "provider": "gateway",
        "model": "DeepSeek-V4.1-Flash",
        "temperature": 0.0,
        "max_output_tokens": 700,
        "price_per_1m_input": 0.30,
        "price_per_1m_output": 1.20,
        "source_id": "ref-01",
        "base_url": "https://ai-gateway.seai-x.com/inference/v1",
        "api_key_env": "LLM_API_KEY",
        "json_mode": "json_object",
        "reasoning_effort": "none",
    }
    values.update(overrides)
    return __import__("answer").ChatConfig(**values)


def embed_config(**overrides):
    values = {
        "provider": "gateway",
        "model": "local-embedding-model",
        "dimensions": 1024,
        "max_input_tokens": 8192,
        "price_per_1m_tokens": 0.0,
        "tokenizer": "cl100k_base",
        "batch_size": 64,
        "batch_max_tokens": 200000,
        "base_url": "https://ai-gateway.seai-x.com/inference/v1",
        "api_key_env": "LLM_API_KEY",
        "send_dimensions": False,
    }
    values.update(overrides)
    return EmbeddingConfig(**values)


def test_the_key_is_read_from_the_variable_the_config_names(tmp_path):
    """A project key can be named anything; the code never hardcodes OPENAI_API_KEY."""
    env_file = tmp_path / ".env"
    env_file.write_text("LLM_API_KEY=gw-test-value\n", encoding="utf-8")

    assert gateway.api_key(chat_config(), env_file) == "gw-test-value"


def test_an_absent_key_names_the_variable_and_never_its_value(tmp_path):
    with pytest.raises(RuntimeError, match="LLM_API_KEY"):
        gateway.api_key(chat_config(), tmp_path / "absent.env")


def test_chat_asks_for_json_object_and_no_thinking():
    kwargs = gateway.chat_kwargs(chat_config())

    assert kwargs["response_format"] == {"type": "json_object"}
    assert kwargs["extra_body"] == {"reasoning_effort": "none"}


def test_chat_omits_the_reasoning_effort_when_none_is_configured():
    kwargs = gateway.chat_kwargs(chat_config(reasoning_effort=""))

    assert "extra_body" not in kwargs


def test_embed_sends_no_dimensions_by_default():
    """The gateway model may reject a parameter it does not know; it is opt-in."""
    kwargs = gateway.embed_kwargs(embed_config())

    assert "dimensions" not in kwargs
    assert kwargs["encoding_format"] == "float"


def test_embed_sends_the_dimensions_when_the_config_asks():
    kwargs = gateway.embed_kwargs(embed_config(send_dimensions=True))

    assert kwargs["dimensions"] == 1024
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `venv\Scripts\python.exe -m pytest backend/tests/test_gateway.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gateway'`

- [ ] **Step 3: Write the module, the config fields and the TOML values**

```python
# backend/scripts/gateway.py
"""One place that knows the provider: base URL, key name, JSON and thinking mode.

Every script that calls a model goes through this module, so no script names a vendor and
swapping the gateway is a change to two TOML files. The key is read from the environment
variable the config names, so the project and a teammate hold different keys without a code
change, and its value is never logged, printed or returned.
"""

from __future__ import annotations

import os
from pathlib import Path

from fetch_sources import REPO_ROOT

DEFAULT_ENV_FILE = REPO_ROOT / ".env"
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_MAX_RETRIES = 3


def load_env_file(env_path: Path) -> dict[str, str]:
    """Read simple KEY=VALUE lines from ``env_path``; empty when absent."""
    env_path = Path(env_path)
    if not env_path.exists():
        return {}

    values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip()
        if name.startswith("export "):
            name = name[len("export ") :].strip()
        values[name] = value.strip().strip('"').strip("'")
    return values


def api_key(config, env_file: Path = DEFAULT_ENV_FILE) -> str:
    """The key named by the config, from .env then the environment.

    The value is never returned to a log or an error message.
    """
    name = config.api_key_env
    value = (load_env_file(env_file).get(name) or os.environ.get(name, "")).strip()
    if not value:
        raise RuntimeError(
            f"{name} is not set; add it to {Path(env_file).name} "
            f"(git-ignored, see .env.example) or export it"
        )
    return value


def make_chat_client(config, env_file: Path = DEFAULT_ENV_FILE):
    """The chat client for the configured gateway."""
    from openai import OpenAI

    return OpenAI(
        api_key=api_key(config, env_file),
        base_url=config.base_url,
        timeout=config.timeout_seconds,
        max_retries=config.max_retries,
    )


def make_embed_client(config, env_file: Path = DEFAULT_ENV_FILE):
    """The embedding client for the configured gateway."""
    from openai import OpenAI

    return OpenAI(
        api_key=api_key(config, env_file),
        base_url=config.base_url,
        timeout=DEFAULT_TIMEOUT_SECONDS,
        max_retries=DEFAULT_MAX_RETRIES,
    )


def chat_kwargs(config) -> dict:
    """The JSON mode and thinking mode every chat call sends."""
    kwargs: dict = {"response_format": {"type": config.json_mode}}
    if config.reasoning_effort:
        kwargs["extra_body"] = {"reasoning_effort": config.reasoning_effort}
    return kwargs


def embed_kwargs(config) -> dict:
    """The request parameters every embedding call sends.

    ``dimensions`` is opt-in: a model that does not know the parameter may reject the
    request, and the returned length is validated by the caller anyway.
    """
    kwargs: dict = {"encoding_format": "float"}
    if config.send_dimensions:
        kwargs["dimensions"] = config.dimensions
    return kwargs
```

In `backend/config/chat.toml`, replace the `[chat]` table with:

```toml
[chat]
provider = "gateway"
base_url = "https://ai-gateway.seai-x.com/inference/v1"
model = "DeepSeek-V4.1-Flash"
api_key_env = "LLM_API_KEY"
json_mode = "json_object"
reasoning_effort = "none"
temperature = 0.0
max_output_tokens = 700
price_per_1m_input = 0.30
price_per_1m_output = 1.20
source_id = "ref-01"
timeout_seconds = 60
max_retries = 3
```

In `backend/config/embeddings.toml`, replace the `[embedding]` table with:

```toml
[embedding]
provider = "gateway"
base_url = "https://ai-gateway.seai-x.com/inference/v1"
model = "local-embedding-model"
api_key_env = "LLM_API_KEY"
dimensions = 1024
max_input_tokens = 8192
price_per_1m_tokens = 0.0
tokenizer = "cl100k_base"
batch_size = 64
batch_max_tokens = 200000
send_dimensions = false
```

In `backend/scripts/answer.py`, add the four fields to `ChatConfig` with defaults, after `max_retries`:

```python
    base_url: str = ""
    api_key_env: str = "OPENAI_API_KEY"
    json_mode: str = "json_object"
    reasoning_effort: str = ""
```

and read them in `load_config`:

```python
        base_url=str(section.get("base_url", "")).strip(),
        api_key_env=str(section.get("api_key_env", "OPENAI_API_KEY")).strip(),
        json_mode=str(section.get("json_mode", "json_object")).strip(),
        reasoning_effort=str(section.get("reasoning_effort", "")).strip(),
```

and extend the validation after the existing checks:

```python
    if not config.base_url:
        raise ValueError(f"{config_path}: base_url is required")
    if config.json_mode not in {"json_object", "text"}:
        raise ValueError(f"{config_path}: json_mode must be json_object or text")
```

In `backend/scripts/embed_chunks.py`, add the three fields to `EmbeddingConfig` with defaults, after `batch_max_tokens`:

```python
    base_url: str = ""
    api_key_env: str = "OPENAI_API_KEY"
    send_dimensions: bool = False
```

read them in `load_config`:

```python
        base_url=str(section.get("base_url", "")).strip(),
        api_key_env=str(section.get("api_key_env", "OPENAI_API_KEY")).strip(),
        send_dimensions=bool(section.get("send_dimensions", False)),
```

and replace the local `DEFAULT_ENV_FILE` and `load_env_file` definitions with a re-export, so `app/auth/config.py:10` and `test_embed_chunks.py:218-230` keep importing them from here:

```python
from gateway import DEFAULT_ENV_FILE, load_env_file, api_key
```

`.env.example` becomes:

```
# Copy this file to .env at the repo root and fill in the value.
# .env is git-ignored and must never be committed or printed.
#
# One key covers the chat model and the embedding model, both on the gateway
# configured in backend/config/chat.toml and backend/config/embeddings.toml.
LLM_API_KEY=
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `venv\Scripts\python.exe -m pytest backend/tests/test_gateway.py -v`
Expected: PASS, 7 tests

- [ ] **Step 5: Run the whole suite to prove nothing else moved**

Run: `venv\Scripts\python.exe -m pytest backend/tests/ -q`
Expected: PASS, the same count as before this task

- [ ] **Step 6: Write `prompt-log.md` and commit**

Create `prompt-log.md` with the header below and this task's entry, then commit:

```markdown
# Prompt log

The prompt sent to each sub-agent, per task. Newest task first. Nothing is
paraphrased: an entry is the prompt as sent.

## Task 1 — ai-ml-engineer — 2026-11-24

<paste the prompt sent to the ai-ml-engineer sub-agent verbatim>
```

```bash
git add backend/scripts/gateway.py backend/tests/test_gateway.py backend/config/chat.toml backend/config/embeddings.toml backend/scripts/answer.py backend/scripts/embed_chunks.py .env.example prompt-log.md
git commit -m "feat: one gateway seam that names the provider in config"
```

---

### Task 2: The answer model moves to the gateway

**Files:**
- Modify: `backend/scripts/answer.py` (`ANSWER_FORMAT`, `ask_model`, `make_client`)
- Modify: `backend/tests/test_answer.py` (add one test; edit no existing one)

**Interfaces:**
- Consumes: `gateway.chat_kwargs(config) -> dict`, `gateway.make_chat_client(config)`, `answer.ChatConfig.base_url`, `.api_key_env`, `.json_mode`, `.reasoning_effort`
- Produces: `answer.ask_model(config, client, messages)` unchanged in name and signature

- [ ] **Step 1: Write the failing test**

```python
def test_the_answer_model_is_asked_for_a_json_object_not_a_schema():
    """The gateway does not offer json_schema, so the request must not send one."""
    client = FakeChatClient(reply(True, "المادة 25."))
    config = make_config()

    ask_model(config, client, [{"role": "user", "content": "سؤال"}])

    call = client.calls[0]
    assert call["response_format"] == {"type": "json_object"}
    assert "json_schema" not in call["response_format"]


def test_the_answer_model_is_asked_not_to_think():
    """Thinking is on by default on the gateway and would break the latency target."""
    client = FakeChatClient(reply(True, "المادة 25."))

    ask_model(make_config(), client, [{"role": "user", "content": "سؤال"}])

    assert client.calls[0]["extra_body"] == {"reasoning_effort": "none"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv\Scripts\python.exe -m pytest backend/tests/test_answer.py -k "json_object or not_to_think" -v`
Expected: FAIL — `response_format` is still the schema, and `extra_body` is absent

- [ ] **Step 3: Change the two call sites**

In `answer.py`, delete the `ANSWER_FORMAT` dictionary and its comment, and change `ask_model`:

```python
def ask_model(
    config: ChatConfig, client, messages: list[dict]
) -> tuple[str | None, object | None]:
    """Call the chat model once; returns its text and usage.

    The JSON mode and the thinking mode come from the gateway module, so the
    citation contract's strict parse is the guard and not the schema. The SDK's own
    timeout and retry settings have already been applied when this raises. The
    message names the model and the error type only: neither the prompt nor the
    API key is ever logged.
    """
    try:
        response = client.chat.completions.create(
            model=config.model,
            messages=messages,
            temperature=config.temperature,
            max_tokens=config.max_output_tokens,
            **gateway.chat_kwargs(config),
        )
    except Exception as exc:  # network, timeout, rate limit, provider error
        raise ModelUnavailable(
            f"the chat model {config.model} failed: {type(exc).__name__}"
        ) from exc

    if not response.choices:
        raise ModelUnavailable(f"the chat model {config.model} returned no choice")
    return response.choices[0].message.content, getattr(response, "usage", None)
```

and `make_client`:

```python
def make_client(config: ChatConfig):
    """The chat client for the configured gateway; the key comes from .env."""
    return gateway.make_chat_client(config)
```

with `from gateway import api_key` added to the imports and `import gateway` beside it.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `venv\Scripts\python.exe -m pytest backend/tests/test_answer.py -v`
Expected: PASS

- [ ] **Step 5: Run the whole suite and the answer eval**

Run: `venv\Scripts\python.exe -m pytest backend/tests/ -q`
Run: `venv\Scripts\python.exe eval\run_answer_eval.py`
Expected: PASS, and the eval score no lower than the baseline recorded in Task 4

- [ ] **Step 6: Update `prompt-log.md` and commit**

Add the Task 2 entry with the prompt sent to the sub-agent, then:

```bash
git add backend/scripts/answer.py backend/tests/test_answer.py prompt-log.md
git commit -m "feat: ask the gateway for a json object and no thinking"
```

---

### Task 3: The embedder moves to the gateway and the index is rebuilt

**Files:**
- Modify: `backend/scripts/embed_chunks.py` (`embed_chunks`, `make_client`)
- Modify: `backend/scripts/retrieve.py` (`embed_query`)
- Modify: `backend/tests/test_embed_chunks.py` (add one test; edit no existing one)
- Rebuild: `data/processed/index/ref-01.npz`, `ref-01.index.json` (git-ignored)

**Interfaces:**
- Consumes: `gateway.embed_kwargs(config) -> dict`, `gateway.make_embed_client(config)`
- Produces: `embed_chunks.embed_chunks(config, chunks, token_counts, client, ...)` unchanged in name and signature; `retrieve.embed_query(query, config, client, tokenizer=None)` unchanged

- [ ] **Step 1: Write the failing test**

```python
def test_the_embed_request_sends_no_dimensions_unless_the_config_asks():
    """A model that does not know the parameter may reject the whole request."""
    config = make_config()
    client = FakeEmbeddingClient(dimensions=config.dimensions)
    chunks = [Chunk(index=0, article_number=1, heading="المادة 1", text="نص")]

    embed_chunks(config, chunks, [3], client)

    assert "dimensions" not in client.calls[0]
    assert client.calls[0]["encoding_format"] == "float"


def test_the_embed_request_sends_the_dimensions_when_the_config_asks():
    config = make_config(send_dimensions=True)
    client = FakeEmbeddingClient(dimensions=config.dimensions)
    chunks = [Chunk(index=0, article_number=1, heading="المادة 1", text="نص")]

    embed_chunks(config, chunks, [3], client)

    assert client.calls[0]["dimensions"] == config.dimensions
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv\Scripts\python.exe -m pytest backend/tests/test_embed_chunks.py -k "dimensions" -v`
Expected: FAIL — `dimensions` is sent unconditionally

- [ ] **Step 3: Change the two call sites**

In `embed_chunks.py`, inside `embed_chunks`, replace the four keyword arguments with:

```python
        response = client.embeddings.create(
            model=config.model,
            input=[chunks[position].text for position in batch],
            **embed_kwargs(config),
        )
```

and `make_client`:

```python
def make_client(config: EmbeddingConfig):
    """The embedding client for the configured gateway; the key comes from .env."""
    return gateway.make_embed_client(config)
```

In `retrieve.py`, inside `embed_query`, replace the same four keyword arguments with:

```python
    response = client.embeddings.create(
        model=config.model,
        input=[normalized],
        **embed_kwargs(config),
    )
```

importing `embed_kwargs` from `embed_chunks` beside the existing names.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `venv\Scripts\python.exe -m pytest backend/tests/test_embed_chunks.py backend/tests/test_retrieve.py backend/tests/test_retrieve_hybrid.py -v`
Expected: PASS

- [ ] **Step 5: Rebuild the index and prove it matches the chunks**

Run: `venv\Scripts\python.exe backend\scripts\embed_chunks.py --source-id ref-01`
Run: `venv\Scripts\python.exe -c "import numpy as np, json; v=np.load(r'data/processed/index/ref-01.npz')['vectors']; print(v.shape); print(json.load(open(r'data/processed/index/ref-01.index.json'))['model'])"`
Expected: `(75, 1024)` and `local-embedding-model`

- [ ] **Step 6: Prove the new index is searchable**

Run: `venv\Scripts\python.exe backend\scripts\retrieve.py --source-id ref-01 --query "كم نسبة الحضور المطلوبة للحرمان" --k 5`
Expected: article 25 first, and `load_index` accepts the index without raising

- [ ] **Step 7: Update `prompt-log.md` and commit**

Add the Task 3 entry with the prompt sent to the sub-agent, then:

```bash
git add backend/scripts/embed_chunks.py backend/scripts/retrieve.py backend/tests/test_embed_chunks.py prompt-log.md
git commit -m "feat: embed through the gateway at 1024 dimensions"
```

---

### Task 4: The eval gates and the recorded baseline

**Files:**
- Create: `docs/eval-baseline.md`
- Modify: `prompt-log.md`

**Interfaces:**
- Consumes: the index from Task 3, the chat client from Task 2
- Produces: the numbers Task 5 is measured against

- [ ] **Step 1: Record the retrieval numbers**

Run: `venv\Scripts\python.exe eval\run_retrieval_eval.py`
Record the hit@1, hit@3 and hit@5 in `docs/eval-baseline.md` beside the previous
baseline (`hit@1 0.50`, `hit@3 0.80`, `hit@5 0.80`).

- [ ] **Step 2: Record the answer numbers**

Run: `venv\Scripts\python.exe eval\run_answer_eval.py`
Record the score beside the same table.

- [ ] **Step 3: Decide, and write the decision down**

If either number is lower than its baseline, the embedder is the suspect and not the
language, because the corpus did not change. Write the finding in
`docs/eval-baseline.md`: either "the gateway embedder holds the baseline" or the
measured drop, and stop before Task 5 until it is explained.

- [ ] **Step 4: Update `prompt-log.md` and commit**

```bash
git add docs/eval-baseline.md prompt-log.md
git commit -m "docs: the gateway embedder measured against the baseline"
```

---

### Task 5: LangChain replaces the transport

**Files:**
- Modify: `backend/scripts/gateway.py` (client construction only)
- Modify: `backend/scripts/answer.py` (`ask_model` body only)
- Modify: `backend/scripts/embed_chunks.py` (`embed_chunks` body only)
- Modify: `backend/scripts/retrieve.py` (`embed_query` body only)
- Modify: `requirements.txt` (add `langchain-core`, `langchain-openai`)
- Edit no test file

**Interfaces:**
- Consumes: everything from Tasks 1–3
- Produces: every public name and signature unchanged, which is the point

- [ ] **Step 1: Install the two packages**

Run: `venv\Scripts\python.exe -m pip install langchain-core langchain-openai`
Add both to `requirements.txt`.

- [ ] **Step 2: Change `gateway.make_chat_client` to build a LangChain chat model**

```python
def make_chat_client(config, env_file: Path = DEFAULT_ENV_FILE):
    """The chat model for the configured gateway, as a LangChain model."""
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        api_key=api_key(config, env_file),
        base_url=config.base_url,
        model=config.model,
        temperature=config.temperature,
        max_tokens=config.max_output_tokens,
        timeout=config.timeout_seconds,
        max_retries=config.max_retries,
        model_kwargs=chat_kwargs(config),
    )
```

- [ ] **Step 3: Change `gateway.make_embed_client` to build a LangChain embedder**

```python
def make_embed_client(config, env_file: Path = DEFAULT_ENV_FILE):
    """The embedder for the configured gateway, as a LangChain embedder."""
    from langchain_openai import OpenAIEmbeddings

    kwargs = {}
    if config.send_dimensions:
        kwargs["dimensions"] = config.dimensions
    return OpenAIEmbeddings(
        api_key=api_key(config, env_file),
        base_url=config.base_url,
        model=config.model,
        **kwargs,
    )
```

- [ ] **Step 4: Change `answer.ask_model` to invoke the model**

```python
def ask_model(
    config: ChatConfig, client, messages: list[dict]
) -> tuple[str | None, object | None]:
    """Call the chat model once; returns its text and usage.

    The JSON mode and the thinking mode come from the gateway module. The model's
    own retry and timeout settings have already been applied when this raises. The
    message names the model and the error type only: neither the prompt nor the
    API key is ever logged.
    """
    try:
        response = client.invoke(messages)
    except Exception as exc:  # network, timeout, rate limit, provider error
        raise ModelUnavailable(
            f"the chat model {config.model} failed: {type(exc).__name__}"
        ) from exc

    content = getattr(response, "content", None)
    if content is None:
        raise ModelUnavailable(f"the chat model {config.model} returned no text")
    return content, getattr(response, "usage_metadata", None)
```

- [ ] **Step 5: Change `embed_chunks.embed_chunks` to embed documents**

```python
        vectors[position] = vector
```

becomes, inside the batch loop, replacing the SDK call with:

```python
        embedded = client.embed_documents(
            [chunks[position].text for position in batch]
        )
        if len(embedded) != len(batch):
            raise ValueError(
                f"{config.model} returned {len(embedded)} vectors for "
                f"{len(batch)} inputs"
            )
```

with the per-vector length check kept exactly as it is:

```python
        for item, position in zip(embedded, batch):
            vector = np.asarray(item, dtype=np.float32)
            if vector.shape != (config.dimensions,):
                raise ValueError(
                    f"{config.model} returned {vector.size} dimensions for "
                    f"{chunks[position].label}; config expects {config.dimensions}"
                )
            vectors[position] = vector
```

- [ ] **Step 6: Change `retrieve.embed_query` to embed the query**

```python
    vector = np.asarray(client.embed_query(normalized), dtype=np.float32)
```

replacing the SDK call and its `response.data` handling, and keeping the length check:

```python
    if vector.shape != (config.dimensions,):
        raise ValueError(
            f"{config.model} returned {vector.size} dimensions; config expects "
            f"{config.dimensions}"
        )
```

- [ ] **Step 7: Update the fakes in the tests' style, without weakening an assertion**

The existing fakes expose `.embeddings.create`; LangChain clients expose
`embed_documents` and `embed_query`. Each fake gains the second shape and keeps the
first, so no assertion changes.

- [ ] **Step 8: Run the whole suite — this is the gate**

Run: `venv\Scripts\python.exe -m pytest backend/tests/ -q`
Expected: PASS, and `git diff --stat backend/tests/` shows **no test file edited except
the fakes**

- [ ] **Step 9: Run both evals again**

Run: `venv\Scripts\python.exe eval\run_retrieval_eval.py`
Run: `venv\Scripts\python.exe eval\run_answer_eval.py`
Expected: no lower than `docs/eval-baseline.md`

- [ ] **Step 10: Update `prompt-log.md` and commit**

```bash
git add backend/scripts/gateway.py backend/scripts/answer.py backend/scripts/embed_chunks.py backend/scripts/retrieve.py backend/tests/ requirements.txt prompt-log.md
git commit -m "refactor: make every model call through LangChain"
```
