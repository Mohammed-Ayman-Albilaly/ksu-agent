"""Tests for /auth/* — a temporary SQLite file and a fake mailer, so no network.

Covers the contract in docs/api-contract.md (register, login, logout, me, cookie
session, short error codes) with email verification off, which is the shipped
setting, and the one-time-code flow with it switched on.
"""

import dataclasses
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app import main
from app.auth import config as auth_config
from app.auth import routes
from app.auth.store import AuthStore

EMAIL = "444100001@student.ksu.edu.sa"
PASSWORD = "Secret123"
NAME = "Ahmed Alqahtani"


class FakeMailer:
    """Records codes instead of sending them; can be told to fail."""

    def __init__(self):
        self.sent: list[dict] = []
        self.fail = False

    def send_code(self, to, code, lang, minutes):
        if self.fail:
            raise OSError("smtp down")
        self.sent.append({"to": to, "code": code, "lang": lang, "minutes": minutes})

    @property
    def last_code(self):
        return self.sent[-1]["code"]


@pytest.fixture
def auth(tmp_path, monkeypatch):
    """make(verification=False) -> (TestClient, mailer, store, clock dict)."""

    def make(verification=False):
        config = dataclasses.replace(
            auth_config.load_config(),
            email_verification=verification,
            db_path=tmp_path / "auth.sqlite3",
        )
        store = AuthStore(config.db_path)
        mailer = FakeMailer()
        now = {"t": 1_800_000_000}

        monkeypatch.setattr(routes, "get_config", lambda: config)
        monkeypatch.setattr(routes, "get_store", lambda: store)
        monkeypatch.setattr(routes, "get_mailer", lambda: mailer)
        monkeypatch.setattr(routes, "clock", lambda: now["t"])
        return TestClient(main.app), mailer, store, now

    return make


def register(client, **overrides):
    body = {"full_name": NAME, "email": EMAIL, "password": PASSWORD, "lang": "ar"}
    body.update(overrides)
    return client.post("/auth/register", json=body)


# --- shipped behaviour: email verification off -----------------------------


def test_shipped_config_has_verification_off():
    assert auth_config.load_config().email_verification is False


def test_register_signs_in_and_me_returns_the_user(auth):
    client, mailer, _store, _now = auth()

    response = register(client)

    assert response.status_code == 201
    user = response.json()["user"]
    assert set(user) == {"id", "full_name", "email"}
    assert user["email"] == EMAIL and user["full_name"] == NAME
    assert "verification_required" not in response.json()
    assert mailer.sent == []

    cookie = response.headers["set-cookie"].lower()
    assert "ksu_session=" in cookie and "httponly" in cookie and "samesite=lax" in cookie

    me = client.get("/auth/me")
    assert me.status_code == 200 and me.json() == {"user": user}


def test_register_normalises_email_and_name(auth):
    client, *_ = auth()
    response = register(client, email="  444100001@Student.KSU.edu.sa ", full_name="  Ahmed   Ali  ")
    assert response.status_code == 201
    assert response.json()["user"]["email"] == EMAIL
    assert response.json()["user"]["full_name"] == "Ahmed Ali"


def test_duplicate_email_is_409(auth):
    client, *_ = auth()
    register(client)
    client.cookies.clear()
    response = register(client, email=EMAIL.upper())
    assert response.status_code == 409
    assert response.json() == {"error": "email_taken"}


