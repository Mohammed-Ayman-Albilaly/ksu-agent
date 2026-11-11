#!/usr/bin/env python3
"""Measure answer quality on the golden question set.

For every question in eval/questions_regulation.json the answer pipeline
(answer.py) is run end to end: retrieve the top ``k`` articles, call the chat
model, parse its reply and cite the articles. For each question the run records

* the answer text the student would see,
* the cited article numbers (the citations the pipeline returns),
* whether there is any citation at all,
* whether one of the question's expected articles is among them,
* the latency of the whole pipeline call, in milliseconds,
* the estimated cost of the model call, from the prices in chat.toml.

One extra question is appended to the golden set: "متى حفل التخرج؟" (when is the
graduation ceremony?). The regulation does not answer it, so the pipeline must
return the fixed fallback text with no citations. That case is reported on its
own line, because a fallback is a correct answer there while a fallback on a
golden question is a miss.

The run ends with citation_presence, expected_article_cited, the median and p95
latency, and the estimated cost of the run. Answering is non-deterministic, so
these are rates over the set, never an exact-text comparison.

The scoring functions take the answer as a callable, so the tests run offline
with a fake retriever and a fake chat client and never touch a provider.

Usage:
    python eval/run_answer_eval.py --source-id ref-01
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = REPO_ROOT / "backend" / "scripts"
for directory in (EVAL_DIR, SCRIPTS_DIR):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import answer  # noqa: E402  (needs backend/scripts on sys.path)
import retrieve  # noqa: E402
import run_retrieval_eval  # noqa: E402  (golden-set loader, same eval package)

Question = run_retrieval_eval.Question

DEFAULT_QUESTIONS = REPO_ROOT / "eval" / "questions_regulation.json"
DEFAULT_K = retrieve.DEFAULT_K

# The regulation says nothing about a graduation ceremony, so this must come back
# as the fixed fallback text with no citations. It is not in the golden JSON file:
# that file holds questions the regulation answers, and run_retrieval_eval.py reads
# the same file for its hit@k.
UNANSWERABLE_QUESTION = Question(
    id="q11",
    question="متى حفل التخرج؟",
    expected_articles=(),
    note="غير موجودة في اللائحة: يجب أن تعود بالنص الاحتياطي دون أي استشهاد.",
)

AnswerFn = Callable[[str, int], answer.Answer]


@dataclass(frozen=True)
class Row:
    """The outcome for one question."""

    question: Question
    answer: str
    cited_articles: tuple[int, ...]
    used_fallback: bool
    latency_ms: float
    cost_usd: float | None = None
    error: str = ""

    @property
    def answerable(self) -> bool:
        """Whether the golden set expects the regulation to answer this question."""
        return bool(self.question.expected_articles)

    @property
    def has_citation(self) -> bool:
        return bool(self.cited_articles)

    @property
    def expected_article_cited(self) -> bool:
        """Whether a cited article is one the question should be answered from.

        An unanswerable question has no expected article, so this is False for it:
        citing anything there would be a wrong answer, not a hit.
        """
        return any(
            article in self.cited_articles
            for article in self.question.expected_articles
        )


class MeteredClient:
    """Wraps the chat client and keeps the usage of every call it makes.

    answer.py drops the usage when it returns the fallback, so the cost of a call
    the model answered "unsupported" to would otherwise go unrecorded. Metering the
    client instead prices every call the run actually made.
    """

    def __init__(self, client):
        self._client = client
        self.usages: list = []
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create)
        )

    def _create(self, **kwargs):
        response = self._client.chat.completions.create(**kwargs)
        self.usages.append(getattr(response, "usage", None))
        return response

    def usages_since(self, position: int) -> list:
        """The usages recorded since ``position`` (a previous len of usages)."""
        return self.usages[position:]


def load_questions(path: Path = DEFAULT_QUESTIONS) -> list[Question]:
    """The golden questions, with the unanswerable question last."""
    return [*run_retrieval_eval.load_questions(path), UNANSWERABLE_QUESTION]


def percentile(values: Sequence[float], fraction: float) -> float:
    """The ``fraction`` percentile of ``values``, linear interpolation.

    Same definition as numpy's default: for a one-value sample the value itself.
    """
    if not 0.0 <= fraction <= 1.0:
        raise ValueError("fraction must be between 0 and 1")
    ordered = sorted(values)
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return float(ordered[0])

    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    weight = position - lower
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * weight)


def evaluate(
    questions: Sequence[Question], answer_fn: AnswerFn, *, k: int = DEFAULT_K
) -> list[Row]:
    """Run every question through ``answer_fn(question, k)`` and time it.

    A model failure is recorded as an error row and the run continues: one
    unavailable call should not throw away the rest of the measurements.
    """
    rows: list[Row] = []
    for question in questions:
        started = time.perf_counter()
        try:
            result = answer_fn(question.question, k)
        except answer.ModelUnavailable as exc:
            rows.append(
                Row(
                    question=question,
                    answer="",
                    cited_articles=(),
                    used_fallback=False,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    error=str(exc),
                )
            )
            continue

        rows.append(
            Row(
                question=question,
                answer=result.answer,
                cited_articles=tuple(
                    citation.article
                    for citation in result.citations
                    if citation.article is not None
                ),
                used_fallback=result.used_fallback,
                latency_ms=(time.perf_counter() - started) * 1000,
                cost_usd=result.cost_usd,
            )
        )
    return rows


def citation_presence(rows: Sequence[Row]) -> float:
    """Share of questions whose answer carries at least one citation."""
    if not rows:
        return 0.0
    return sum(1 for row in rows if row.has_citation) / len(rows)


def expected_article_rate(rows: Sequence[Row]) -> float:
    """Share of answerable questions citing one of their expected articles."""
    answerable = [row for row in rows if row.answerable]
    if not answerable:
        return 0.0
    hits = sum(1 for row in answerable if row.expected_article_cited)
    return hits / len(answerable)


def median_latency(rows: Sequence[Row]) -> float:
    return percentile([row.latency_ms for row in rows], 0.5)


def p95_latency(rows: Sequence[Row]) -> float:
    return percentile([row.latency_ms for row in rows], 0.95)


def total_cost(rows: Sequence[Row]) -> float:
    """Estimated USD for the run; rows that never called the model cost nothing."""
    return sum(row.cost_usd for row in rows if row.cost_usd is not None)


def model_calls(rows: Sequence[Row]) -> int:
    """Rows that reached the model (a row with no cost never did)."""
    return sum(1 for row in rows if row.cost_usd is not None)


def fallback_failures(rows: Sequence[Row]) -> list[Row]:
    """Unanswerable questions that did not come back as the bare fallback."""
    return [
        row
        for row in rows
        if not row.answerable
        and (not row.used_fallback or row.has_citation or row.error)
    ]


def make_answer_fn(
    config: answer.ChatConfig,
    *,
    source_id: str | None = None,
    client=None,
    retriever=None,
    config_path: Path = retrieve.DEFAULT_CONFIG,
    chunks_dir: Path = retrieve.DEFAULT_CHUNKS_DIR,
    index_dir: Path = retrieve.DEFAULT_INDEX_DIR,
) -> AnswerFn:
    """The real pipeline as ``answer_fn(question, k)``, with per-question cost.

    The retriever and client are injectable so the tests run offline with fakes.
    """
    retriever = retriever or retrieve.make_searcher(
        source_id or config.source_id,
        config_path=config_path,
        chunks_dir=chunks_dir,
        index_dir=index_dir,
    )
    metered = MeteredClient(client or answer.make_client(config))

    def answer_fn(question: str, k: int = DEFAULT_K) -> answer.Answer:
        before = len(metered.usages)
        result = answer.answer_question(
            question, retriever=retriever, client=metered, config=config, k=k
        )
        usages = metered.usages_since(before)
        cost = (
            sum(answer.estimate_cost(usage, config) or 0.0 for usage in usages)
            if usages
            else None
        )
        return replace(result, cost_usd=cost)

    return answer_fn


def _one_line(text: str, limit: int = 60) -> str:
    """The answer on one line, cut at ``limit`` characters for the table."""
    flat = " ".join((text or "").split())
    if len(flat) <= limit:
        return flat
    return flat[:limit].rstrip() + "…"


def report(
    rows: Sequence[Row], config: answer.ChatConfig, k: int = DEFAULT_K
) -> None:
    """Print one line per question, then the metrics for the whole run."""
    print(
        f"{'id':<4} {'any':<4} {'exp':<4} {'fb':<4} {'ms':>6}  "
        f"{'cites':<14} answer"
    )
    for row in rows:
        cites = ", ".join(str(article) for article in row.cited_articles) or "-"
        expected = "yes" if row.expected_article_cited else ("-" if not row.answerable else "no")
        print(
            f"{row.question.id:<4} "
            f"{'yes' if row.has_citation else 'no':<4} "
            f"{expected:<4} "
            f"{'yes' if row.used_fallback else 'no':<4} "
            f"{row.latency_ms:>6.0f}  "
            f"{cites:<14} "
            f"{_one_line(row.error or row.answer)}"
        )

    answerable = [row for row in rows if row.answerable]
    cited = sum(1 for row in rows if row.has_citation)
    hits = sum(1 for row in answerable if row.expected_article_cited)
    print()
    print(f"citation_presence {cited}/{len(rows)} ({citation_presence(rows):.2f})")
    print(
        f"expected_article_cited {hits}/{len(answerable)} "
        f"({expected_article_rate(rows):.2f})"
    )
    print(
        f"latency median {median_latency(rows):.0f} ms, "
        f"p95 {p95_latency(rows):.0f} ms ({len(rows)} questions, k={k})"
    )
    print(
        f"estimated cost ${total_cost(rows):.6f} "
        f"({len(rows)} questions, {model_calls(rows)} model calls; "
        f"${config.price_per_1m_input}/{config.price_per_1m_output} per 1M "
        f"tokens from chat.toml, model {config.model})"
    )

    failed = fallback_failures(rows)
    if failed:
        print(
            "unanswerable questions not returned as the bare fallback: "
            + ", ".join(row.question.id for row in failed)
        )
    else:
        print("unanswerable questions: fallback with no citations on every one")


def _use_utf8_stdout() -> None:
    """Write the Arabic answer column even on a legacy (cp1252) Windows console."""
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is None:
        return
    try:
        reconfigure(encoding="utf-8", errors="replace")
    except (OSError, ValueError):  # redirected or already closed
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Answer the golden question set and report citation and latency "
        "metrics."
    )
    parser.add_argument(
        "--source-id",
        default=None,
        help="id of the indexed source (default: source_id from chat.toml)",
    )
    parser.add_argument(
        "--questions",
        type=Path,
        default=DEFAULT_QUESTIONS,
        help=f"golden question file (default: {DEFAULT_QUESTIONS})",
    )
    parser.add_argument(
        "--k",
        type=int,
        default=DEFAULT_K,
        help=f"articles retrieved per question (default: {DEFAULT_K})",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=answer.DEFAULT_CONFIG,
        help=f"chat config file (default: {answer.DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "--embeddings-config",
        type=Path,
        default=retrieve.DEFAULT_CONFIG,
        help=f"embedding config file (default: {retrieve.DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "--chunks-dir",
        type=Path,
        default=retrieve.DEFAULT_CHUNKS_DIR,
        help=f"chunk directory (default: {retrieve.DEFAULT_CHUNKS_DIR})",
    )
    parser.add_argument(
        "--index-dir",
        type=Path,
        default=retrieve.DEFAULT_INDEX_DIR,
        help=f"index directory (default: {retrieve.DEFAULT_INDEX_DIR})",
    )
    args = parser.parse_args(argv)
    _use_utf8_stdout()

    try:
        config = answer.load_config(args.config)
        questions = load_questions(args.questions)
        answer_fn = make_answer_fn(
            config,
            source_id=args.source_id,
            config_path=args.embeddings_config,
            chunks_dir=args.chunks_dir,
            index_dir=args.index_dir,
        )
        rows = evaluate(questions, answer_fn, k=args.k)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    report(rows, config, args.k)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
