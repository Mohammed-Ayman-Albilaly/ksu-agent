#!/usr/bin/env python3
"""Answer a student's question from the retrieved regulation articles.

Retrieval is retrieve.py's job; this module only builds the prompt and calls the
chat model. The prompt contains nothing but the question and the top-k retrieved
articles — each with its article number, heading and URL — and asks for an Arabic
answer that cites those article numbers. The model is told to say so when the
articles do not support an answer; in that case the exact FALLBACK_ANSWER is
returned with no citations, so the user never sees an uncited claim.

The model, temperature, output limit and prices come from
backend/config/chat.toml. The API key is read from OPENAI_API_KEY in the repo-root
.env (see .env.example) and is never logged, printed or returned.

Usage:
    python backend/scripts/answer.py --source-id ref-01 --question "..." [--k 5]
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from embed_chunks import api_key
from fetch_sources import REPO_ROOT
from retrieve import DEFAULT_K, SearchResult, make_searcher

LOGGER = logging.getLogger(__name__)

DEFAULT_CONFIG = REPO_ROOT / "backend" / "config" / "chat.toml"
REQUIRED_FIELDS = (
    "provider",
    "model",
    "temperature",
    "max_output_tokens",
    "price_per_1m_input",
    "price_per_1m_output",
    "source_id",
)
TOKENS_PER_PRICE_UNIT = 1_000_000
MAX_QUESTION_CHARS = 1000

# Shown when the retrieved articles do not support an answer. It is fixed text, not
# something the model writes, so the wording cannot drift between answers.
FALLBACK_ANSWER = (
    "لا تتوفر هذه المعلومة في لائحة الدراسة والاختبارات. "
    "يرجى التواصل مع عمادة القبول والتسجيل للاستفسار."
)

SYSTEM_PROMPT = (
    "أنت مساعد أكاديمي لطلاب كلية علوم الحاسب والمعلومات في جامعة الملك سعود.\n"
    "أجب باللغة العربية اعتمادًا على المواد المسترجعة المرفقة فقط، ولا تستخدم أي "
    "معلومة من خارجها ولا تخمّن ولا تكمل النقص من معرفتك العامة.\n"
    "إذا لم تكن المواد المرفقة كافية للإجابة عن السؤال، فأعد supported=false ونصًا "
    "فارغًا، وسيعرض النظام رسالة ثابتة للطالب.\n"
    "إذا ورد في المادة قاعدة تنفيذية أو استثناء يخص كلية علوم الحاسب والمعلومات "
    "فطبّقه واذكره، فهو الحكم الأدق لحالة الطالب.\n"
    "إذا كانت كافية، فأعد supported=true وإجابة موجزة، واذكر رقم المادة بعد كل معلومة "
    "تنقلها منها بهذه الصيغة: (المادة 62).\n"
    "لا تذكر رقم أي مادة غير موجودة في المواد المرفقة.\n"
    "أعد الإخراج بصيغة JSON فقط، بالحقلين supported و answer، دون أي نص آخر."
)

ARTICLE_TEMPLATE = """المادة {number}
العنوان: {heading}
الرابط: {url}
النص:
{text}"""

USER_PROMPT_TEMPLATE = """السؤال:
{question}

المواد المسترجعة (لا تستخدم غيرها):
{articles}"""

# Strict JSON schema: the answer is parsed, never scraped out of prose, so a
# malformed reply falls back instead of reaching the student.
ANSWER_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "regulation_answer",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "supported": {
                    "type": "boolean",
                    "description": "true only when the retrieved articles answer "
                    "the question",
                },
                "answer": {
                    "type": "string",
                    "description": "Arabic answer citing article numbers; empty "
                    "when supported is false",
                },
            },
            "required": ["supported", "answer"],
            "additionalProperties": False,
        },
    },
}

_ARTICLE_REFERENCE = re.compile(r"المادة\s*(?:رقم\s*)?([0-9\u0660-\u0669]+)")
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_CODE_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")

Retriever = Callable[[str, int], Sequence[SearchResult]]


class ModelUnavailable(RuntimeError):
    """The chat model could not be called or returned nothing usable."""


@dataclass(frozen=True)
class ChatConfig:
    """The chat model, its sampling settings and its prices, as configured."""

    provider: str
    model: str
    temperature: float
    max_output_tokens: int
    price_per_1m_input: float
    price_per_1m_output: float
    source_id: str
    timeout_seconds: float = 60.0
    max_retries: int = 3


@dataclass(frozen=True)
class Citation:
    """One cited article: the source's title, the article number and its URL."""

    title: str
    article: int | None
    url: str


