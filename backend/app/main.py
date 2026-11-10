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
from pydantic import BaseModel, Field, field_validator

import answer

LOGGER = logging.getLogger(__name__)

app = FastAPI(title="KSU Agent", version="0.1.0")


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
            raise ValueError("message must not be empty")
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


@app.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    retriever: answer.Retriever = Depends(get_retriever),
    client: object = Depends(get_client),
) -> ChatResponse:
    """Answer one question from the regulation and cite the articles used."""
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