@pytest.mark.parametrize(
    "overrides, field, code",
    [
        ({"full_name": ""}, "full_name", "name_required"),
        ({"full_name": "A"}, "full_name", "name_length"),
        ({"full_name": "A" * 61}, "full_name", "name_length"),
        ({"email": ""}, "email", "email_required"),
        ({"email": "a@gmail.com"}, "email", "email_domain"),
        ({"email": "a b@student.ksu.edu.sa"}, "email", "email_domain"),
        ({"email": "@student.ksu.edu.sa"}, "email", "email_domain"),
        ({"password": ""}, "password", "password_required"),
        ({"password": "Ab1"}, "password", "password_too_short"),
        ({"password": "abcdefgh"}, "password", "password_weak"),
        ({"password": "12345678"}, "password", "password_weak"),
        ({"password": "a1" * 65}, "password", "password_too_long"),
    ],
)
def test_register_validation_codes(auth, overrides, field, code):
    client, *_ = auth()
    response = register(client, **overrides)
    assert response.status_code == 422
    assert response.json()["error"] == "validation"
    assert response.json()["fields"][field] == code


def test_missing_fields_are_field_codes_not_a_crash(auth):
    client, *_ = auth()
    response = client.post("/auth/register", json={})
    assert response.status_code == 422
    assert response.json()["fields"] == {
        "full_name": "name_required",
        "email": "email_required",
        "password": "password_required",
    }


def test_arabic_letters_count_as_letters_in_a_password(auth):
    client, *_ = auth()
    assert register(client, password="كلمةسر123").status_code == 201


def test_password_is_stored_hashed(auth):
    client, _mailer, store, _now = auth()
    register(client)
    stored = store.get_user_by_email(EMAIL).password_hash
    assert PASSWORD not in stored and stored.startswith("scrypt$")


def test_login_logout_and_wrong_password(auth):
    client, *_ = auth()
    register(client)
    client.post("/auth/logout")
    client.cookies.clear()

    wrong = client.post("/auth/login", json={"email": EMAIL, "password": "Wrong1234"})
    assert wrong.status_code == 401 and wrong.json() == {"error": "invalid_credentials"}

    unknown = client.post(
        "/auth/login", json={"email": "999@student.ksu.edu.sa", "password": PASSWORD}
    )
    assert unknown.status_code == 401 and unknown.json() == {"error": "invalid_credentials"}

    ok = client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert ok.status_code == 200 and ok.json()["user"]["email"] == EMAIL
    assert client.get("/auth/me").status_code == 200

    out = client.post("/auth/logout")
    assert out.status_code == 204
    client.cookies.clear()
    me = client.get("/auth/me")
    assert me.status_code == 401 and me.json() == {"error": "unauthenticated"}


def test_logout_deletes_the_server_session(auth):
    client, _mailer, store, _now = auth()
    register(client)
    token = client.cookies.get("ksu_session")
    client.post("/auth/logout")

    replay = TestClient(main.app)
    replay.cookies.set("ksu_session", token)
    assert replay.get("/auth/me").status_code == 401


def test_session_token_is_not_stored_in_plain_text(auth):
    client, _mailer, store, _now = auth()
    register(client)
    token = client.cookies.get("ksu_session")
    with sqlite3.connect(store.db_path) as conn:
        hashes = [row[0] for row in conn.execute("SELECT token_hash FROM sessions")]
    assert token not in hashes and len(hashes) == 1


def test_session_expires(auth):
    client, _mailer, _store, now = auth()
    register(client)
    now["t"] += 7 * 86_400 + 1
    assert client.get("/auth/me").status_code == 401


def test_login_validation_codes(auth):
    client, *_ = auth()
    response = client.post("/auth/login", json={"email": "x@gmail.com", "password": ""})
    assert response.status_code == 422
    assert response.json()["fields"] == {
        "email": "email_domain",
        "password": "password_required",
    }


def test_verification_routes_are_off_by_default(auth):
    client, *_ = auth()
    for path, body in (
        ("/auth/verify", {"email": EMAIL, "code": "123456"}),
        ("/auth/resend", {"email": EMAIL}),
    ):
        response = client.post(path, json=body)
        assert response.status_code == 404
        assert response.json() == {"error": "verification_disabled"}


