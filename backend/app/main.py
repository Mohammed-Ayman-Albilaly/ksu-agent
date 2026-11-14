"""HTTP API for KSU Agent.

One endpoint, POST /chat, exactly as written in docs/api-contract.md: a question in,
an Arabic answer plus the regulation articles it cites out. Retrieval and generation
live in backend/scripts (retrieve.py, answer.py); this module validates the request
and maps failures to status codes. The API key is read from .env by answer.make_client
and never appears in a response or a log line.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

import answer
from app.auth.routes import require_user, router as auth_router

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


@app.exception_handler(RequestValidationError)
async def _chat_validation_error(request, exc: RequestValidationError):
    """Answer /chat validation failures with a code; leave everything else alone."""
    if request.url.path == "/chat":
        code = _message_validation_code(exc)
        if code is not None:
            LOGGER.info("rejected a chat request: %s", code)
            return JSONResponse(status_code=422, content={"detail": code})
    return await request_validation_exception_handler(request, exc)


class ChatRequest(BaseModel):
    """The request body from docs/api-contract.md."""

    message: str = Field(..., max_length=answer.MAX_QUESTION_CHARS)
    # Accepted so a client can keep its conversation id; the endpoint keeps no
    # history yet, so the value is not used.
    session_id: str | None = Field(default=None, max_length=128)

    @field_validator("message")
    @classmethod
    def _message_is_not_blank(cls, value: str) -> str:
        """An empty or whitespace-only question is a 422, not a model call."""
        message = value.strip()
        if not message:
            raise ValueError("message_empty")
        return message


class CitationModel(BaseModel):
    """One cited article, in the contract's field order."""

    title: str
    article: int | None
    url: str


class ChatResponse(BaseModel):
    """The response body from docs/api-contract.md."""

    answer: str
    citations: list[CitationModel]


@lru_cache
def get_config() -> answer.ChatConfig:
    """The chat config, read from backend/config/chat.toml once."""
    return answer.load_config()


@lru_cache
def get_retriever() -> answer.Retriever:
    """The retriever for the configured source; the index loads on first use."""
    return answer.make_searcher(get_config().source_id)


@lru_cache
def get_client():
    """The chat client; the key is read from .env here and nowhere else."""
    return answer.make_client(get_config())


@app.post("/chat", response_model=ChatResponse, dependencies=[Depends(require_user)])
def chat(request: ChatRequest) -> ChatResponse:
    """Answer one question from the regulation and cite the articles used.

    Only for a signed-in student: require_user answers 401 before this runs.
    """
    # Built here rather than through Depends: FastAPI solves dependencies before
    # the request body, so a dependency would load the index and the model client
    # for a body it then rejects with a 422. Called after validation, a rejected
    # request costs nothing.
    retriever = get_retriever()
    client = get_client()
    try:
        result = answer.answer_question(
            request.message,
            retriever=retriever,
            client=client,
            config=get_config(),
        )
    except answer.ModelUnavailable as exc:
        LOGGER.error("chat failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="the answer service is unavailable; please try again",
        ) from exc
    except (OSError, ValueError, RuntimeError) as exc:
        # Retrieval or index trouble: say the service is down rather than answer
        # without the regulation behind it.
        LOGGER.error("chat failed: %s: %s", type(exc).__name__, exc)
        raise HTTPException(
            status_code=503,
            detail="the answer service is unavailable; please try again",
        ) from exc

    LOGGER.info(
        "answered a %d-character question with %d citation(s)",
        len(request.message),
        len(result.citations),
    )
    return ChatResponse(
        answer=result.answer,
        citations=[
            CitationModel(
                title=citation.title,
                article=citation.article,
                url=citation.url,
            )
            for citation in result.citations
        ],
    )
