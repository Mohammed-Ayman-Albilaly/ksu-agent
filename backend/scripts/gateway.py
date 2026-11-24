"""One place that knows the provider: base URL, key name, JSON and thinking mode.

Every script that calls a model goes through this module, so no script names a vendor and
swapping the gateway is a change to two TOML files. The key is read from the environment
variable the config names, so the project and a teammate hold different keys without a code
change, and its value is never logged, printed or returned.

The transport is LangChain: ``make_chat_client`` builds a ``ChatOpenAI`` and
``make_embed_client`` an ``OpenAIEmbeddings``, so a call is ``invoke``,
``embed_documents`` or ``embed_query`` rather than a hand-rolled SDK call. LangChain changes
how a call is made and not what is guaranteed: the guards in the scripts that use this module
are untouched.

This module must not import ``embed_chunks``: ``embed_chunks`` imports this module, so that
would be a circular import. ``REPO_ROOT`` comes from ``fetch_sources`` instead.
"""

from __future__ import annotations

import os
from pathlib import Path

from fetch_sources import REPO_ROOT

DEFAULT_ENV_FILE = REPO_ROOT / ".env"
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_MAX_RETRIES = 3

# Used only when the caller names no key: the legacy ``api_key(env_file)`` call shape kept
# by embed_chunks (and the tests that import it from there) names no config.
DEFAULT_ENV_NAME = "OPENAI_API_KEY"


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


def api_key(config=None, env_file: Path = DEFAULT_ENV_FILE) -> str:
    """The key named by the config, from .env then the environment.

    ``config`` is a config object carrying ``api_key_env``. For the call shape kept by
    ``embed_chunks`` — ``api_key(env_file)``, where no config is named — the first
    argument may be the env file itself, and ``DEFAULT_ENV_NAME`` is read.

    The value is never returned to a log or an error message: only the variable's name
    appears in the message.
    """
    if isinstance(config, (str, Path)):
        env_file, config = Path(config), None
    name = (getattr(config, "api_key_env", "") or DEFAULT_ENV_NAME).strip()
    value = (load_env_file(env_file).get(name) or os.environ.get(name, "")).strip()
    if not value:
        raise RuntimeError(
            f"{name} is not set; add it to {Path(env_file).name} "
            f"(git-ignored, see .env.example) or export it"
        )
    return value


def make_chat_client(
    config, env_file: Path = DEFAULT_ENV_FILE, key: str | None = None
):
    """The chat model for the configured gateway, as a LangChain chat model.

    ``key`` lets a caller that already read the key pass it in, so the key is read
    once and the caller's own seam stays the one that fails on a missing key.

    The client is built once and shared (``app/main.get_client``), so only what
    belongs to the connection is set here: the key, the base URL, the timeout and the
    retry count. What belongs to one call — the pinned model, the sampling settings
    and the JSON and thinking modes from ``chat_request`` — is sent with the call, so
    one shared client serves the answer and the classifier with their own settings.
    """
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=config.model,
        api_key=key or api_key(config, env_file),
        base_url=config.base_url,
        timeout=config.timeout_seconds,
        max_retries=config.max_retries,
    )


def make_embed_client(
    config, env_file: Path = DEFAULT_ENV_FILE, key: str | None = None
):
    """The embedder for the configured gateway, as a LangChain embedder.

    ``check_embedding_ctx_length`` is off on purpose: this project's own guard counts
    every chunk with the configured tokenizer and refuses an over-long one, so the
    embedder must not quietly split a text and average the pieces. It sends each text
    whole, as the SDK call did, and the caller checks the vector's length.
    """
    from langchain_openai import OpenAIEmbeddings

    return OpenAIEmbeddings(
        model=config.model,
        api_key=key or api_key(config, env_file),
        base_url=config.base_url,
        check_embedding_ctx_length=False,
        timeout=DEFAULT_TIMEOUT_SECONDS,
        max_retries=DEFAULT_MAX_RETRIES,
    )


def chat_request(config, *, truncated_reply_ok: bool) -> dict:
    """The request kwargs for one chat call, the JSON-mode placement included.

    LangChain takes a structured-output path whenever the request carries a
    top-level ``response_format``, and that path raises on a reply cut off at the
    output limit instead of returning the truncated text. An answer needs the
    truncated text so ``parse_model_answer`` rejects it and the fallback runs, so its
    JSON mode travels in ``extra_body``, which the SDK merges into the body: the
    model receives the same request. A routing decision that is cut off is
    ``regulation`` either way, so it keeps the top-level form.
    """
    if truncated_reply_ok:
        body: dict = {"response_format": {"type": config.json_mode}}
        if config.reasoning_effort:
            body["reasoning_effort"] = config.reasoning_effort
        return {"extra_body": body}

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
