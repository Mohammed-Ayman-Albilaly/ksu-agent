"""Tests for POST /chat — fake retriever and fake LLM, so no network.

The fakes come from test_answer.py: the same retriever results and the same JSON
reply shape, patched onto the module so the endpoint's own validation and status
codes are what is under test.
"""

import json
import logging
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import answer
from app import main
from app.auth.routes import require_user
from app.auth.store import User

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

SIGNED_IN = User(
    id="u-1",
    full_name="Test Student",
    email="444100001@student.ksu.edu.sa",
    password_hash="scrypt$unused",
    lang="ar",
    email_verified=True,
)


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
        # /chat requires sign-in; these tests are about answering, so they run as a
        # signed-in student. The 401 itself is tested in test_auth.py.
        monkeypatch.setitem(main.app.dependency_overrides, require_user, lambda: SIGNED_IN)

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
    assert set(body) == {"type", "answer", "citations", "basis"}
    assert body["type"] == "answer"
    assert "2,75" in body["answer"]
    assert body["citations"] == [{"title": TITLE, "article": 62, "url": URL}]
    assert body["basis"] == "regulation"


def test_a_question_about_the_students_own_gpa_returns_the_tool(api):
    """The backend picks the tool and returns it; the values are read in the browser."""
    client, fake = api(content=reply(True, "x"))

    response = client.post("/chat", json={"message": "ما معدلي؟", "session_id": "s-1"})

    assert response.status_code == 200
    assert response.json() == {"type": "tool", "tool": "get_gpa", "args": {}}
    assert fake.calls == []

def test_a_reasoning_question_returns_the_tools_it_needs(api):
    """A reasoning question names its tools; the values are still read in the browser."""
    client, fake = api(content=reply(True, "x"))

    response = client.post("/chat", json={"message": "هل أقدر أتخرج الفصل القادم؟"})

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "reason"
    assert body["tools"] == ["get_plan_progress", "get_gpa"]
    # The token binds this question and this student to that route (test_route_token.py).
    assert body["route_token"]
    assert fake.calls == []


