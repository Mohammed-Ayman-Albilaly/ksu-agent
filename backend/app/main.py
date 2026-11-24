"""HTTP API for KSU Agent.

Two endpoints, exactly as written in docs/api-contract.md: POST /chat answers a question
with an Arabic answer plus the regulation articles it cites, or names the tools the
website runs; POST /chat/with-data answers a reasoning question from the values the
student approved sending. Retrieval and generation live in backend/scripts (retrieve.py,
answer.py); this module validates the request and maps failures to status codes. The API
key is read from .env by answer.make_client and never appears in a response or a log line.

A reasoning reply carries a `route_token` (app/route_token.py): the route the question was
given, signed. `/chat/with-data` verifies it and answers from the route it names instead of
deciding the kind again, so a question only the classifier routed is not refused there.
"""

from __future__ import annotations

import logging
import time
from functools import lru_cache
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

import answer
from app import facts, intent, route_token
from app.auth.routes import require_user, router as auth_router
from app.auth.store import User
from app.tools import ToolRequest, detect_personal_request
from app.with_data import DataError, data_size, validate_data

LOGGER = logging.getLogger(__name__)

app = FastAPI(title="KSU Agent", version="0.1.0")

# The front-end dev server is the only browser origin allowed, and it sends
# cookies, so the origin is named exactly and never "*": a wildcard with
# credentials is rejected by browsers and would let any page call the API.
# Methods and headers are listed explicitly for the same reason.
ALLOWED_ORIGINS = ["http://localhost:3000"]
ALLOWED_METHODS = ["GET", "POST", "OPTIONS"]
ALLOWED_HEADERS = ["Content-Type", "Accept"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=ALLOWED_METHODS,
    allow_headers=ALLOWED_HEADERS,
)

app.include_router(auth_router)

# The whole body of a reasoning answer is small: one entry per tool the reply named,
# with the fields the contract lists. A body over this is refused before it is parsed.
MAX_WITH_DATA_BYTES = 20 * 1024

# The two endpoints whose validation failures answer with a short code.
ANSWER_PATHS = ("/chat", "/chat/with-data")


@app.middleware("http")
async def _refuse_oversized_with_data(request, call_next):
    """A body over the contract's limit is a 422 with a code, not a parse attempt."""
    if request.method == "POST" and request.url.path == "/chat/with-data":
        body = await request.body()
        if len(body) > MAX_WITH_DATA_BYTES:
            LOGGER.info("rejected a with-data request: data_too_large")
            return JSONResponse(
                status_code=422, content={"detail": "data_too_large"}
            )
    return await call_next(request)


def _message_validation_code(exc: RequestValidationError) -> str | None:
    """The short code for a bad `message`, or None for any other failure.

    The front-end switches on these codes, so the body is `{"detail": "<code>"}`
    and never a sentence: `message_empty` for an absent, empty or blank question,
    `message_too_long` for one over the contract's limit.
    """
    for error in exc.errors():
        if "message" not in error.get("loc", ()):
            continue
        if error.get("type") == "string_too_long":
            return "message_too_long"
        if error.get("type") in {"value_error", "missing"}:
            return "message_empty"
    return None


def _validation_code(exc: RequestValidationError) -> str:
    """The short code for a rejected body, whatever field it was.

    FastAPI's own 422 body repeats the offending input, and on /chat/with-data that input is
    a value the student approved for one answer (ADR 0001, rule 2), so both answer paths
    always answer with a code: `data_invalid` for a `data` the contract does not allow,
    `route_invalid` for a `route_token` that does not bind this question to this student,
    `history_invalid` for an earlier turn that is not one this API accepts, and
    `bad_request` for anything else, such as a body that is not JSON.
    """
    code = _message_validation_code(exc)
    if code is not None:
        return code
    if any("history" in error.get("loc", ()) for error in exc.errors()):
        return "history_invalid"
    if any("route_token" in error.get("loc", ()) for error in exc.errors()):
        return "route_invalid"
    if any("data" in error.get("loc", ()) for error in exc.errors()):
        return "data_invalid"
    return "bad_request"


@app.exception_handler(RequestValidationError)
async def _chat_validation_error(request, exc: RequestValidationError):
    """Answer a chat validation failure with a code; leave everything else alone."""
    if request.url.path in ANSWER_PATHS:
        code = _validation_code(exc)
        LOGGER.info("rejected a request to %s: %s", request.url.path, code)
        return JSONResponse(status_code=422, content={"detail": code})
    return await request_validation_exception_handler(request, exc)


# The turns a request may carry: the website sends the last three exchanges (six turns) with
# each question, and the server keeps none of it (ADR 0001: no session, no history file, no log
# line carrying the text).
MAX_HISTORY_TURNS = 6


class HistoryTurn(BaseModel):
    """One earlier turn of the conversation, as the website holds it.

    It is context for the answer and never a source of a fact (answer.HISTORY_RULES): the server
    only passes it into this question's prompt and stores nothing.
    """

    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=answer.MAX_QUESTION_CHARS)

    @field_validator("content")
    @classmethod
    def _content_is_not_blank(cls, value: str) -> str:
        """A blank turn carries no conversation, so it is refused rather than sent."""
        content = value.strip()
        if not content:
            raise ValueError("history_invalid")
        return content


