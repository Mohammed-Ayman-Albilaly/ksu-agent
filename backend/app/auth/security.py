"""Password hashing, session tokens and verification codes (standard library only).

Passwords are hashed with scrypt and a random salt per user. Session tokens and
verification codes are random; only their SHA-256 digests are stored, so a copy of
the database does not hand out live sessions or codes.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32
SALT_BYTES = 16


def hash_password(password: str) -> str:
    """scrypt$n$r$p$salt$hash, all needed to check the password later."""
    salt = secrets.token_bytes(SALT_BYTES)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${derived.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """True when `password` matches `stored`; compared in constant time."""
    try:
        scheme, n, r, p, salt_hex, hash_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = bytes.fromhex(hash_hex)
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(derived, expected)


# Checked against when the email is unknown, so a wrong email and a wrong
# password take the same time and the response does not reveal which accounts exist.
DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(16))


def new_session_token() -> str:
    """A random, URL-safe session token for the cookie."""
    return secrets.token_urlsafe(32)


def digest(value: str) -> str:
    """SHA-256 hex digest; what the database stores for tokens and codes."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def new_code(length: int) -> str:
    """A random numeric verification code of `length` digits."""
    return "".join(str(secrets.randbelow(10)) for _ in range(length))


def code_digest(email: str, code: str) -> str:
    """Digest of a code tied to its email, so one stored digest fits one address."""
    return digest(f"{email}:{code}")


def same_digest(left: str, right: str) -> bool:
    """Constant-time comparison of two hex digests."""
    return hmac.compare_digest(left, right)
