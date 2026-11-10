"""Tests for POST /chat — fake retriever and fake LLM, so no network.

The fakes come from test_answer.py: the same retriever results and the same JSON
reply shape, injected through FastAPI's dependency overrides so the endpoint's own
validation and status codes are what is under test.
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
def api(tmp_path):
    """A TestClient whose retriever, chat client and config are fakes."""
    def make(results=None, content=None, error=None):
        chat_client = FakeChatClient(content, error)
        retriever = FakeRetriever(results or [make_result(62, GRADUATION_TEXT)])
        config = answer.load_config(write_config(tmp_path / "chat.toml"))

        main.app.dependency_overrides[main.get_retriever] = lambda: retriever
        main.app.dependency_overrides[main.get_client] = lambda: chat_client
        main.app.dependency_overrides[main.get_config] = lambda: config

        return TestClient(main.app), chat_client

    yield make
    main.app.dependency_overrides.clear()


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
    main.app.dependency_overrides[main.get_retriever] = lambda: broken_retriever

    response = client.post("/chat", json={"message": QUESTION})

    assert response.status_code == 503


def test_the_response_carries_the_contract_fields_in_order(api):
    client, _fake = api(content=reply(True, "الحد الأدنى 2,75 (المادة 62)."))

    body = client.post("/chat", json={"message": QUESTION}).json()

    assert list(body) == ["answer", "citations"]
    assert list(body["citations"][0]) == ["title", "article", "url"]