class ChatRequest(BaseModel):
    """The request body from docs/api-contract.md."""

    message: str = Field(..., max_length=answer.MAX_QUESTION_CHARS)
    # Accepted so a client can keep its conversation id; the endpoint keeps no
    # history yet, so the value is not used.
    session_id: str | None = Field(default=None, max_length=128)
    # The conversation so far, held by the website and sent with each question. It is
    # passed into this question's prompt and stored nowhere (ADR 0001).
    history: list[HistoryTurn] = Field(
        default_factory=list, max_length=MAX_HISTORY_TURNS
    )

    @field_validator("message")
    @classmethod
    def _message_is_not_blank(cls, value: str) -> str:
        """An empty or whitespace-only question is a 422, not a model call."""
        message = value.strip()
        if not message:
            raise ValueError("message_empty")
        return message


class WithDataRequest(ChatRequest):
    """`/chat/with-data`: the question, the token it was routed with, and its values.

    `route_token` is the one `/chat` issued for this question and this student (app/route_token.py);
    `data` is one entry per tool the token names, and `validate_data` checks the keys against that
    list and each value against the tool's contract fields.
    """

    data: dict[str, Any] = Field(default_factory=dict)
    route_token: str = Field(..., max_length=2048)

class CitationModel(BaseModel):
    """One cited article, in the contract's field order."""

    title: str
    article: int | None
    url: str


class ChatResponse(BaseModel):
    """An answer, in the contract's field order.

    `basis` says what the answer rests on: "regulation" when the regulation answers the question,
    "student_data" when the student's own numbers are all there is, so the website can say so
    before the student reads a number that no article supports.
    """

    type: Literal["answer"] = "answer"
    answer: str
    citations: list[CitationModel]
    basis: Literal["regulation", "student_data"] = "regulation"


class ToolResponse(BaseModel):
    """A tool the website runs in the student's browser, in the contract's order.

    The backend names the tool and nothing else: the values are read and kept on the
    student's device (ADR 0001), so this body never carries them.
    """

    type: Literal["tool"] = "tool"
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)


class ReasonResponse(BaseModel):
    """The tools a reasoning question needs, in the contract's order, and its route token.

    Nothing but names: the website runs these tools, shows the student what would be sent, and
    asks for consent for this one question (ADR 0001, rule 5). `route_token` binds the answer to
    the route the question was given, so `/chat/with-data` never has to decide it again.
    """

    type: Literal["reason"] = "reason"
    tools: list[str]
    route_token: str

@lru_cache
def get_config() -> answer.ChatConfig:
    """The chat config, read from backend/config/chat.toml once."""
    return answer.load_config()


@lru_cache
def get_retriever() -> answer.Retriever:
    """The retriever for the configured source; the index loads on first use."""
    return answer.make_searcher(get_config().source_id)


@lru_cache
def get_source() -> answer.SourceRef | None:
    """The regulation's title and URL from sources.toml, for citing an article retrieval missed."""
    return answer.load_source(get_config().source_id)


@lru_cache
def get_client():
    """The chat client; the key is read from .env here and nowhere else."""
    return answer.make_client(get_config())


@lru_cache
def get_reasoning() -> facts.ReasoningConfig:
    """The reasoning thresholds and fixed queries, read from reasoning.toml once."""
    return facts.load_config()


@app.post(
    "/chat",
    response_model=ChatResponse | ToolResponse | ReasonResponse,
)
def chat(
    request: ChatRequest, user: User = Depends(require_user)
) -> ChatResponse | ToolResponse | ReasonResponse:
    """Answer one question: a tool request, a reasoning request, or an answer.

    Only for a signed-in student: require_user answers 401 before this runs. The student is
    taken here rather than through `dependencies`, because a reasoning reply carries a token
    that names the student it was issued for.
    """
    # The regex is the fast path: it costs nothing, so it decides first and its answer is
    # never second guessed. Only tool names and the route are logged — never the question.
    personal = detect_personal_request(request.message)

    if personal is not None:
        route = intent.route_name(personal, request.message)
        LOGGER.info("routed a question to %s by regex", route)
        return _personal_response(
            personal, route=route, user_id=user.id, message=request.message
        )

    # The regex recognised nothing, so the model is asked which route the question takes
    # (app/intent.py). It costs one short call, and it is the only model call a tool answer
    # ever makes: the values are still read in the student's browser.
    # The client, the config and the index are built here rather than through Depends:
    # FastAPI solves dependencies before the request body, so a dependency would load the
    # index for a body it then rejects with a 422. Called after validation, a rejected
    # request costs nothing.
    # All of it runs inside the try, the index and the key included: a missing index file,
    # a missing API key and anything unexpected answer the same 503. Only the exception's
    # type is logged, because an error's message can carry the question and uvicorn logs a
    # chained traceback with it.
    try:
        config = get_config()
        client = get_client()
        route = intent.classify(request.message, client=client, config=config)
        personal = intent.request_for(route)

        if personal is not None:
            return _personal_response(
                personal, route=route, user_id=user.id, message=request.message
            )

        result = answer.answer_question(
            request.message,
            retriever=get_retriever(),
            client=client,
            config=config,
            source=get_source(),
            # The earlier turns are the website's, not the server's: they go into this
            # question's prompt and are kept nowhere. Only their number is ever logged.
            history=[turn.model_dump() for turn in request.history],
        )
    except Exception as exc:
        LOGGER.error("chat failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="the answer service is unavailable; please try again",
        ) from None
    LOGGER.info(
        "answered a %d-character question with %d citation(s) and %d earlier turn(s)",
        len(request.message),
        len(result.citations),
        len(request.history),
    )
    return _answer_response(result)

