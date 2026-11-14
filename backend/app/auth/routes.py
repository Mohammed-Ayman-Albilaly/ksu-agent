"""HTTP routes under /auth, as listed in docs/api-contract.md ("Planned").

POST /auth/register  {full_name, email, password, lang}
    201 {user} + session cookie            (email_verification off)
    201 {user, verification_required: true} (email_verification on; no cookie yet)
    409 {error: "email_taken"}
    422 {error: "validation", fields: {field: code}}
    503 {error: "email_unavailable"}       (code could not be sent)
POST /auth/login     {email, password}
    200 {user} + cookie · 401 {error: "invalid_credentials"}
    403 {error: "email_not_verified"} (only when email_verification is on)
POST /auth/logout    204, cookie cleared
GET  /auth/me        200 {user} · 401 {error: "unauthenticated"}

Email verification (built, switched off by auth.toml until SMTP is ready):
POST /auth/verify    {email, code} -> 200 {user} + cookie
    400 {error: "invalid_code" | "code_expired"} · 429 {error: "too_many_attempts"}
POST /auth/resend    {email} -> 204 · 429 {error: "resend_too_soon", retry_after}
Both answer 404 {error: "verification_disabled"} while it is off.

Errors are short codes the front end translates, never sentences. Emails,
passwords, codes and tokens are never logged.
"""

from __future__ import annotations

import logging
import re
import time
from functools import lru_cache

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from app.auth import security
from app.auth.config import AuthConfig, load_config, load_smtp_settings
from app.auth.mailer import Mailer, SmtpMailer
from app.auth.store import AuthStore, User

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

NAME_MIN, NAME_MAX = 2, 60
PASSWORD_MIN, PASSWORD_MAX = 8, 128
EMAIL_MAX = 254
LETTER = re.compile(r"[A-Za-z؀-ۿ]")
DIGIT = re.compile(r"[0-9]")


# --- dependencies (module functions, so tests can replace them) -----------


def clock() -> int:
    """Seconds since the epoch; replaced in tests to move time forward."""
    return int(time.time())


@lru_cache
def get_config() -> AuthConfig:
    return load_config()


@lru_cache
def get_store() -> AuthStore:
    return AuthStore(get_config().db_path)


@lru_cache
def get_mailer() -> Mailer:
    return SmtpMailer(load_smtp_settings())


# --- request bodies ----------------------------------------------------------
# Every field defaults to "" so that a missing field is reported as a field code
# in the 422 body, the same way as an empty one.


class RegisterRequest(BaseModel):
    full_name: str = ""
    email: str = ""
    password: str = ""
    lang: str = "ar"


class LoginRequest(BaseModel):
    email: str = ""
    password: str = ""


class VerifyRequest(BaseModel):
    email: str = ""
    code: str = ""


class ResendRequest(BaseModel):
    email: str = ""


# --- helpers -----------------------------------------------------------------


def error(status: int, code: str, **extra) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": code, **extra})


def validation_error(fields: dict[str, str]) -> JSONResponse:
    return error(422, "validation", fields=fields)


def normalize_email(value: str) -> str:
    return value.strip().lower()


def email_problem(email: str, config: AuthConfig) -> str | None:
    if not email:
        return "email_required"
    local, _, domain = email.rpartition("@")
    if (
        len(email) > EMAIL_MAX
        or not local
        or any(ch.isspace() for ch in email)
        or "@" in local
        or domain != config.allowed_email_domain
    ):
        return "email_domain"
    return None


def password_problem(password: str) -> str | None:
    if not password:
        return "password_required"
    if len(password) < PASSWORD_MIN:
        return "password_too_short"
    if len(password) > PASSWORD_MAX:
        return "password_too_long"
    if not LETTER.search(password) or not DIGIT.search(password):
        return "password_weak"
    return None


def start_session(response: Response, user: User, config: AuthConfig) -> None:
    """Create a server-side session and set its token as an httpOnly cookie."""
    token = security.new_session_token()
    lifetime = config.session_days * 86_400
    get_store().create_session(security.digest(token), user.id, clock() + lifetime)
    response.set_cookie(
        key=config.cookie_name,
        value=token,
        max_age=lifetime,
        httponly=True,
        secure=config.cookie_secure,
        samesite="lax",
        path="/",
    )


def current_user(request: Request) -> User | None:
    """The signed-in user for this request's cookie, or None.

    Ready for POST /chat to require sign-in later (contract: 401 when not signed in).
    """
    config = get_config()
    token = request.cookies.get(config.cookie_name)
    if not token:
        return None
    return get_store().session_user(security.digest(token), clock())


def send_new_code(user: User, config: AuthConfig) -> bool:
    """Create, store and email a fresh code. False when the email could not be sent."""
    code = security.new_code(config.otp_length)
    now = clock()
    get_store().save_code(
        user.email,
        security.code_digest(user.email, code),
        expires_at=now + config.otp_ttl_minutes * 60,
        sent_at=now,
    )
    try:
        get_mailer().send_code(user.email, code, user.lang, config.otp_ttl_minutes)
    except Exception as exc:  # SMTP down, wrong password, bad settings
        LOGGER.error("verification email failed: %s", type(exc).__name__)
        get_store().delete_code(user.email)
        return False
    return True


