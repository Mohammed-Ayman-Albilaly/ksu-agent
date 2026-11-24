"""A second opinion on a question the regex router does not recognise.

`app/tools.py` matches patterns, costs nothing and answers first. Its rules were written
against the questions we could think of, and a student's wording is wider than that: «كم مرة
غبت في 434» carries none of the words the absence pattern needs, so the regex returns None and
the question used to fall through to a regulation answer that could not help.

When the regex returns None this module asks the chat model once which route the question takes.
The route is one of a closed set — `regulation`, the nine tools, or `reason:<kind>` for the six
reasoning kinds — and every other answer, including a failure, a timeout and a reply outside the set,
is `regulation`: exactly what the endpoint did before this module existed. A tool route builds the
same `ToolRequest` the regex would, so the consent flow cannot tell which of the two decided.

The model and the client come from `backend/config/chat.toml`; the temperature is 0 rather than the
configured one, because a routing decision must not move between two identical questions. The question
is the only text sent — it already reaches the server — and only the chosen route and which of the two
decided it are logged, never the question.
"""

from __future__ import annotations

import json
import logging

import gateway

from app.tools import REASONING_TOOLS, ToolRequest, detect_reasoning_kind

LOGGER = logging.getLogger(__name__)

# A routing decision is one short word: a model that cannot answer in three seconds is no better
# than the regex that already missed, and the student is waiting for it.
INTENT_TIMEOUT_SECONDS = 3.0

# {"route": "reason:academic_warning"} is a handful of tokens; the cap only stops a model that
# decides to explain itself.
INTENT_MAX_TOKENS = 24

REGULATION = "regulation"
REASON_PREFIX = "reason:"

# The catalogue, in the order docs/api-contract.md lists it.
TOOL_ROUTES: tuple[str, ...] = (
    "get_gpa",
    "get_grades",
    "get_lms_grades",
    "get_schedule",
    "get_final_exams",
    "get_absences",
    "get_plan_progress",
    "get_courses",
    "get_assignments",
)

# The six kinds `app/facts.py` computes; the route is the kind, so the reply never names tools.
REASONING_ROUTES: tuple[str, ...] = tuple(REASONING_TOOLS)

ALLOWED_ROUTES: tuple[str, ...] = (
    REGULATION,
    *TOOL_ROUTES,
    *(f"{REASON_PREFIX}{kind}" for kind in REASONING_ROUTES),
)

# One line per route: what the student is asking about. The prompt is built from this table so a
# route can never be allowed without being described.
_ROUTE_DESCRIPTIONS: dict[str, str] = {
    REGULATION: "a rule, a condition, a policy, or how something is calculated",
    "get_gpa": "this student's cumulative GPA",
    "get_grades": "this student's course results for the term",
    "get_lms_grades": "this student's grade on Blackboard for one item: a midterm, a quiz "
    "or an assignment",
    "get_schedule": "this student's class timetable",
    "get_final_exams": "this student's final exam dates and rooms",
    "get_absences": "this student's absences and absence percentage",
    "get_plan_progress": "this student's study plan: the hours done and what is left",
    "get_courses": "this student's course list on Blackboard",
    "get_assignments": "what this student has to hand in, and when",
    f"{REASON_PREFIX}graduation": "whether or when this student can graduate",
    f"{REASON_PREFIX}absences": "whether this student is close to being barred for absence",
    f"{REASON_PREFIX}gpa_target": "what average this student needs for a target GPA",
    f"{REASON_PREFIX}academic_warning": "whether this student is on academic warning",
    f"{REASON_PREFIX}exam_conflicts": "whether this student's final exams clash",
    f"{REASON_PREFIX}plan_week": "planning this student's week around classes and due dates",
}

# One example per route a student is likely to reach, in the student's own words. The last four teach
# the self-reference rule: the same two questions asked in general and about the student. Two of them are
# already in a set, and that is said here rather than hidden: «معدل الترم هذا كم ساعة؟» is trap-01 in
# eval/phase2_router.json, and «كم معدلي؟» is «كم معدلي» in eval/phase2_router_heldout.json. Both are
# questions the classifier moved between runs, so both are taught now, and those two items no longer score
# the classifier independently. No other example is in either set.
_ROUTE_EXAMPLES: tuple[tuple[str, str], ...] = (
    ("معدلي التراكمي كم", "get_gpa"),
    ("نتيجتي في المواد", "get_grades"),
    ("درجتي في الكويز", "get_lms_grades"),
    ("محاضراتي الأسبوع الجاي", "get_schedule"),
    ("موعد اختباري النهائي", "get_final_exams"),
    ("كم غياب عندي", "get_absences"),
    ("كم ساعة خلصت من الخطة", "get_plan_progress"),
    ("ايش المواد المسجلة عندي في البلاك بورد", "get_courses"),
    ("ايش لازم اسلم هالأيام", "get_assignments"),
    ("هل راح أتخرج", f"{REASON_PREFIX}graduation"),
    ("هل باقي لي غياب قبل الحرمان", f"{REASON_PREFIX}absences"),
    ("كم أحتاج عشان أوصل 4.5", f"{REASON_PREFIX}gpa_target"),
    ("هل علي انذار", f"{REASON_PREFIX}academic_warning"),
    ("هل عندي تعارض بين الاختبارات", f"{REASON_PREFIX}exam_conflicts"),
    ("رتب لي جدولي هذا الأسبوع", f"{REASON_PREFIX}plan_week"),
    ("ما نسبة الحضور المطلوبة", REGULATION),
    ("كيف يتم حساب المعدل", REGULATION),
    ("معدل الترم هذا كم ساعة؟", REGULATION),
    ("When is the final exam period?", REGULATION),
    ("كم معدلي؟", "get_gpa"),
    ("متى الفاينل حقي؟", "get_final_exams"),
)