def _personal_response(
    personal: ToolRequest, *, route: str, user_id: str, message: str
) -> ToolResponse | ReasonResponse:
    """The reply for a question answered with tools, whichever router decided it.

    A reasoning reply carries the route token, so `/chat/with-data` answers from the kind and the
    tools this question was given instead of deciding them again with the regex alone.
    """
    if personal.reasoning:
        return ReasonResponse(
            tools=list(personal.tools),
            route_token=route_token.issue(
                user_id=user_id,
                message=message,
                kind=intent.kind_for(route),
                tools=personal.tools,
            ),
        )

    return ToolResponse(tool=personal.tools[0])

def _answer_response(
    result: answer.Answer, basis: Literal["regulation", "student_data"] = "regulation"
) -> ChatResponse:
    """The contract's answer body, in its field order."""
    return ChatResponse(
        answer=result.answer,
        basis=basis,
        citations=[
            CitationModel(
                title=citation.title,
                article=citation.article,
                url=citation.url,
            )
            for citation in result.citations
        ],
    )


@app.post(
    "/chat/with-data",
    response_model=ChatResponse,
)
def chat_with_data(
    request: WithDataRequest, user: User = Depends(require_user)
) -> ChatResponse:
    """Answer one reasoning question from the student's own values.

    The body carries the values the website read in the browser, once, after the student
    approved this one question (ADR 0001, rule 5). Only tool names, the size of the data and
    the latency are logged: never the question, never a value, and never the text of an error.

    A verdict kind (absences, academic warning, graduation, GPA target, exam clash) is answered
    from the computed numbers and the template, with no model call at all.

    The kind and the tools come from the token `/chat` issued for this question, not from the
    regex again: a question only the classifier routed would otherwise be refused here.
    """
    started = time.monotonic()

    try:
        claim = route_token.verify(
            request.route_token, user_id=user.id, message=request.message
        )
    except route_token.RouteTokenError:
        # The token's text is never logged: it is a signature, and it names no value anyway.
        LOGGER.info("rejected a with-data request: route_invalid")
        raise HTTPException(status_code=422, detail="route_invalid") from None

    kind = claim.kind

    try:
        data = validate_data(request.data, claim.tools)
    except DataError as exc:
        LOGGER.info("rejected a with-data request: %s", exc.code)
        raise HTTPException(status_code=422, detail=exc.code) from exc

    # Everything that touches the values runs inside the try, the fact computation included: an
    # unexpected error there is the same 503 as one from the answer, and only the exception's
    # type is logged, because an error's message can carry a value from the prompt and uvicorn
    # logs a chained traceback with it.
    try:
        # The numbers are computed here, in code, and never by the model: the answer explains
        # them and states no other number (app/facts.py). The extra queries are the kind's
        # fixed ones, so no value of the student's is ever part of a query.
        reasoning = get_reasoning()
        computed = facts.build_facts(kind, data, reasoning.thresholds, request.message)
        extra_queries = reasoning.retrieval.get(kind, ()) if kind else ()
        needs_regulation = facts.needs_regulation(kind)

        # A verdict kind is answered from the template and the computed numbers alone: there is
        # nothing for the model to phrase and nothing it could get wrong, so it is never called
        # and the client is not even built. Retrieval still runs, for the citations.
        if answer.is_verdict_kind(kind):
            result = answer.answer_from_facts(
                kind,
                request.message,
                retriever=get_retriever(),
                facts=computed,
                needs_regulation=needs_regulation,
                extra_queries=extra_queries,
                source=get_source(),
            )
        else:
            result = answer.answer_question(
                request.message,
                retriever=get_retriever(),
                client=get_client(),
                config=get_config(),
                student_data=data,
                facts=computed,
                extra_queries=extra_queries,
                needs_regulation=needs_regulation,
                source=get_source(),
            )
    except Exception as exc:
        LOGGER.error("with-data failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="the answer service is unavailable; please try again",
        ) from None

    LOGGER.info(
        "answered a %s question with %s (%d bytes of data) in %d ms",
        kind,
        ", ".join(data),
        data_size(data),
        round((time.monotonic() - started) * 1000),
    )
    return _answer_response(
        result, "regulation" if needs_regulation else "student_data"
    )
