#!/usr/bin/env python3
"""Measure retrieval quality on the golden question set.

For every question in eval/questions_regulation.json the top ``k`` chunks are
retrieved and the rank of the first expected article is recorded. The run ends
with hit@1, hit@3 and hit@5 over the whole set, plus the questions that missed
at k=5.

A question counts as a hit at k when any of its expected articles is among the
top k chunks; its rank is the position of the first one found.

``--mode`` selects the ranking measured — dense, lexical (BM25) or hybrid (RRF
fusion of the two) — exactly as retrieve.py does, so the same golden set can be
compared across the three rankers.

The scoring functions take the search as a callable, so the tests run offline
with a fake retriever and never touch the embedding provider.

Usage:
    python eval/run_retrieval_eval.py --source-id ref-01 --mode hybrid
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "backend" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import retrieve  # noqa: E402  (needs backend/scripts on sys.path)

DEFAULT_QUESTIONS = REPO_ROOT / "eval" / "questions_regulation.json"
DEFAULT_K = 5
HIT_THRESHOLDS = (1, 3, 5)
REQUIRED_FIELDS = ("id", "question", "expected_articles")


@dataclass(frozen=True)
class Question:
    """One golden question and the articles that should answer it."""

    id: str
    question: str
    expected_articles: tuple[int, ...]
    note: str = ""


@dataclass(frozen=True)
class Row:
    """The outcome for one question."""

    question: Question
    rank: int | None
    top_articles: tuple[int | None, ...]

    @property
    def hit_at_5(self) -> bool:
        return self.rank is not None and self.rank <= DEFAULT_K


def load_questions(path: Path = DEFAULT_QUESTIONS) -> list[Question]:
    """Read and validate the golden set."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"{path} not found")

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{path}: expected a non-empty list of questions")

    questions: list[Question] = []
    seen: set[str] = set()
    for position, item in enumerate(raw, start=1):
        missing = [field for field in REQUIRED_FIELDS if item.get(field) in (None, "")]
        if missing:
            raise ValueError(f"{path}: item {position} is missing {', '.join(missing)}")
        if item["id"] in seen:
            raise ValueError(f"{path}: duplicate id {item['id']!r}")
        seen.add(item["id"])

        expected = item["expected_articles"]
        if not isinstance(expected, list) or not expected:
            raise ValueError(f"{path}: {item['id']} has no expected_articles")
        if not all(isinstance(article, int) for article in expected):
            raise ValueError(f"{path}: {item['id']} has a non-integer article")

        questions.append(
            Question(
                id=str(item["id"]),
                question=str(item["question"]),
                expected_articles=tuple(expected),
                note=str(item.get("note", "")),
            )
        )

    return questions


def rank_of_expected(results: Sequence, expected_articles: Iterable[int]) -> int | None:
    """1-based rank of the first expected article in ``results``, else None."""
    expected = set(expected_articles)
    for position, result in enumerate(results, start=1):
        if result.article_number in expected:
            return position
    return None


def evaluate(
    questions: Sequence[Question],
    search: Callable[[str, int], Sequence],
    *,
    k: int = DEFAULT_K,
) -> list[Row]:
    """Run every question through ``search(question, k)`` and record its rank."""
    rows: list[Row] = []
    for question in questions:
        results = list(search(question.question, k))
        rows.append(
            Row(
                question=question,
                rank=rank_of_expected(results, question.expected_articles),
                top_articles=tuple(result.article_number for result in results),
            )
        )
    return rows


def hit_rate(rows: Sequence[Row], k: int) -> float:
    """Share of questions whose expected article is in the top ``k``."""
    if not rows:
        return 0.0
    hits = sum(1 for row in rows if row.rank is not None and row.rank <= k)
    return hits / len(rows)


def summarize(rows: Sequence[Row]) -> dict[str, float]:
    """hit@1, hit@3 and hit@5 for the whole run."""
    return {f"hit@{k}": hit_rate(rows, k) for k in HIT_THRESHOLDS}


def misses(rows: Sequence[Row], k: int = DEFAULT_K) -> list[Row]:
    """Questions whose expected article is not in the top ``k``."""
    return [row for row in rows if row.rank is None or row.rank > k]


def make_search(
    source_id: str,
    *,
    mode: str = retrieve.DEFAULT_MODE,
    config_path: Path = retrieve.DEFAULT_CONFIG,
    chunks_dir: Path = retrieve.DEFAULT_CHUNKS_DIR,
    index_dir: Path = retrieve.DEFAULT_INDEX_DIR,
    client=None,
) -> Callable[[str, int], list]:
    """Load the index once and return ``search(question, k)`` for one mode."""
    retrieve.check_mode(mode)
    config = retrieve.load_config(config_path)
    vectors, chunks, _metadata = retrieve.load_index(
        source_id, config, chunks_dir=chunks_dir, index_dir=index_dir
    )
    bm25 = retrieve.build_bm25_index(chunks)

    # Lexical search never calls the embedding provider, so it must not need a key.
    needs_embeddings = mode in (retrieve.MODE_DENSE, retrieve.MODE_HYBRID)
    client = client or (retrieve.make_client(config) if needs_embeddings else None)
    tokenizer = retrieve.make_tokenizer(config) if needs_embeddings else None

    def search(question: str, k: int = DEFAULT_K) -> list:
        return retrieve.search_chunks(
            question,
            vectors=vectors,
            chunks=chunks,
            bm25=bm25,
            mode=mode,
            config=config,
            client=client,
            tokenizer=tokenizer,
            k=k,
        )

    return search


def report(rows: Sequence[Row], k: int = DEFAULT_K, *, mode: str | None = None) -> None:
    """Print one line per question, the hit rates and the misses."""
    for row in rows:
        rank = str(row.rank) if row.rank is not None else "-"
        top = ", ".join(str(article) for article in row.top_articles)
        print(f"{row.question.id:<4} rank {rank:<2} top-{k}: {top}")

    metrics = summarize(rows)
    line = "  ".join(f"{name} {value:.2f}" for name, value in metrics.items())
    label = f" ({len(rows)} questions, k={k}"
    if mode:
        label += f", mode={mode}"
    print(f"\n{line}{label})")

    missed = misses(rows, k)
    if missed:
        print(f"missed at k={k}: " + ", ".join(row.question.id for row in missed))
    else:
        print(f"missed at k={k}: none")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report hit@1, hit@3 and hit@5 for the golden question set."
    )
    parser.add_argument(
        "--source-id",
        default="ref-01",
        help="id of the indexed source to search (default: ref-01)",
    )
    parser.add_argument(
        "--questions",
        type=Path,
        default=DEFAULT_QUESTIONS,
        help=f"golden question file (default: {DEFAULT_QUESTIONS})",
    )
    parser.add_argument(
        "--mode",
        choices=retrieve.MODES,
        default=retrieve.DEFAULT_MODE,
        help=f"ranking to measure (default: {retrieve.DEFAULT_MODE})",
    )
    parser.add_argument(
        "--k",
        type=int,
        default=DEFAULT_K,
        help=f"chunks retrieved per question (default: {DEFAULT_K})",
    )
    parser.add_argument(
        "--config",
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

    try:
        questions = load_questions(args.questions)
        search = make_search(
            args.source_id,
            mode=args.mode,
            config_path=args.config,
            chunks_dir=args.chunks_dir,
            index_dir=args.index_dir,
        )
        rows = evaluate(questions, search, k=args.k)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    report(rows, args.k, mode=args.mode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