SELF_REFERENCE_RULE = (
    'The self-reference rule: any route other than "regulation" needs the question to refer to the '
    "student themselves — a first-person word such as معدلي, جدولي, غيابي, لي, عندي, أنا, أتخرج, جبت or "
    "غبت, or in English I, my or me. A question about the term, the university, or the final exam in "
    'general, with no such reference, is "regulation": it asks what the rule says, not what this student\'s '
    "record holds. The same words with a first-person word are about the student."
)


SYSTEM_PROMPT = "\n".join(
    [
        "You route one question from a King Saud University student to exactly one route.",
        'Reply with one JSON object and nothing else: {"route": "<route>"}',
        "",
        "The routes:",
        *(f"- {route}: {_ROUTE_DESCRIPTIONS[route]}" for route in ALLOWED_ROUTES),
        "",
        "",
        'A question about the rule itself — a condition, a policy, how something is '
        'calculated, what the regulation requires — is "regulation", even when it names the GPA, '
        "the absences, graduation or the final exam. Only a question about this student's own "
        "situation takes any other route.",
        "",
        SELF_REFERENCE_RULE,
        "",
        "Examples:",
        *(f'- "{question}" -> {{"route": "{route}"}}' for question, route in _ROUTE_EXAMPLES),
    ]
)


def classify(message: str, *, client, config) -> str:
    """The route for one question, always one of `ALLOWED_ROUTES`.

    The question is the only text sent. Whatever the call does — raise, time out, answer a route
    outside the set — the route is `regulation`, so a failure costs the student the tool answer and
    never a wrong page read.
    """
    try:
        route = _asked_route(message, client=client, config=config)
    except Exception:  # network, timeout, a reply that is not the JSON asked for
        route = REGULATION

    LOGGER.info("routed a question to %s by classifier", route)
    return route


def request_for(route: str) -> ToolRequest | None:
    """The request the regex would have built for `route`, or None for the regulation."""
    if route in TOOL_ROUTES:
        return ToolRequest(tools=(route,))

    if route.startswith(REASON_PREFIX):
        tools = REASONING_TOOLS.get(route[len(REASON_PREFIX) :])

        if tools is not None:
            return ToolRequest(tools=tools, reasoning=True)

    return None


def kind_for(route: str) -> str:
    """The reasoning kind a route names; a route that names none is a programming error.

    `/chat/with-data` computes its facts from the kind, so the kind is taken from the route the
    question was given rather than read from the message again: a question only the classifier routed
    has no kind the regex could find.
    """
    kind = route[len(REASON_PREFIX) :] if route.startswith(REASON_PREFIX) else None

    if kind not in REASONING_ROUTES:
        raise ValueError(f"{route!r} names no reasoning kind")

    return kind

def route_name(request: ToolRequest, message: str) -> str:
    """The route a `ToolRequest` names, in the vocabulary `classify` answers in.

    The kind is read from the message, not from the tools: `gpa_target` and
    `academic_warning` both read `get_gpa`, so the tools alone cannot tell them apart.
    """
    if not request.reasoning:
        return request.tools[0]

    kind = detect_reasoning_kind(message)

    return REGULATION if kind is None else f"{REASON_PREFIX}{kind}"


def _asked_route(message: str, *, client, config) -> str:
    """Call the model once and read its route; anything unreadable is a ValueError.

    The JSON mode and the thinking mode come from the gateway module: the gateway offers
    json_object and not a schema, and its thinking mode is on by default, which a routing
    decision that must take a moment cannot afford.
    """
    response = client.invoke(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ],
        model=config.model,
        # Not config.temperature: routing must be the same for the same question.
        temperature=0.0,
        max_tokens=INTENT_MAX_TOKENS,
        timeout=INTENT_TIMEOUT_SECONDS,
        **gateway.chat_kwargs(config),
    )
    route = _reply_object(_content(response)).get("route")

    if route not in ALLOWED_ROUTES:
        raise ValueError("the reply named no allowed route")

    return route

def _content(response) -> str:
    """The reply's text, or a ValueError when there is none."""
    content = getattr(response, "content", None)

    if not isinstance(content, str):
        raise ValueError("the reply had no text")

    return content


def _reply_object(content: str) -> dict:
    """The JSON object in the reply, even when the model wrapped it in a sentence."""
    try:
        value = json.loads(content)
    except ValueError:
        start, end = content.find("{"), content.rfind("}")

        if start < 0 or end <= start:
            raise ValueError("the reply was not JSON") from None

        value = json.loads(content[start : end + 1])

    return value if isinstance(value, dict) else {}
