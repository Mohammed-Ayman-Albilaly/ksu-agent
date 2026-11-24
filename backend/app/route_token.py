"""The token that binds a reasoning answer to the route its question was given.

`/chat` decides a route — the regex first, the classifier when the regex does not know the
question — and a reasoning route is answered by `/chat/with-data` once the student approves the
values it would send. That second request used to decide the kind again, with the regex alone, so a
question only the classifier recognised was routed by `/chat` and then refused by `/chat/with-data`.

This module closes that gap. A reasoning reply carries a `route_token`: an HMAC-SHA256, under a
server secret, over the user id, the SHA-256 of the question, the kind, the tools and the issue time.
`/chat/with-data` verifies it and uses the kind and the tools it names instead of guessing again.

The token names no student data: the question travels as a hash, and the browser only ever holds the
kind and the tool names it already shows. It is base64url(payload).base64url(mac), lives fifteen
minutes, and is never logged.

The secret is KSU_ROUTE_SECRET from .env, else the environment, read the way the other secrets are.
Without it the process makes a random one and says so: route tokens then do not survive a restart.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Sequence

from embed_chunks import DEFAULT_ENV_FILE, load_env_file

from app.tools import REASONING_TOOLS

LOGGER = logging.getLogger(__name__)

SECRET_ENV = "KSU_ROUTE_SECRET"

# A student approves the values in the same minute they read them, so fifteen minutes is far
# longer than the flow needs and far shorter than a token is useful to anyone else.
TOKEN_LIFETIME_SECONDS = 15 * 60

# The payload's fields: the user, the question's hash, the kind, the tools, and the issue time.
_FIELDS = ("u", "m", "k", "t", "iat")


class RouteTokenError(Exception):
    """A token that does not bind this request to this student and this question."""

    code = "route_invalid"


@dataclass(frozen=True)
class RouteClaim:
    """What a verified token says the question was routed to."""

    kind: str
    tools: tuple[str, ...]


@lru_cache
def get_secret(env_file: Path = DEFAULT_ENV_FILE) -> bytes:
    """The HMAC key: KSU_ROUTE_SECRET from .env, else the environment, else random.

    The value is never logged, and the warning for a missing one names no value: it only says
    that the tokens of this process do not survive a restart.
    """
    value = (load_env_file(env_file).get(SECRET_ENV) or os.environ.get(SECRET_ENV, "")).strip()

    if value:
        return value.encode("utf-8")

    LOGGER.warning(
        "%s is not set; route tokens are signed with a secret for this process only, "
        "so they do not survive a restart",
        SECRET_ENV,
    )
    return secrets.token_bytes(32)


def issue(
    *,
    user_id: str,
    message: str,
    kind: str,
    tools: Sequence[str],
    issued_at: int | None = None,
) -> str:
    """The token for one reasoning route: base64url(payload).base64url(mac)."""
    payload = _encode(
        {
            "u": user_id,
            "m": _message_digest(message),
            "k": kind,
            "t": list(tools),
            "iat": int(time.time()) if issued_at is None else issued_at,
        }
    )

    return f"{_b64encode(payload)}.{_b64encode(_mac(payload))}"


def verify(
    token: str, *, user_id: str, message: str, now: int | None = None
) -> RouteClaim:
    """The route `token` binds this student and this question to, or RouteTokenError.

    Checked in this order: the signature, the expiry, the student, the question. A token that
    fails any of them is refused before anything is computed from it.
    """
    segments = token.split(".")

    if len(segments) != 2:
        raise RouteTokenError()

    payload_segment, mac_segment = segments

    try:
        payload, mac = _b64decode(payload_segment), _b64decode(mac_segment)
    except (ValueError, TypeError):
        raise RouteTokenError() from None

    if not hmac.compare_digest(mac, _mac(payload)):
        raise RouteTokenError()

    try:
        claim = json.loads(payload)
    except ValueError:
        raise RouteTokenError() from None

    if not isinstance(claim, dict) or set(claim) != set(_FIELDS):
        raise RouteTokenError()

    issued_at = claim["iat"]

    if not isinstance(issued_at, int):
        raise RouteTokenError()

    current = int(time.time()) if now is None else now

    if current - issued_at > TOKEN_LIFETIME_SECONDS:
        raise RouteTokenError()

    if claim["u"] != user_id:
        raise RouteTokenError()

    if claim["m"] != _message_digest(message):
        raise RouteTokenError()

    # The kind and the tools are what the answer is computed from, so they are checked to be
    # a kind this backend computes and the tools it reads, never a value a client could choose.
    kind, tools = claim["k"], claim["t"]

    if not isinstance(kind, str) or kind not in REASONING_TOOLS:
        raise RouteTokenError()

    if tools != list(REASONING_TOOLS[kind]):
        raise RouteTokenError()

    return RouteClaim(kind=kind, tools=tuple(tools))


def _message_digest(message: str) -> str:
    """The question as a hex digest: the token carries no text of it."""
    return hashlib.sha256(message.encode("utf-8")).hexdigest()


def _encode(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _mac(payload: bytes) -> bytes:
    return hmac.new(get_secret(), payload, hashlib.sha256).digest()


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(segment: str) -> bytes:
    """Decode one base64url segment, refusing an encoding that is not canonical.

    Python's decoder ignores the padding bits, so "AA", "AB" and "AP" all decode to
    b"\\x00": a token whose last character was changed could still verify, and it did
    for about one key in four. Re-encoding and comparing refuses that, so a changed
    character is refused every time and not one run in four.
    """
    if not isinstance(segment, str):
        raise TypeError("not text")

    try:
        value = base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))
    except (ValueError, TypeError):
        raise RouteTokenError() from None

    if _b64encode(value) != segment.rstrip("="):
        raise RouteTokenError()

    return value
