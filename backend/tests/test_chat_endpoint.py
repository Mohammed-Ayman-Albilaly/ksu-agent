"""Tests for POST /chat — fake retriever and fake LLM, so no network.

The fakes come from test_answer.py: the same retriever results and the same JSON
reply shape, patched onto the module so the endpoint's own validation and status
codes are what is under test.
"""

import pytest
from fastapi.testclient import TestClient

import answer
from app import main

from test_answer import (
    GRADUATION_TEXT,
    TITLE,
    URL,
    FakeChatClient,
    FakeRetriever,
    make_result,
    reply,
    write_config,
)

QUESTION = "كم المعدل المطلوب عشان أتخرج؟"


@pytest.fixture
def api(tmp_path, monkeypatch):
    """A TestClient whose retriever, chat client and config are fakes.

    The endpoint resolves these itself rather than through Depends, so the fakes are
    patched onto the module instead of into app.dependency_overrides.
    """
    def make(results=None, content=None, error=None):
        chat_client = FakeChatClient(content, error)
        retriever = FakeRetriever(results or [make_result(62, GRADUATION_TEXT)])
        config = answer.load_config(write_config(tmp_path / "chat.toml"))

        monkeypatch.setattr(main, "get_retriever", lambda: retriever)
        monkeypatch.setattr(main, "get_client", lambda: chat_client)
        monkeypatch.setattr(main, "get_config", lambda: config)

        return TestClient(main.app), chat_client

    yield make


# --- the two required behaviours -------------------------------------------


def test_answerable_question_returns_an_answer_with_citations(api):
    client, _fake = api(
        content=reply(True, "الحد الأدنى للمعدل التراكمي 2,75 من 5,00 (المادة 62).")
    )

    response = client.post("/chat", json={"message": QUESTION, "session_id": "s-1"})

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"answer", "citations"}
    assert "2,75" in body["answer"]
    assert body["citations"] == [{"title": TITLE, "article": 62, "url": URL}]


def test_unsupported_question_returns_the_fallback_without_citations(api):
    client, _fake = api(content=reply(False, ""))

    response = client.post("/chat", json={"message": QUESTION, "session_id": "s-1"})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == answer.FALLBACK_ANSWER
    assert body["citations"] == []


# --- request validation ----------------------------------------------------


def test_an_empty_message_is_a_422(api):
    client, fake = api(content=reply(True, "x"))

    response = client.post("/chat", json={"message": "", "session_id": "s-1"})

    assert response.status_code == 422
    assert fake.calls == []


def test_a_whitespace_only_message_is_a_422(api):
    client, fake = api(content=reply(True, "x"))

    response = client.post("/chat", json={"message": "   ", "session_id": "s-1"})

    assert response.status_code == 422
    assert fake.calls == []


def test_a_missing_message_is_a_422(api):
    client, _fake = api(content=reply(True, "x"))

    response = client.post("/chat", json={"session_id": "s-1"})

    assert response.status_code == 422


def test_a_message_over_1000_characters_is_a_422(api):
    client, fake = api(content=reply(True, "x"))

    response = client.post("/chat", json={"message": "س" * 1001})

    assert response.status_code == 422
    assert fake.calls == []


def test_a_message_of_exactly_1000_characters_is_accepted(api):
    client, fake = api(content=reply(True, "الحد الأدنى 2,75 (المادة 62)."))

    response = client.post("/chat", json={"message": "س" * 1000})

    assert response.status_code == 200
    assert len(fake.calls) == 1


def test_session_id_is_optional(api):
    client, _fake = api(content=reply(True, "الحد الأدنى 2,75 (المادة 62)."))

    response = client.post("/chat", json={"message": QUESTION})

    assert response.status_code == 200


# --- failure handling -----------------------------------------------------


def test_model_failure_is_a_503_without_the_question_or_the_key(api):
    client, _fake = api(error=RuntimeError("provider is down"))

    response = client.post("/chat", json={"message": QUESTION})

    assert response.status_code == 503
    assert "provider is down" not in response.text
    assert QUESTION not in response.text


def test_retrieval_failure_is_a_503(api, monkeypatch):
    def broken_retriever(question, k=5):
        raise OSError("index missing")

    client, _fake = api(content=reply(True, "x"))
    monkeypatch.setattr(main, "get_retriever", lambda: broken_retriever)

    response = client.post("/chat", json={"message": QUESTION})

    assert response.status_code == 503