@dataclass(frozen=True)
class Answer:
    """What the endpoint returns: the text and the articles behind it."""

    answer: str
    citations: tuple[Citation, ...]
    used_fallback: bool = False
    cost_usd: float | None = None


@dataclass(frozen=True)
class ModelAnswer:
    """The model's structured reply, after validation."""

    supported: bool
    answer: str


def load_config(config_path: Path = DEFAULT_CONFIG) -> ChatConfig:
    """Read and validate the chat config."""
    with Path(config_path).open("rb") as fh:
        data = tomllib.load(fh)

    section = data.get("chat")
    if not isinstance(section, dict):
        raise ValueError(f"{config_path}: no [chat] table found")

    missing = [field for field in REQUIRED_FIELDS if section.get(field) is None]
    if missing:
        raise ValueError(f"{config_path}: [chat] is missing {', '.join(missing)}")

    config = ChatConfig(
        provider=str(section["provider"]).strip(),
        model=str(section["model"]).strip(),
        temperature=float(section["temperature"]),
        max_output_tokens=int(section["max_output_tokens"]),
        price_per_1m_input=float(section["price_per_1m_input"]),
        price_per_1m_output=float(section["price_per_1m_output"]),
        source_id=str(section["source_id"]).strip(),
        timeout_seconds=float(section.get("timeout_seconds", 60.0)),
        max_retries=int(section.get("max_retries", 3)),
    )

    if not config.provider or not config.model or not config.source_id:
        raise ValueError(
            f"{config_path}: provider, model and source_id are required"
        )
    if not 0.0 <= config.temperature <= 2.0:
        raise ValueError(f"{config_path}: temperature must be between 0 and 2")
    if config.max_output_tokens < 1:
        raise ValueError(f"{config_path}: max_output_tokens must be positive")
    if config.price_per_1m_input < 0 or config.price_per_1m_output < 0:
        raise ValueError(f"{config_path}: prices must not be negative")
    if config.timeout_seconds <= 0 or config.max_retries < 0:
        raise ValueError(f"{config_path}: timeout and retries must be positive")

    return config


def make_client(config: ChatConfig):
    """OpenAI client for the configured provider; the key comes from .env."""
    from openai import OpenAI

    return OpenAI(
        api_key=api_key(),
        timeout=config.timeout_seconds,
        max_retries=config.max_retries,
    )


def format_articles(results: Sequence[SearchResult]) -> str:
    """The retrieved articles as prompt text: number, heading, URL, body.

    Chunks with no article number (the annex) are left out: the answer must cite
    article numbers, so a chunk that cannot be cited is not put in the prompt.
    """
    blocks: list[str] = []
    for result in results:
        number = result.article_number
        if number is None:
            continue
        blocks.append(
            ARTICLE_TEMPLATE.format(
                number=number,
                heading=result.chunk.heading or "—",
                url=result.chunk.url or "—",
                text=result.chunk.text,
            )
        )
    return "\n\n".join(blocks)


def build_messages(
    question: str, results: Sequence[SearchResult]
) -> list[dict] | None:
    """System and user messages, or None when no retrieved article can be cited."""
    articles = format_articles(results)
    if not articles:
        return None
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": USER_PROMPT_TEMPLATE.format(
                question=question, articles=articles
            ),
        },
    ]


def parse_model_answer(content: str | None) -> ModelAnswer | None:
    """The model's JSON reply, or None when it is missing or malformed.

    A malformed reply is not repaired and not guessed at: the caller falls back.
    """
    text = (content or "").strip()
    if not text:
        return None
    text = _CODE_FENCE.sub("", text).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None

    supported = data.get("supported")
    answer = data.get("answer")
    if not isinstance(supported, bool) or not isinstance(answer, str):
        return None
    return ModelAnswer(supported=supported, answer=answer.strip())


def cited_article_numbers(answer_text: str) -> set[int]:
    """Article numbers the answer names as "المادة N" (Western or Arabic digits)."""
    numbers: set[int] = set()
    for match in _ARTICLE_REFERENCE.finditer(answer_text or ""):
        digits = match.group(1).translate(_ARABIC_DIGITS)
        numbers.add(int(digits))
    return numbers


def citations_from(results: Sequence[SearchResult]) -> tuple[Citation, ...]:
    """One citation per retrieved article, in retrieval order."""
    citations: list[Citation] = []
    seen: set[int] = set()
    for result in results:
        number = result.article_number
        if number is None or number in seen:
            continue
        seen.add(number)
        citations.append(
            Citation(
                title=result.chunk.title,
                article=number,
                url=result.chunk.url,
            )
        )
    return tuple(citations)


