"""The fallback intent classifier — a fake chat client, so no network.

The regex router (`app/tools.py`) answers a question it recognises and is never second
guessed. This module is the second opinion for a question it does not: one model call,
temperature 0, a JSON route, and `regulation` whenever the call fails or answers something
outside the set. Nothing here may log the question.
"""

import json
from dataclasses import replace

import pytest

import answer
from app.intent import (
    ALLOWED_ROUTES,
    INTENT_TIMEOUT_SECONDS,
    SELF_REFERENCE_RULE,
    SYSTEM_PROMPT,
    classify,
    request_for,
    route_name,
)
from app.tools import ToolRequest, detect_personal_request

from test_answer import FakeChatClient

CONFIG = answer.ChatConfig(
    provider="openai",
    model="gpt-4o-mini",
    temperature=0.0,
    max_output_tokens=700,
    price_per_1m_input=0.15,
    price_per_1m_output=0.60,
    source_id="ref-01",
)

# A held-out question the regex does not recognise: the classifier is the only route it has.
QUESTION = "كم مرة غبت في 434"


def route_of(content=None, error=None, question=QUESTION):
    """The route the classifier chooses for `question`, with the fake's calls kept."""
    client = FakeChatClient(content, error)

    return classify(question, client=client, config=CONFIG), client


def routed(content=None, error=None, question=QUESTION):
    """The request `/chat` would build, from the route the classifier chose."""
    route, client = route_of(content, error, question)

    return route, request_for(route), client


# --- an allowed route is used ----------------------------------------------


def test_a_tool_route_becomes_that_one_tool():
    route, request, _client = routed(json.dumps({"route": "get_absences"}))

    assert route == "get_absences"
    assert request == ToolRequest(tools=("get_absences",))


def test_a_reason_route_carries_the_tools_the_regex_would():
    """The consent flow is the same either way: one card, the same pages."""
    _route, request, _client = routed(json.dumps({"route": "reason:graduation"}))
    regex = detect_personal_request("هل أقدر أتخرج الفصل القادم؟")

    assert request == regex
    assert request == ToolRequest(
        tools=("get_plan_progress", "get_gpa"), reasoning=True
    )


def test_a_regulation_route_is_no_tool_request():
    route, request, _client = routed(json.dumps({"route": "regulation"}))

    assert route == "regulation"
    assert request is None


def test_the_route_is_read_from_the_json_reply():
    """The model's reply is JSON, so a wrapped or padded object still routes."""
    route, request, _client = routed(
        'Here is the route:\n{"route": "get_courses"}\n'
    )

    assert route == "get_courses"
    assert request == ToolRequest(tools=("get_courses",))


# --- anything else is regulation -------------------------------------------


def test_a_route_outside_the_set_is_regulation():
    route, request, _client = routed(json.dumps({"route": "get_marks"}))

    assert route == "regulation"
    assert request is None


@pytest.mark.parametrize(
    "value",
    [
        "get_gpa ",  # padded, so it is not one of the routes
        "GET_GPA",
        "reason:",
        "reason:unknown",
        "tool:get_gpa",
        "",
    ],
)
def test_an_allowed_route_must_be_spelled_exactly(value):
    route, request, _client = routed(json.dumps({"route": value}))

    assert route == "regulation"
    assert request is None


def test_a_timeout_is_regulation():
    route, request, _client = routed(error=TimeoutError("the model was too slow"))

    assert route == "regulation"
    assert request is None


def test_an_exception_is_regulation():
    route, request, _client = routed(error=RuntimeError("network is down"))

    assert route == "regulation"
    assert request is None


def test_a_reply_that_is_not_json_is_regulation():
    route, request, _client = routed("get_absences")

    assert route == "regulation"
    assert request is None


def test_a_reply_without_a_route_is_regulation():
    route, request, _client = routed(json.dumps({"kind": "get_absences"}))

    assert route == "regulation"
    assert request is None


def test_an_empty_reply_is_regulation():
    route, request, _client = routed(None)

    assert route == "regulation"
    assert request is None


# --- the call the classifier makes -----------------------------------------


def test_the_call_uses_the_configured_model_at_temperature_zero():
    """A routing decision must not move between two identical questions."""
    _route, _request, client = routed(json.dumps({"route": "get_gpa"}))
    call = client.calls[0]

    assert call["model"] == CONFIG.model
    assert call["temperature"] == 0.0
    assert call["timeout"] == INTENT_TIMEOUT_SECONDS == 3.0
    assert call["response_format"] == {"type": "json_object"}


