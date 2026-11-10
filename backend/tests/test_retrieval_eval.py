"""Tests for eval/run_retrieval_eval.py — offline, with a fake retriever.

The scoring functions take the search as a callable, so nothing here loads an
index, calls the embedding provider or reads the .env file.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

EVAL_DIR = Path(__file__).resolve().parents[2] / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import run_retrieval_eval as ev  # noqa: E402


def make_question(qid, expected, question="سؤال"):
    return ev.Question(
        id=qid, question=question, expected_articles=tuple(expected), note=""
    )


def result(article_number):
    return SimpleNamespace(article_number=article_number)


def fake_search(table):
    """A search stand-in: question text -> list of article numbers."""
    calls = []

    def search(question, k=ev.DEFAULT_K):
        calls.append((question, k))
        return [result(article) for article in table[question][:k]]

    search.calls = calls
    return search


# --- golden set -----------------------------------------------------------


def test_shipped_golden_set_has_the_ten_questions():
    questions = ev.load_questions()

    assert [question.id for question in questions] == [f"q{i}" for i in range(1, 11)]
    assert {question.id: question.expected_articles for question in questions} == {
        "q1": (25, 26),
        "q2": (32,),
        "q3": (54,),
        "q4": (56,),
        "q5": (58,),
        "q6": (60,),
        "q7": (38,),
        "q8": (62,),
        "q9": (37,),
        "q10": (8,),
    }
    assert all(question.question for question in questions)
    assert all(question.note for question in questions)


def test_golden_set_ids_are_unique(tmp_path):
    path = tmp_path / "questions.json"
    path.write_text(
        json.dumps(
            [
                {"id": "q1", "question": "a", "expected_articles": [1]},
                {"id": "q1", "question": "b", "expected_articles": [2]},
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate id"):
        ev.load_questions(path)


def test_golden_set_item_without_expected_articles_is_rejected(tmp_path):
    path = tmp_path / "questions.json"
    path.write_text(
        json.dumps([{"id": "q1", "question": "a", "expected_articles": []}]),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="no expected_articles"):
        ev.load_questions(path)


# --- rank -----------------------------------------------------------------


def test_rank_is_the_position_of_the_expected_article():
    results = [result(12), result(25), result(47)]

    assert ev.rank_of_expected(results, [25]) == 2


def test_rank_uses_the_first_of_several_expected_articles():
    results = [result(12), result(26), result(25)]

    assert ev.rank_of_expected(results, [25, 26]) == 2


def test_rank_is_none_when_the_expected_article_is_absent():
    results = [result(12), result(47)]

    assert ev.rank_of_expected(results, [25]) is None


def test_rank_is_none_for_an_empty_result_list():
    assert ev.rank_of_expected([], [25]) is None


# --- evaluation -----------------------------------------------------------


def test_evaluate_asks_for_k_results_per_question_and_keeps_order():
    questions = [make_question("q1", [25]), make_question("q2", [32])]
    search = fake_search({"سؤال": [12, 25, 47]})

    rows = ev.evaluate(questions, search, k=5)

    assert [row.question.id for row in rows] == ["q1", "q2"]
    assert search.calls == [("سؤال", 5), ("سؤال", 5)]
    assert [row.rank for row in rows] == [2, None]
    assert rows[0].top_articles == (12, 25, 47)


def test_evaluate_only_keeps_the_top_k():
    questions = [make_question("q1", [25])]
    search = fake_search({"سؤال": [12, 47, 25]})

    rows = ev.evaluate(questions, search, k=2)

    assert rows[0].rank is None
    assert rows[0].top_articles == (12, 47)


def test_hit_rates_over_a_fixed_run():
    ranks = [1, 1, 2, 4, None, 3, 1, 5, 2, 6]
    rows = [
        ev.Row(question=make_question(f"q{index}", [1]), rank=rank, top_articles=())
        for index, rank in enumerate(ranks, start=1)
    ]

    assert ev.summarize(rows) == {
        "hit@1": pytest.approx(0.3),
        "hit@3": pytest.approx(0.6),
        "hit@5": pytest.approx(0.8),
    }


def test_hit_rate_of_an_empty_run_is_zero():
    assert ev.hit_rate([], 5) == 0.0
    assert ev.summarize([]) == {"hit@1": 0.0, "hit@3": 0.0, "hit@5": 0.0}


def test_misses_lists_questions_outside_the_top_k():
    rows = [
        ev.Row(question=make_question("q1", [1]), rank=1, top_articles=()),
        ev.Row(question=make_question("q2", [2]), rank=4, top_articles=()),
        ev.Row(question=make_question("q3", [3]), rank=None, top_articles=()),
    ]

    assert [row.question.id for row in ev.misses(rows, k=3)] == ["q2", "q3"]


# --- report ---------------------------------------------------------------


def test_report_prints_ranks_metrics_and_misses(capsys):
    rows = [
        ev.Row(question=make_question("q1", [25]), rank=1, top_articles=(25, 47)),
        ev.Row(question=make_question("q2", [32]), rank=None, top_articles=(12, 13)),
    ]

    ev.report(rows, k=5)

    out = capsys.readouterr().out
    assert "q1   rank 1" in out
    assert "q2   rank -" in out
    assert "hit@1 0.50" in out
    assert "hit@3 0.50" in out
    assert "hit@5 0.50" in out
    assert "missed at k=5: q2" in out