def select_citations(
    answer_text: str, results: Sequence[SearchResult]
) -> tuple[Citation, ...]:
    """The retrieved articles the answer names, else every retrieved article.

    Every citation is therefore an article that was in the prompt; an answer that
    names no article is still cited against the articles it was allowed to use.
    """
    citations = citations_from(results)
    named = cited_article_numbers(answer_text)
    chosen = tuple(c for c in citations if c.article in named)
    return chosen or citations


def ask_model(
    config: ChatConfig, client, messages: list[dict]
) -> tuple[str | None, object | None]:
    """Call the chat model once; returns its text and usage.

    The SDK's own timeout and retry settings (from the config) have already been
    applied when this raises. The message names the model and the error type only:
    neither the prompt nor the API key is ever logged.
    """
    try:
        response = client.chat.completions.create(
            model=config.model,
            messages=messages,
            temperature=config.temperature,
            max_tokens=config.max_output_tokens,
            response_format=ANSWER_FORMAT,
        )
    except Exception as exc:  # network, timeout, rate limit, provider error
        raise ModelUnavailable(
            f"the chat model {config.model} failed: {type(exc).__name__}"
        ) from exc

    if not response.choices:
        raise ModelUnavailable(f"the chat model {config.model} returned no choice")
    return response.choices[0].message.content, getattr(response, "usage", None)


def estimate_cost(usage, config: ChatConfig) -> float | None:
    """USD spent on one call, from the configured prices; None without usage."""
    if usage is None:
        return None
    prompt_tokens = getattr(usage, "prompt_tokens", None)
    completion_tokens = getattr(usage, "completion_tokens", None)
    if prompt_tokens is None or completion_tokens is None:
        return None
    return (
        prompt_tokens / TOKENS_PER_PRICE_UNIT * config.price_per_1m_input
        + completion_tokens / TOKENS_PER_PRICE_UNIT * config.price_per_1m_output
    )


def answer_question(
    question: str,
    *,
    retriever: Retriever,
    client,
    config: ChatConfig,
    k: int = DEFAULT_K,
) -> Answer:
    """Retrieve, answer from the retrieved articles only, and cite them.

    The fallback is returned when nothing citable was retrieved, when the model says
    the articles do not support an answer, or when its reply cannot be parsed. A
    model call that fails raises ModelUnavailable instead: "the service is down" and
    "the regulation does not say" are different answers.
    """
    question = (question or "").strip()
    if not question:
        raise ValueError("question is empty")
    if len(question) > MAX_QUESTION_CHARS:
        raise ValueError(
            f"question is {len(question)} characters; the limit is "
            f"{MAX_QUESTION_CHARS}"
        )

    results = list(retriever(question, k))
    messages = build_messages(question, results)
    if messages is None:
        LOGGER.info("nothing citable retrieved; returning the fallback answer")
        return Answer(answer=FALLBACK_ANSWER, citations=(), used_fallback=True)

    content, usage = ask_model(config, client, messages)
    parsed = parse_model_answer(content)
    if parsed is None or not parsed.supported or not parsed.answer:
        LOGGER.warning("the model returned no supported answer; using the fallback")
        return Answer(answer=FALLBACK_ANSWER, citations=(), used_fallback=True)

    citations = select_citations(parsed.answer, results)
    cost = estimate_cost(usage, config)
    LOGGER.info(
        "answered %d chars from %d retrieved article(s)%s",
        len(parsed.answer),
        len(citations),
        f"; estimated cost ${cost:.6f}" if cost is not None else "",
    )
    return Answer(answer=parsed.answer, citations=citations, cost_usd=cost)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Answer one question from the retrieved regulation articles."
    )
    parser.add_argument(
        "--source-id",
        required=True,
        help="id of the indexed source, e.g. ref-01",
    )
    parser.add_argument("--question", required=True, help="the student's question")
    parser.add_argument(
        "--k",
        type=int,
        default=DEFAULT_K,
        help=f"articles to retrieve (default: {DEFAULT_K})",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"chat config file (default: {DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the docs/api-contract.md response shape as JSON",
    )
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
        retriever = make_searcher(args.source_id)
        client = make_client(config)
        result = answer_question(
            args.question,
            retriever=retriever,
            client=client,
            config=config,
            k=args.k,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        payload = {
            "answer": result.answer,
            "citations": [
                {
                    "title": citation.title,
                    "article": citation.article,
                    "url": citation.url,
                }
                for citation in result.citations
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(result.answer)
    if result.citations:
        print()
        for citation in result.citations:
            print(f"  article {citation.article}  {citation.title}")
            print(f"  {citation.url}")
    else:
        print("\n  (no citations)")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