# --- routes ------------------------------------------------------------------


@router.post("/register", status_code=201)
def register(body: RegisterRequest):
    config = get_config()
    full_name = " ".join(body.full_name.split())
    email = normalize_email(body.email)
    lang = "en" if body.lang == "en" else "ar"

    fields: dict[str, str] = {}
    if not full_name:
        fields["full_name"] = "name_required"
    elif not NAME_MIN <= len(full_name) <= NAME_MAX:
        fields["full_name"] = "name_length"
    if problem := email_problem(email, config):
        fields["email"] = problem
    if problem := password_problem(body.password):
        fields["password"] = problem
    if fields:
        return validation_error(fields)

    user = get_store().create_user(
        full_name=full_name,
        email=email,
        password_hash=security.hash_password(body.password),
        lang=lang,
        email_verified=not config.email_verification,
    )
    if user is None:
        return error(409, "email_taken")

    if config.email_verification:
        if not send_new_code(user, config):
            # Undo the sign-up so the student can simply try again.
            get_store().delete_user(user.id)
            return error(503, "email_unavailable")
        LOGGER.info("registered an account; verification code sent")
        return JSONResponse(
            status_code=201,
            content={"user": user.public(), "verification_required": True},
        )

    LOGGER.info("registered an account")
    response = JSONResponse(status_code=201, content={"user": user.public()})
    start_session(response, user, config)
    return response


@router.post("/login")
def login(body: LoginRequest):
    config = get_config()
    email = normalize_email(body.email)

    fields: dict[str, str] = {}
    if problem := email_problem(email, config):
        fields["email"] = problem
    if not body.password:
        fields["password"] = "password_required"
    if fields:
        return validation_error(fields)

    user = get_store().get_user_by_email(email)
    if user is None:
        security.verify_password(body.password, security.DUMMY_PASSWORD_HASH)
        return error(401, "invalid_credentials")
    if not security.verify_password(body.password, user.password_hash):
        return error(401, "invalid_credentials")
    if config.email_verification and not user.email_verified:
        return error(403, "email_not_verified")

    response = JSONResponse(status_code=200, content={"user": user.public()})
    start_session(response, user, config)
    return response


@router.post("/logout", status_code=204)
def logout(request: Request):
    config = get_config()
    token = request.cookies.get(config.cookie_name)
    if token:
        get_store().delete_session(security.digest(token))
    response = Response(status_code=204)
    response.delete_cookie(
        key=config.cookie_name,
        path="/",
        httponly=True,
        secure=config.cookie_secure,
        samesite="lax",
    )
    return response


@router.get("/me")
def me(request: Request):
    user = current_user(request)
    if user is None:
        return error(401, "unauthenticated")
    return {"user": user.public()}


@router.post("/verify")
def verify(body: VerifyRequest):
    config = get_config()
    if not config.email_verification:
        return error(404, "verification_disabled")

    email = normalize_email(body.email)
    code = body.code.strip()
    fields: dict[str, str] = {}
    if problem := email_problem(email, config):
        fields["email"] = problem
    if not code:
        fields["code"] = "code_required"
    elif not (code.isascii() and code.isdigit() and len(code) == config.otp_length):
        fields["code"] = "code_format"
    if fields:
        return validation_error(fields)

    store = get_store()
    user = store.get_user_by_email(email)
    pending = store.get_code(email)
    if user is None or pending is None:
        return error(400, "invalid_code")
    if pending.expires_at <= clock():
        store.delete_code(email)
        return error(400, "code_expired")
    if pending.attempts >= config.otp_max_attempts:
        store.delete_code(email)
        return error(429, "too_many_attempts")
    if not security.same_digest(pending.code_hash, security.code_digest(email, code)):
        store.add_attempt(email)
        if pending.attempts + 1 >= config.otp_max_attempts:
            store.delete_code(email)
            return error(429, "too_many_attempts")
        return error(400, "invalid_code")

    store.delete_code(email)
    store.mark_verified(user.id)
    LOGGER.info("verified an account email")
    response = JSONResponse(status_code=200, content={"user": user.public()})
    start_session(response, user, config)
    return response


@router.post("/resend", status_code=204)
def resend(body: ResendRequest):
    config = get_config()
    if not config.email_verification:
        return error(404, "verification_disabled")

    email = normalize_email(body.email)
    if problem := email_problem(email, config):
        return validation_error({"email": problem})

    store = get_store()
    user = store.get_user_by_email(email)
    # Unknown or already verified: answer the same as success, so the endpoint
    # cannot be used to find out which addresses have accounts.
    if user is None or user.email_verified:
        return Response(status_code=204)

    pending = store.get_code(email)
    if pending is not None:
        wait = pending.sent_at + config.otp_resend_seconds - clock()
        if wait > 0:
            return error(429, "resend_too_soon", retry_after=wait)

    if not send_new_code(user, config):
        return error(503, "email_unavailable")
    return Response(status_code=204)