def test_a_reasoning_request_builds_neither_the_retriever_nor_the_model(
    api, monkeypatch
):
    client, fake = api(content=reply(True, "x"))

    def refuse(*_args, **_kwargs):
        raise AssertionError("a reasoning request must not reach retrieval")

    monkeypatch.setattr(main, "get_retriever", refuse)
    monkeypatch.setattr(main, "get_client", refuse)

    response = client.post(
        "/chat", json={"message": "كم أحتاج أجيب عشان يصير معدلي 4.5؟"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "reason"
    assert body["tools"] == ["get_gpa"]
    assert body["route_token"]
    assert fake.calls == []


def test_a_reasoning_request_logs_the_route_and_never_the_question(api, caplog):
    client, _fake = api(content=reply(True, "x"))
    question = "هل أنا قريب من الحرمان هذا الفصل؟"

    with caplog.at_level("INFO", logger="app.main"):
        client.post("/chat", json={"message": question})

    assert "reason:absences" in caplog.text
    assert "by regex" in caplog.text
    assert question not in caplog.text
    assert "الحرمان" not in caplog.text


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
    # A wall of one letter is not a tool question, so the classifier is asked first and
    # the answer is the second call.
    assert len(fake.calls) == 2


def test_session_id_is_optional(api):
    client, _fake = api(content=reply(True, "الحد الأدنى 2,75 (المادة 62)."))

    response = client.post("/chat", json={"message": QUESTION})

    assert response.status_code == 200


# --- the classifier, for a question the regex does not recognise --------------

# None of these is matched by app/tools.py, so each one reaches the classifier.
HELD_OUT_TOOL_QUESTION = "كم مرة غبت في 434"
HELD_OUT_REASON_QUESTION = "نظم لي أسبوعي"


def client_failing_once(content, error):
    """A fake whose first call (the classifier) raises and whose answer call works."""
    calls = []

    def invoke(messages, **kwargs):
        calls.append({"messages": messages, **kwargs})
        if len(calls) == 1:
            raise error
        return SimpleNamespace(content=content, usage_metadata=None)

    return SimpleNamespace(invoke=invoke), calls


def test_the_classifier_is_not_asked_when_the_regex_matches(api, monkeypatch):
    """The regex is the fast path: a question it knows never costs a model call."""
    client, fake = api(content=reply(True, "x"))

    def refuse(*_args, **_kwargs):
        raise AssertionError("a regex match must not build the client")

    monkeypatch.setattr(main, "get_client", refuse)

    response = client.post("/chat", json={"message": "كم معدلي التراكمي؟"})

    assert response.status_code == 200
    assert response.json() == {"type": "tool", "tool": "get_gpa", "args": {}}
    assert fake.calls == []


def test_a_regex_miss_returns_the_tool_the_classifier_names(api):
    client, fake = api(content=json.dumps({"route": "get_absences"}))

    response = client.post("/chat", json={"message": HELD_OUT_TOOL_QUESTION})

    assert response.status_code == 200
    assert response.json() == {"type": "tool", "tool": "get_absences", "args": {}}
    # One call: the classifier's. A tool answer never reaches the model again.
    assert len(fake.calls) == 1
    assert fake.calls[0]["temperature"] == 0.0
    assert fake.calls[0]["timeout"] == 3.0


def test_a_regex_miss_returns_the_reasoning_tools_the_classifier_names(api):
    client, fake = api(content=json.dumps({"route": "reason:plan_week"}))

    response = client.post("/chat", json={"message": HELD_OUT_REASON_QUESTION})

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "reason"
    assert body["tools"] == ["get_assignments", "get_schedule"]
    assert body["route_token"]
    assert len(fake.calls) == 1


def test_a_classifier_route_of_regulation_still_gets_an_answer(api):
    """The classifier only decides the route; a regulation route is answered as before."""
    client, fake = api(
        content=[
            json.dumps({"route": "regulation"}),
            reply(True, "الحد الأدنى 2,75 (المادة 62)."),
        ]
    )

    response = client.post("/chat", json={"message": HELD_OUT_TOOL_QUESTION})

    assert response.status_code == 200
    assert response.json()["type"] == "answer"
    assert len(fake.calls) == 2


def test_a_classifier_failure_falls_back_to_the_regulation(api, monkeypatch):
    """A broken classifier costs the tool answer, never the answer itself."""
    client, _fake = api(content=reply(True, "الحد الأدنى 2,75 (المادة 62)."))
    broken, calls = client_failing_once(
        reply(True, "الحد الأدنى 2,75 (المادة 62)."), TimeoutError("too slow")
    )
    monkeypatch.setattr(main, "get_client", lambda: broken)

    response = client.post("/chat", json={"message": HELD_OUT_TOOL_QUESTION})

    assert response.status_code == 200
    assert response.json()["type"] == "answer"
    assert len(calls) == 2


def test_a_classifier_route_is_logged_with_the_router_that_chose_it(api, caplog):
    client, _fake = api(content=json.dumps({"route": "get_absences"}))

    with caplog.at_level("INFO"):
        client.post("/chat", json={"message": HELD_OUT_TOOL_QUESTION})

    assert "get_absences" in caplog.text
    assert "by classifier" in caplog.text
    assert HELD_OUT_TOOL_QUESTION not in caplog.text
    assert "434" not in caplog.text


# --- failure handling -----------------------------------------------------

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


def test_a_missing_index_is_a_503_not_a_traceback(api, monkeypatch, caplog):
    """The retriever is built before the answer, so a missing index must not be a 500."""

    def missing_index():
        raise OSError("data/index/ref-01.index not found")

    client, _fake = api(content=reply(True, "x"))
    monkeypatch.setattr(main, "get_retriever", missing_index)

    with caplog.at_level("INFO", logger="app.main"):
        response = client.post("/chat", json={"message": QUESTION})

    assert response.status_code == 503
    assert "index" not in response.text
    # The type is logged, the message is not: it can name a file and a value.
    assert "OSError" in caplog.text
    assert "ref-01.index" not in caplog.text


def test_a_missing_api_key_is_a_503_not_a_traceback(api, monkeypatch, caplog):
    """make_client reads the key when it is built, before the try, so it is caught too."""

    def no_key(*_args, **_kwargs):
        raise RuntimeError("LLM_API_KEY is not set; add it to .env")

    client, _fake = api(content=reply(True, "x"))
    monkeypatch.setattr(answer, "api_key", no_key)
    monkeypatch.setattr(
        main, "get_client", lambda: answer.make_client(main.get_config())
    )

    with caplog.at_level("INFO", logger="app.main"):
        response = client.post("/chat", json={"message": QUESTION})

    assert response.status_code == 503
    assert "OPENAI_API_KEY" not in response.text
    assert "RuntimeError" in caplog.text
    assert "OPENAI_API_KEY" not in caplog.text


def test_the_response_carries_the_contract_fields_in_order(api):
    client, _fake = api(content=reply(True, "الحد الأدنى 2,75 (المادة 62)."))

    body = client.post("/chat", json={"message": QUESTION}).json()

    assert list(body) == ["type", "answer", "citations", "basis"]
    assert list(body["citations"][0]) == ["title", "article", "url"]


def test_a_personal_question_builds_neither_the_retriever_nor_the_model(api, monkeypatch):
    """A tool request costs nothing: no index load, no model call, no retriever call."""
    client, fake = api(content=reply(True, "x"))

    def refuse(*_args, **_kwargs):
        raise AssertionError("a tool request must not reach retrieval or the model")

    monkeypatch.setattr(main, "get_retriever", refuse)
    monkeypatch.setattr(main, "get_client", refuse)

    response = client.post("/chat", json={"message": "كم معدلي التراكمي؟"})

    assert response.status_code == 200
    assert response.json() == {"type": "tool", "tool": "get_gpa", "args": {}}
    assert fake.calls == []


def test_a_tool_request_logs_the_tool_and_never_the_question(api, caplog):
    client, _fake = api(content=reply(True, "x"))
    question = "ما معدلي التراكمي هذا الفصل؟"

    with caplog.at_level("INFO", logger="app.main"):
        client.post("/chat", json={"message": question})

    assert "get_gpa" in caplog.text
    assert question not in caplog.text
    assert "معدلي" not in caplog.text


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


# --- chat memory: the last turns travel with the question, the server keeps none ---

# The classifier answers first for a question the regex does not know, so these use the
# two-reply fake from test_a_classifier_route_of_regulation_still_gets_an_answer.
HISTORY = [
    {"role": "user", "content": "HIST-USER-1"},
    {"role": "assistant", "content": "HIST-ASSISTANT-1"},
]

REGULATION_THEN_ANSWER = [
    json.dumps({"route": "regulation"}),
    reply(True, "الحد الأدنى 2,75 (المادة 62)."),
]


def test_the_history_reaches_the_prompt_in_order_before_the_question(api):
    client, fake = api(content=list(REGULATION_THEN_ANSWER))

    response = client.post(
        "/chat", json={"message": HELD_OUT_TOOL_QUESTION, "history": HISTORY}
    )

    assert response.status_code == 200
    assert response.json()["type"] == "answer"
    messages = fake.calls[-1]["messages"]
    assert [message["role"] for message in messages] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert messages[1]["content"] == HISTORY[0]["content"]
    assert messages[2]["content"] == HISTORY[1]["content"]
    assert HELD_OUT_TOOL_QUESTION in messages[3]["content"]


def test_six_turns_are_accepted(api):
    client, fake = api(content=list(REGULATION_THEN_ANSWER))
    history = [{"role": "user", "content": f"س-{index}"} for index in range(6)]

    response = client.post(
        "/chat", json={"message": HELD_OUT_TOOL_QUESTION, "history": history}
    )

    assert response.status_code == 200
    assert len(fake.calls[-1]["messages"]) == 1 + 6 + 1


def test_a_seven_turn_history_is_history_invalid(api):
    client, fake = api(content=reply(True, "x"))
    history = [{"role": "user", "content": f"س-{index}"} for index in range(7)]

    response = client.post(
        "/chat", json={"message": HELD_OUT_TOOL_QUESTION, "history": history}
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "history_invalid"}
    assert fake.calls == []


def test_a_blank_history_turn_is_history_invalid(api):
    client, fake = api(content=reply(True, "x"))

    response = client.post(
        "/chat",
        json={
            "message": HELD_OUT_TOOL_QUESTION,
            "history": [{"role": "user", "content": "  \t\n "}],
        },
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "history_invalid"}
    assert fake.calls == []


def test_a_history_turn_over_the_limit_is_history_invalid(api):
    client, fake = api(content=reply(True, "x"))

    response = client.post(
        "/chat",
        json={
            "message": HELD_OUT_TOOL_QUESTION,
            "history": [
                {"role": "assistant", "content": "س" * (answer.MAX_QUESTION_CHARS + 1)}
            ],
        },
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "history_invalid"}
    assert fake.calls == []


def test_a_role_that_is_not_user_or_assistant_is_history_invalid(api):
    client, fake = api(content=reply(True, "x"))

    response = client.post(
        "/chat",
        json={
            "message": HELD_OUT_TOOL_QUESTION,
            "history": [{"role": "system", "content": "أنت مساعد"}],
        },
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "history_invalid"}
    assert fake.calls == []


def test_a_history_code_does_not_echo_the_content(api):
    client, _fake = api(content=reply(True, "x"))

    response = client.post(
        "/chat",
        json={
            "message": HELD_OUT_TOOL_QUESTION,
            "history": [
                {"role": "user", "content": "HIST-LEAK-" + "س" * answer.MAX_QUESTION_CHARS}
            ],
        },
    )

    assert response.json() == {"detail": "history_invalid"}
    assert "HIST-LEAK" not in response.text


def test_the_history_text_never_reaches_a_log_record(api, caplog):
    client, _fake = api(content=list(REGULATION_THEN_ANSWER))

    with caplog.at_level("DEBUG"):
        response = client.post(
            "/chat", json={"message": HELD_OUT_TOOL_QUESTION, "history": HISTORY}
        )

    assert response.status_code == 200
    # Only the number of turns is recorded, never their text.
    assert "2 earlier turn" in caplog.text
    assert "HIST-USER-1" not in caplog.text
    assert "HIST-ASSISTANT-1" not in caplog.text
    formatted = "\n".join(
        logging.Formatter().format(record) for record in caplog.records
    )
    assert "HIST-USER-1" not in formatted
    assert "HIST-ASSISTANT-1" not in formatted
