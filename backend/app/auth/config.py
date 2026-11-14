"""Auth settings from backend/config/auth.toml; SMTP secrets from .env."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from embed_chunks import DEFAULT_ENV_FILE, load_env_file
from fetch_sources import REPO_ROOT

DEFAULT_CONFIG = REPO_ROOT / "backend" / "config" / "auth.toml"


@dataclass(frozen=True)
class AuthConfig:
    """The [auth] table of auth.toml; see that file for what each value means."""

    email_verification: bool
    allowed_email_domain: str
    db_path: Path
    session_days: int
    cookie_name: str
    cookie_secure: bool
    otp_length: int
    otp_ttl_minutes: int
    otp_max_attempts: int
    otp_resend_seconds: int


def load_config(config_path: Path = DEFAULT_CONFIG) -> AuthConfig:
    """Read and check auth.toml; a missing or wrong value stops the start-up."""
    with open(config_path, "rb") as fh:
        section = tomllib.load(fh)["auth"]

    db_path = Path(section["db_path"])
    if not db_path.is_absolute():
        db_path = REPO_ROOT / db_path

    config = AuthConfig(
        email_verification=bool(section["email_verification"]),
        allowed_email_domain=str(section["allowed_email_domain"]).strip().lower(),
        db_path=db_path,
        session_days=int(section["session_days"]),
        cookie_name=str(section["cookie_name"]),
        cookie_secure=bool(section["cookie_secure"]),
        otp_length=int(section["otp_length"]),
        otp_ttl_minutes=int(section["otp_ttl_minutes"]),
        otp_max_attempts=int(section["otp_max_attempts"]),
        otp_resend_seconds=int(section["otp_resend_seconds"]),
    )
    if not config.allowed_email_domain:
        raise ValueError("auth.toml: allowed_email_domain must not be empty")
    if config.session_days < 1 or not 4 <= config.otp_length <= 10:
        raise ValueError("auth.toml: session_days >= 1 and 4 <= otp_length <= 10")
    return config


@dataclass(frozen=True)
class SmtpSettings:
    """The mail account that sends verification codes. Never logged."""

    host: str
    port: int
    username: str
    password: str
    sender: str


def load_smtp_settings(env_file: Path = DEFAULT_ENV_FILE) -> SmtpSettings:
    """SMTP_* from .env, else from the environment. Needed only when verifying."""
    file_values = load_env_file(env_file)

    def get(name: str) -> str:
        return (file_values.get(name) or os.environ.get(name, "")).strip()

    host, sender = get("SMTP_HOST"), get("SMTP_FROM")
    if not host or not sender:
        raise RuntimeError(
            "email_verification is on but SMTP_HOST or SMTP_FROM is not set; "
            "add the SMTP_* values to .env"
        )
    return SmtpSettings(
        host=host,
        port=int(get("SMTP_PORT") or 587),
        username=get("SMTP_USERNAME"),
        password=get("SMTP_PASSWORD"),
        sender=sender,
    )