def test_the_classifier_is_asked_not_to_think():
    """Routing is one short call, and thinking would make every question pay for it.

    The shipped config names the gateway, whose thinking mode is on by default; this
    config is the shipped one with that setting, so the call is the one a gateway makes.
    """
    client = FakeChatClient(content=json.dumps({"route": "regulation"}))
    config = replace(CONFIG, reasoning_effort="none")

    classify(QUESTION, client=client, config=config)

    assert client.calls[0]["extra_body"] == {"reasoning_effort": "none"}


def test_the_question_is_the_only_user_text_sent():
    _route, _request, client = routed(json.dumps({"route": "get_gpa"}))
    messages = client.calls[0]["messages"]

    assert [message["role"] for message in messages] == ["system", "user"]
    assert messages[1]["content"] == QUESTION
    assert QUESTION not in messages[0]["content"]


def test_the_prompt_names_every_route_it_may_answer():
    _route, _request, client = routed(json.dumps({"route": "get_gpa"}))
    prompt = client.calls[0]["messages"][0]["content"]

    for route in ALLOWED_ROUTES:
        assert route in prompt, f"the prompt never names {route}"


def test_the_prompt_says_a_rule_question_is_regulation():
    _route, _request, client = routed(json.dumps({"route": "get_gpa"}))
    prompt = client.calls[0]["messages"][0]["content"].lower()

    assert "regulation" in prompt
    assert "condition" in prompt or "policy" in prompt


def test_the_prompt_puts_the_self_reference_rule_in_front_of_the_model():
    """A tool or reasoning route reads the student's pages: it needs a first-person question."""
    prompt = SYSTEM_PROMPT.lower()

    assert SELF_REFERENCE_RULE in SYSTEM_PROMPT
    assert "self-reference" in prompt
    assert "first-person" in prompt

    for marker in ("معدلي", "جدولي", "غيابي", "عندي", "أتخرج", "my"):
        assert marker in SELF_REFERENCE_RULE, f"the rule never names {marker}"


def test_the_rule_sends_a_general_question_about_the_exam_to_the_regulation():
    prompt = SYSTEM_PROMPT.lower()

    assert "the term, the university, or the final exam in general" in prompt


@pytest.mark.parametrize(
    ("question", "route"),
    (
        ("معدل الترم هذا كم ساعة؟", "regulation"),
        ("When is the final exam period?", "regulation"),
        ("كم معدلي؟", "get_gpa"),
        ("متى الفاينل حقي؟", "get_final_exams"),
    ),
)
def test_the_prompt_teaches_the_self_reference_rule_with_the_questions_it_missed(
    question, route
):
    """The two questions the classifier moved between runs, each next to its first-person pair."""
    assert f'- "{question}" -> {{"route": "{route}"}}' in SYSTEM_PROMPT


# --- privacy ---------------------------------------------------------------


def test_the_log_names_the_route_and_never_the_question(caplog):
    with caplog.at_level("INFO", logger="app.intent"):
        route, _request, _client = routed(json.dumps({"route": "get_absences"}))

    assert route == "get_absences"
    assert "get_absences" in caplog.text
    assert "classifier" in caplog.text
    assert QUESTION not in caplog.text
    assert "434" not in caplog.text


def test_a_failed_call_logs_no_reply_and_no_question(caplog):
    with caplog.at_level("DEBUG", logger="app.intent"):
        routed(error=RuntimeError("network is down"))

    assert QUESTION not in caplog.text
    assert "network is down" not in caplog.text


# --- the regex is the first opinion ----------------------------------------


@pytest.mark.parametrize(
    "question",
    ["كم معدلي التراكمي؟", "وش جدولي بكرة؟", "هل أقدر أتخرج الفصل القادم؟"],
)
def test_the_regex_answers_before_the_classifier_is_asked(question):
    """Every question the regex recognises never reaches the model."""
    assert detect_personal_request(question) is not None


def test_a_route_name_is_the_same_vocabulary_the_classifier_uses():
    question = "هل أقدر أتخرج الفصل القادم؟"
    request = detect_personal_request(question)

    assert route_name(request, question) == "reason:graduation"
    assert route_name(ToolRequest(tools=("get_absences",)), "غيابي") == "get_absences"


@pytest.mark.parametrize(
    ("question", "route"),
    [
        ("كم أحتاج أجيب عشان يصير معدلي 4.5؟", "reason:gpa_target"),
        ("هل أنا تحت الإنذار؟", "reason:academic_warning"),
        ("هل عندي تعارض في الاختبارات النهائية؟", "reason:exam_conflicts"),
        ("كيف أوزع وقتي هالأسبوع؟", "reason:plan_week"),
    ],
)
def test_two_kinds_that_read_the_same_page_are_still_named_apart(question, route):
    """`gpa_target` and `academic_warning` both read get_gpa: the tools cannot name them."""
    request = detect_personal_request(question)

    assert request is not None and request.reasoning
    assert route_name(request, question) == route