def test_the_response_carries_the_contract_fields_in_order(api):
    client, _fake = api(content=reply(True, "الحد الأدنى 2,75 (المادة 62)."))

    body = client.post("/chat", json={"message": QUESTION}).json()

    assert list(body) == ["answer", "citations"]
    assert list(body["citations"][0]) == ["title", "article", "url"]


# --- CORS ------------------------------------------------------------------


def test_preflight_from_the_frontend_origin_is_allowed(api):
    client, _fake = api(content=reply(True, "x"))

    response = client.options(
        "/chat",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert response.headers["access-control-allow-origin"] != "*"
    assert response.headers["access-control-allow-credentials"] == "true"
    allowed_methods = response.headers["access-control-allow-methods"]
    assert "POST" in allowed_methods and "OPTIONS" in allowed_methods
    assert "content-type" in response.headers["access-control-allow-headers"].lower()


def test_preflight_from_another_origin_gets_no_allow_origin_header(api):
    client, _fake = api(content=reply(True, "x"))

    response = client.options(
        "/chat",
        headers={
            "Origin": "http://localhost:3001",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert "access-control-allow-origin" not in response.headers


def test_an_allowed_origin_is_echoed_on_the_actual_response(api):
    client, _fake = api(content=reply(True, "الحد الأدنى 2,75 (المادة 62)."))

    response = client.post(
        "/chat",
        json={"message": QUESTION},
        headers={"Origin": "http://localhost:3000"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert response.headers["access-control-allow-credentials"] == "true"


# --- validation codes ------------------------------------------------------


def test_a_422_never_builds_the_retriever_or_the_client(api, monkeypatch):
    """A rejected body must not load the index or the model client: 422 stays cheap."""
    client, fake = api(content=reply(True, "x"))
    real_retriever = main.get_retriever
    real_client = main.get_client
    built: list[str] = []

    def counting_retriever():
        built.append("retriever")
        return real_retriever()

    def counting_client():
        built.append("client")
        return real_client()

    monkeypatch.setattr(main, "get_retriever", counting_retriever)
    monkeypatch.setattr(main, "get_client", counting_client)

    for body in ({"message": ""}, {"message": "س" * (answer.MAX_QUESTION_CHARS + 1)}):
        assert client.post("/chat", json=body).status_code == 422

    assert built == []
    assert fake.calls == []


def test_an_empty_message_returns_the_code_message_empty(api):
    client, fake = api(content=reply(True, "x"))

    response = client.post("/chat", json={"message": "", "session_id": "s-1"})

    assert response.status_code == 422
    assert response.json() == {"detail": "message_empty"}
    assert fake.calls == []


def test_a_whitespace_only_message_returns_the_code_message_empty(api):
    client, _fake = api(content=reply(True, "x"))

    response = client.post("/chat", json={"message": " \t\n "})

    assert response.status_code == 422
    assert response.json() == {"detail": "message_empty"}


def test_a_missing_message_returns_the_code_message_empty(api):
    client, _fake = api(content=reply(True, "x"))

    response = client.post("/chat", json={"session_id": "s-1"})

    assert response.status_code == 422
    assert response.json() == {"detail": "message_empty"}


def test_a_message_over_the_limit_returns_the_code_message_too_long(api):
    client, fake = api(content=reply(True, "x"))

    response = client.post("/chat", json={"message": "س" * (answer.MAX_QUESTION_CHARS + 1)})

    assert response.status_code == 422
    assert response.json() == {"detail": "message_too_long"}
    assert fake.calls == []


def test_a_message_at_the_limit_is_not_rejected(api):
    client, _fake = api(content=reply(True, "الحد الأدنى 2,75 (المادة 62)."))

    response = client.post("/chat", json={"message": "س" * answer.MAX_QUESTION_CHARS})

    assert response.status_code == 200


def test_a_validation_code_does_not_echo_the_question(api):
    client, _fake = api(content=reply(True, "x"))
    question = "س" * (answer.MAX_QUESTION_CHARS + 1)

    response = client.post("/chat", json={"message": question})

    assert response.json() == {"detail": "message_too_long"}
    assert "س" not in response.text
