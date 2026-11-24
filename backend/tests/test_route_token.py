"""The route token: /chat binds a reasoning answer to the question it routed.

`/chat` decides a route with the regex or the classifier; `/chat/with-data` answers the
approved question from that route's values. Without a token the second request had to decide the
kind again, with the regex alone, so a question only the classifier recognised was answered by
`/chat` and then refused by `/chat/with-data`. The token carries the kind and the tools the question
was given, signed, so the second request uses them instead of guessing again.

What these tests are strictest about: the token names no student data (only a hash of the question),
any change to it or to the request it was issued for is `route_invalid`, and the token's text never
reaches a log record.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import time

import pytest
from fastapi.testclient import TestClient

import answer
from app import main, route_token
from app.auth.routes import require_user
from app.auth.store import User
from app.tools import REASONING_TOOLS, detect_personal_request

from test_answer import (
    GRADUATION_TEXT,
    FakeChatClient,
    FakeRetriever,
    make_result,
    reply,
    write_config,
)

# A graduation question app/tools.py does not recognise: the classifier is the only router
# that can route it, so it is exactly the case the token exists for.
CLASSIFIER_ONLY_QUESTION = "ممكن أتخرج الترم الجاي؟"

# A graduation question the regex does recognise, used where the token must win over it.
GRADUATION_QUESTION = "هل أقدر أتخرج الفصل القادم؟"

SIGNED_IN = User(
    id="u-1",
    full_name="Test Student",
    email="444100001@student.ksu.edu.sa",
    password_hash="scrypt$unused",
    lang="ar",
    email_verified=True,
)

OTHER_STUDENT = User(
    id="u-2",
    full_name="Other Student",
    email="444100002@student.ksu.edu.sa",
    password_hash="scrypt$unused",
    lang="ar",
    email_verified=True,
)

SOURCE = answer.SourceRef(
    title="لائحة الدراسة والاختبارات", url="https://dar.ksu.edu.sa/regulations.pdf"
)

GPA = {
    "cumulative_gpa": "4,21",
    "scale": "5",
    "earned_hours": 96,
    "registered_hours": 99,
    "as_of_term": "الفصل الأول 1448/1449",
}

PLAN = {
    "completed_hours": 96,
    "remaining_hours": 3,
    "remaining_courses": [],
}

DATA = {"get_gpa": GPA, "get_plan_progress": PLAN}

ABSENCES = {
    "get_absences": {
        "courses": [
            {
                "code": "101",
                "name": "تفاضل وتكامل",
                "absence_percent": 10,
                "absences": 3,
                "lates": 0,
            }
        ]
    }
}

CLASSIFIER_REPLY = json.dumps({"route": "reason:graduation"})


def _issue(
    message: str = CLASSIFIER_ONLY_QUESTION,
    *,
    user_id: str = SIGNED_IN.id,
    kind: str = "graduation",
    issued_at: int | None = None,
) -> str:
    """A token as /chat issues it, without driving the endpoint."""
    return route_token.issue(
        user_id=user_id,
        message=message,
        kind=kind,
        tools=REASONING_TOOLS[kind],
        issued_at=issued_at,
    )


# --- the token itself ------------------------------------------------------


def test_a_token_issued_for_a_request_is_accepted_for_it():
    claim = route_token.verify(
        _issue(), user_id=SIGNED_IN.id, message=CLASSIFIER_ONLY_QUESTION
    )

    assert claim.kind == "graduation"
    assert claim.tools == ("get_plan_progress", "get_gpa")


def test_the_token_names_the_student_by_id_and_the_question_only_by_its_hash():
    """The token is base64 text in the browser: it must carry no question and no value."""
    token = _issue()
    payload_segment = token.split(".")[0]
    decoded = base64.urlsafe_b64decode(
        payload_segment + "=" * (-len(payload_segment) % 4)
    )
    payload = json.loads(decoded)

    assert set(payload) == {"u", "m", "k", "t", "iat"}
    assert payload["u"] == SIGNED_IN.id
    assert payload["m"] == hashlib.sha256(
        CLASSIFIER_ONLY_QUESTION.encode("utf-8")
    ).hexdigest()
    assert payload["k"] == "graduation"
    assert payload["t"] == ["get_plan_progress", "get_gpa"]
    assert isinstance(payload["iat"], int)
    assert CLASSIFIER_ONLY_QUESTION.encode("utf-8") not in decoded


def test_a_changed_payload_does_not_verify():
    token = _issue()
    payload, mac = token.split(".")
    raw = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
    rewritten = dict(json.loads(raw), k="absences", t=["get_absences"])
    changed = base64.urlsafe_b64encode(
        json.dumps(rewritten, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).rstrip(b"=").decode("ascii")

    with pytest.raises(route_token.RouteTokenError):
        route_token.verify(
            f"{changed}.{mac}",
            user_id=SIGNED_IN.id,
            message=CLASSIFIER_ONLY_QUESTION,
        )


def test_a_non_canonical_base64_segment_is_rejected():
    """'AB' decodes to the same byte as 'AA', so only a re-encode check catches it.

    Python's decoder ignores the padding bits, so a token whose last character was
    changed verified for about one key in four and the tamper tests passed by luck.
    """
    assert route_token._b64decode("AA") == b"\x00"

    with pytest.raises(route_token.RouteTokenError):
        route_token._b64decode("AB")


def test_a_token_from_another_student_is_rejected():
    with pytest.raises(route_token.RouteTokenError):
        route_token.verify(
            _issue(user_id=OTHER_STUDENT.id),
            user_id=SIGNED_IN.id,
            message=CLASSIFIER_ONLY_QUESTION,
        )


def test_a_token_for_another_question_is_rejected():
    with pytest.raises(route_token.RouteTokenError):
        route_token.verify(
            _issue(), user_id=SIGNED_IN.id, message=GRADUATION_QUESTION
        )


def test_a_token_is_valid_until_fifteen_minutes_have_passed():
    issued_at = int(time.time()) - route_token.TOKEN_LIFETIME_SECONDS

    claim = route_token.verify(
        _issue(issued_at=issued_at), user_id=SIGNED_IN.id, message=CLASSIFIER_ONLY_QUESTION
    )

    assert claim.kind == "graduation"


def test_a_token_older_than_fifteen_minutes_is_rejected():
    issued_at = int(time.time()) - route_token.TOKEN_LIFETIME_SECONDS - 1

    with pytest.raises(route_token.RouteTokenError):
        route_token.verify(
            _issue(issued_at=issued_at),
            user_id=SIGNED_IN.id,
            message=CLASSIFIER_ONLY_QUESTION,
        )


@pytest.mark.parametrize(
    "token",
    [
        "",
        "not-a-token",
        "a.b.c",
        "!!!.???",
        # A payload that is not JSON, with a signature over it.
        base64.urlsafe_b64encode(b"not json").rstrip(b"=").decode("ascii") + ".AAAA",
    ],
)
def test_a_malformed_token_is_rejected(token):
    with pytest.raises(route_token.RouteTokenError):
        route_token.verify(token, user_id=SIGNED_IN.id, message=CLASSIFIER_ONLY_QUESTION)


def test_the_secret_comes_from_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("KSU_ROUTE_SECRET", "a-secret-from-the-environment")

    secret = route_token.get_secret(env_file=tmp_path / "absent.env")

    assert secret == b"a-secret-from-the-environment"


def test_a_missing_secret_is_a_random_secret_and_a_warning_without_a_value(
    monkeypatch, tmp_path, caplog
):
    """No secret in .env or the environment: the process makes one and says so, naming none."""
    monkeypatch.delenv("KSU_ROUTE_SECRET", raising=False)

    with caplog.at_level(logging.WARNING, logger="app.route_token"):
        secret = route_token.get_secret(env_file=tmp_path / "absent.env")
        again = route_token.get_secret(env_file=tmp_path / "absent.env")

    assert len(secret) >= 32
    assert secret == again
    assert "KSU_ROUTE_SECRET" in caplog.text
    assert secret.decode("utf-8", "replace") not in caplog.text


# --- the two endpoints, end to end -----------------------------------------


@pytest.fixture
def api(tmp_path, monkeypatch):
    """A TestClient whose retriever, model and config are fakes."""

    def make(content=None):
        chat_client = FakeChatClient(
            content if content is not None else CLASSIFIER_REPLY
        )
        retriever = FakeRetriever([make_result(62, GRADUATION_TEXT)])
        config = answer.load_config(write_config(tmp_path / "chat.toml"))

        monkeypatch.setattr(main, "get_retriever", lambda: retriever)
        monkeypatch.setattr(main, "get_client", lambda: chat_client)
        monkeypatch.setattr(main, "get_config", lambda: config)
        monkeypatch.setattr(main, "get_source", lambda: SOURCE)
        monkeypatch.setitem(main.app.dependency_overrides, require_user, lambda: SIGNED_IN)

        return TestClient(main.app), chat_client

    yield make


def _reason(client, message=CLASSIFIER_ONLY_QUESTION):
    """The /chat reason reply, as the website receives it."""
    response = client.post("/chat", json={"message": message})

    assert response.status_code == 200

    return response.json()


def _with_data(client, token, *, message=CLASSIFIER_ONLY_QUESTION, data=DATA):
    body = {"message": message, "data": data}

    if token is not None:
        body["route_token"] = token

    return client.post("/chat/with-data", json=body)


def test_a_question_only_the_classifier_routes_is_answered_after_approval(api):
    """The bug this token fixes: /chat routed it, /chat/with-data refused it."""
    assert detect_personal_request(CLASSIFIER_ONLY_QUESTION) is None

    client, fake = api()
    reason = _reason(client)

    assert reason["type"] == "reason"
    assert reason["tools"] == ["get_plan_progress", "get_gpa"]
    assert reason["route_token"]

    response = _with_data(client, reason["route_token"])

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "answer"
    # The graduation template, from the kind the token carries: the regex would have
    # computed no facts at all for this wording.
    assert "3 ساعة" in body["answer"]
    assert body["basis"] == "regulation"
    # The classifier was asked once, by /chat; the approved request never asks it again.
    assert len(fake.calls) == 1


def test_the_answer_uses_the_kind_the_token_carries_not_the_regex(api):
    """The same wording the regex routes to graduation is answered as absences."""
    client, fake = api()
    token = _issue(GRADUATION_QUESTION, kind="absences")

    response = _with_data(
        client, token, message=GRADUATION_QUESTION, data=ABSENCES
    )

    assert response.status_code == 200
    body = response.json()
    assert "10%" in body["answer"] and "25%" in body["answer"]
    assert fake.calls == []


def test_the_data_keys_must_equal_the_tokens_tools(api):
    client, _fake = api()

    response = _with_data(client, _issue(), data={"get_gpa": GPA})

    assert response.status_code == 422
    assert response.json() == {"detail": "data_missing"}


def test_a_missing_token_is_route_invalid(api):
    client, fake = api()

    response = _with_data(client, None)

    assert response.status_code == 422
    assert response.json() == {"detail": "route_invalid"}
    assert fake.calls == []


def test_a_tampered_token_is_route_invalid(api):
    client, fake = api()
    reason = _reason(client)
    asked = len(fake.calls)
    payload, mac = reason["route_token"].split(".")
    flipped = payload[:-1] + ("A" if payload[-1] != "A" else "B")

    response = _with_data(client, f"{flipped}.{mac}")

    assert response.status_code == 422
    assert response.json() == {"detail": "route_invalid"}
    # Refused before anything is answered, and the classifier is not asked again.
    assert len(fake.calls) == asked


def test_an_expired_token_is_route_invalid(api):
    client, fake = api()
    token = _issue(issued_at=int(time.time()) - route_token.TOKEN_LIFETIME_SECONDS - 1)

    response = _with_data(client, token)

    assert response.status_code == 422
    assert response.json() == {"detail": "route_invalid"}
    assert fake.calls == []


def test_another_students_token_is_route_invalid(api):
    client, fake = api()

    response = _with_data(client, _issue(user_id=OTHER_STUDENT.id))

    assert response.status_code == 422
    assert response.json() == {"detail": "route_invalid"}
    assert fake.calls == []


def test_a_token_for_another_question_is_route_invalid(api):
    client, fake = api()

    response = _with_data(client, _issue(message=GRADUATION_QUESTION))

    assert response.status_code == 422
    assert response.json() == {"detail": "route_invalid"}
    assert fake.calls == []


def test_the_token_never_reaches_a_log_record(api, caplog):
    client, _fake = api()

    with caplog.at_level("DEBUG"):
        reason = _reason(client)
        token = reason["route_token"]
        tampered = _with_data(client, token[:-1] + ("A" if token[-1] != "A" else "B"))

    formatted = "\n".join(
        logging.Formatter().format(record) for record in caplog.records
    )

    assert reason["route_token"] not in caplog.text
    assert token[:32] not in caplog.text
    assert token[:32] not in formatted
    assert tampered.status_code == 422
    assert "route_invalid" in caplog.text
