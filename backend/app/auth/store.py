"""SQLite storage for users, sessions and verification codes.

One small file (auth.toml: db_path, under the git-ignored data/private/). It uses
only the standard library, so no database server is needed during development; the
same three tables can move to PostgreSQL later without changing the routes.
"""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id             TEXT PRIMARY KEY,
    full_name      TEXT NOT NULL,
    email          TEXT NOT NULL UNIQUE,
    password_hash  TEXT NOT NULL,
    lang           TEXT NOT NULL,
    email_verified INTEGER NOT NULL,
    created_at     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);
CREATE TABLE IF NOT EXISTS email_codes (
    email      TEXT PRIMARY KEY,
    code_hash  TEXT NOT NULL,
    expires_at INTEGER NOT NULL,
    sent_at    INTEGER NOT NULL,
    attempts   INTEGER NOT NULL DEFAULT 0
);
"""


@dataclass(frozen=True)
class User:
    """A stored account. `password_hash` never leaves the backend."""

    id: str
    full_name: str
    email: str
    password_hash: str
    lang: str
    email_verified: bool

    def public(self) -> dict[str, str]:
        """The `user` object of the API: id, full_name, email."""
        return {"id": self.id, "full_name": self.full_name, "email": self.email}


@dataclass(frozen=True)
class EmailCode:
    """The pending verification code for one address (its digest only)."""

    email: str
    code_hash: str
    expires_at: int
    sent_at: int
    attempts: int


def _user(row: sqlite3.Row | None) -> User | None:
    if row is None:
        return None
    return User(
        id=row["id"],
        full_name=row["full_name"],
        email=row["email"],
        password_hash=row["password_hash"],
        lang=row["lang"],
        email_verified=bool(row["email_verified"]),
    )


class AuthStore:
    """All reads and writes of the auth tables. Each call opens its own connection."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn, conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    # --- users -----------------------------------------------------------

    def create_user(
        self,
        *,
        full_name: str,
        email: str,
        password_hash: str,
        lang: str,
        email_verified: bool,
    ) -> User | None:
        """The new user, or None when the email is already registered."""
        user = User(
            id=uuid.uuid4().hex,
            full_name=full_name,
            email=email,
            password_hash=password_hash,
            lang=lang,
            email_verified=email_verified,
        )
        try:
            with closing(self._connect()) as conn, conn:
                conn.execute(
                    "INSERT INTO users (id, full_name, email, password_hash, lang,"
                    " email_verified, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        user.id,
                        user.full_name,
                        user.email,
                        user.password_hash,
                        user.lang,
                        int(user.email_verified),
                        datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    ),
                )
        except sqlite3.IntegrityError:
            return None
        return user

    def get_user_by_email(self, email: str) -> User | None:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return _user(row)

    def delete_user(self, user_id: str) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))

    def mark_verified(self, user_id: str) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("UPDATE users SET email_verified = 1 WHERE id = ?", (user_id,))

    # --- sessions --------------------------------------------------------

    def create_session(self, token_hash: str, user_id: str, expires_at: int) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                (token_hash, user_id, expires_at),
            )

    def session_user(self, token_hash: str, now: int) -> User | None:
        """The signed-in user for a session, or None; expired sessions are removed."""
        with closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
            row = conn.execute(
                "SELECT users.* FROM sessions JOIN users ON users.id = sessions.user_id"
                " WHERE sessions.token_hash = ?",
                (token_hash,),
            ).fetchone()
        return _user(row)

    def delete_session(self, token_hash: str) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))

    # --- verification codes ---------------------------------------------

    def save_code(self, email: str, code_hash: str, expires_at: int, sent_at: int) -> None:
        """Store the code for `email`, replacing any earlier one and its attempts."""
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO email_codes (email, code_hash, expires_at, sent_at, attempts)"
                " VALUES (?, ?, ?, ?, 0) ON CONFLICT(email) DO UPDATE SET"
                " code_hash = excluded.code_hash, expires_at = excluded.expires_at,"
                " sent_at = excluded.sent_at, attempts = 0",
                (email, code_hash, expires_at, sent_at),
            )

    def get_code(self, email: str) -> EmailCode | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM email_codes WHERE email = ?", (email,)
            ).fetchone()
        if row is None:
            return None
        return EmailCode(
            email=row["email"],
            code_hash=row["code_hash"],
            expires_at=row["expires_at"],
            sent_at=row["sent_at"],
            attempts=row["attempts"],
        )

    def add_attempt(self, email: str) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "UPDATE email_codes SET attempts = attempts + 1 WHERE email = ?", (email,)
            )

    def delete_code(self, email: str) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM email_codes WHERE email = ?", (email,))