def test_cors_preflight_allows_the_front_end_for_auth(auth):
    client, *_ = auth()
    response = client.options(
        "/auth/login",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert response.headers["access-control-allow-credentials"] == "true"


# --- email verification switched on -----------------------------------------


def test_verification_on_register_sends_a_code_and_no_cookie(auth):
    client, mailer, store, _now = auth(verification=True)

    response = register(client, lang="en")

    assert response.status_code == 201
    assert response.json()["verification_required"] is True
    assert "set-cookie" not in response.headers
    assert len(mailer.sent) == 1
    sent = mailer.sent[0]
    assert sent["to"] == EMAIL and sent["lang"] == "en"
    assert len(sent["code"]) == 6 and sent["code"].isdigit()
    assert store.get_code(EMAIL).code_hash != sent["code"]

    blocked = client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert blocked.status_code == 403 and blocked.json() == {"error": "email_not_verified"}


def test_verification_with_the_right_code_signs_in(auth):
    client, mailer, store, _now = auth(verification=True)
    register(client)

    response = client.post("/auth/verify", json={"email": EMAIL, "code": mailer.last_code})

    assert response.status_code == 200
    assert response.json()["user"]["email"] == EMAIL
    assert client.get("/auth/me").status_code == 200
    assert store.get_code(EMAIL) is None
    client.post("/auth/logout")
    client.cookies.clear()
    ok = client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert ok.status_code == 200


def test_verification_code_is_single_use(auth):
    client, mailer, *_ = auth(verification=True)
    register(client)
    code = mailer.last_code
    assert client.post("/auth/verify", json={"email": EMAIL, "code": code}).status_code == 200
    again = client.post("/auth/verify", json={"email": EMAIL, "code": code})
    assert again.status_code == 400 and again.json() == {"error": "invalid_code"}


def test_wrong_codes_are_limited(auth):
    client, mailer, store, _now = auth(verification=True)
    register(client)
    right = mailer.last_code
    wrong = "000000" if right != "000000" else "111111"

    for _ in range(4):
        response = client.post("/auth/verify", json={"email": EMAIL, "code": wrong})
        assert response.status_code == 400 and response.json() == {"error": "invalid_code"}

    fifth = client.post("/auth/verify", json={"email": EMAIL, "code": wrong})
    assert fifth.status_code == 429 and fifth.json() == {"error": "too_many_attempts"}
    assert store.get_code(EMAIL) is None
    late = client.post("/auth/verify", json={"email": EMAIL, "code": right})
    assert late.status_code == 400


def test_expired_code_is_rejected(auth):
    client, mailer, _store, now = auth(verification=True)
    register(client)
    now["t"] += 10 * 60
    response = client.post("/auth/verify", json={"email": EMAIL, "code": mailer.last_code})
    assert response.status_code == 400 and response.json() == {"error": "code_expired"}


def test_code_format_is_checked(auth):
    client, *_ = auth(verification=True)
    register(client)
    response = client.post("/auth/verify", json={"email": EMAIL, "code": "12ab"})
    assert response.status_code == 422 and response.json()["fields"]["code"] == "code_format"


def test_resend_waits_then_replaces_the_code(auth):
    client, mailer, _store, now = auth(verification=True)
    register(client)
    first = mailer.last_code

    too_soon = client.post("/auth/resend", json={"email": EMAIL})
    assert too_soon.status_code == 429
    assert too_soon.json()["error"] == "resend_too_soon"
    assert too_soon.json()["retry_after"] == 60

    now["t"] += 60
    assert client.post("/auth/resend", json={"email": EMAIL}).status_code == 204
    assert len(mailer.sent) == 2
    if mailer.last_code != first:
        stale = client.post("/auth/verify", json={"email": EMAIL, "code": first})
        assert stale.status_code == 400
    assert client.post(
        "/auth/verify", json={"email": EMAIL, "code": mailer.last_code}
    ).status_code == 200


def test_resend_does_not_reveal_unknown_accounts(auth):
    client, mailer, *_ = auth(verification=True)
    response = client.post("/auth/resend", json={"email": "999@student.ksu.edu.sa"})
    assert response.status_code == 204 and mailer.sent == []


def test_failed_email_undoes_the_sign_up(auth):
    client, mailer, store, _now = auth(verification=True)
    mailer.fail = True

    response = register(client)

    assert response.status_code == 503 and response.json() == {"error": "email_unavailable"}
    assert store.get_user_by_email(EMAIL) is None
    mailer.fail = False
    assert register(client).status_code == 201


def test_smtp_settings_are_required_when_verification_is_on(tmp_path, monkeypatch):
    for name in ("SMTP_HOST", "SMTP_FROM"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(RuntimeError, match="SMTP_HOST"):
        auth_config.load_smtp_settings(tmp_path / "missing.env")

    env = tmp_path / ".env"
    env.write_text("SMTP_HOST=smtp.example.com\nSMTP_FROM=agent@example.com\n")
    settings = auth_config.load_smtp_settings(env)
    assert settings.port == 587 and settings.host == "smtp.example.com"


# --- POST /chat requires sign-in --------------------------------------------


def _fake_answering(monkeypatch, tmp_path):
    """Fake retriever, model and config for /chat, the same fakes test_chat uses."""
    import answer
    from test_answer import (
        GRADUATION_TEXT,
        FakeChatClient,
        FakeRetriever,
        make_result,
        reply,
        write_config,
    )

    fake = FakeChatClient(reply(True, "الحد الأدنى 2,75 (المادة 62)."), None)
    retriever = FakeRetriever([make_result(62, GRADUATION_TEXT)])
    config = answer.load_config(write_config(tmp_path / "chat.toml"))
    monkeypatch.setattr(main, "get_retriever", lambda: retriever)
    monkeypatch.setattr(main, "get_client", lambda: fake)
    monkeypatch.setattr(main, "get_config", lambda: config)
    return fake


def test_chat_without_a_session_is_401_and_costs_nothing(auth, monkeypatch, tmp_path):
    client, *_ = auth()
    fake = _fake_answering(monkeypatch, tmp_path)

    response = client.post("/chat", json={"message": "كم المعدل المطلوب؟"})

    assert response.status_code == 401
    assert response.json() == {"detail": "unauthenticated"}
    assert fake.calls == []


def test_chat_auth_is_checked_before_the_message(auth, monkeypatch, tmp_path):
    client, *_ = auth()
    _fake_answering(monkeypatch, tmp_path)
    response = client.post("/chat", json={"message": ""})
    assert response.status_code == 401


def test_chat_with_a_bad_or_expired_session_is_401(auth, monkeypatch, tmp_path):
    client, _mailer, _store, now = auth()
    _fake_answering(monkeypatch, tmp_path)

    client.cookies.set("ksu_session", "not-a-real-token")
    assert client.post("/chat", json={"message": "سؤال"}).status_code == 401

    client.cookies.clear()
    register(client)
    now["t"] += 7 * 86_400 + 1
    assert client.post("/chat", json={"message": "سؤال"}).status_code == 401


def test_chat_with_a_session_answers(auth, monkeypatch, tmp_path):
    client, *_ = auth()
    fake = _fake_answering(monkeypatch, tmp_path)
    register(client)

    response = client.post("/chat", json={"message": "كم المعدل المطلوب؟", "session_id": "s"})

    assert response.status_code == 200
    assert response.json()["citations"][0]["article"] == 62
    assert len(fake.calls) == 1

    client.post("/auth/logout")
    client.cookies.clear()
    assert client.post("/chat", json={"message": "سؤال"}).status_code == 401


def test_chat_401_carries_cors_headers_for_the_front_end(auth, monkeypatch, tmp_path):
    client, *_ = auth()
    _fake_answering(monkeypatch, tmp_path)
    response = client.post(
        "/chat",
        json={"message": "سؤال"},
        headers={"Origin": "http://localhost:3000"},
    )
    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
