"""One place that knows the provider: base URL, key name, JSON and thinking mode.

Every script that calls a model goes through this module, so no script names a vendor and
swapping the gateway is a change to two TOML files. The key is read from the environment
variable the config names, so the project and a teammate hold different keys without a code
change, and its value is never logged, printed or returned.

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
    """The chat client for the configured gateway.

    ``key`` lets a caller that already read the key pass it in, so the key is read
    once and the caller's own seam stays the one that fails on a missing key.
    """
    from openai import OpenAI

    return OpenAI(
        api_key=key or api_key(config, env_file),
        base_url=config.base_url,
        timeout=config.timeout_seconds,
        max_retries=config.max_retries,
    )


def make_embed_client(
    config, env_file: Path = DEFAULT_ENV_FILE, key: str | None = None
):
    """The embedding client for the configured gateway."""
    from openai import OpenAI

    return OpenAI(
        api_key=key or api_key(config, env_file),
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
