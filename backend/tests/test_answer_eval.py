"""Tests for eval/run_answer_eval.py — a fake LLM and a fake retriever, so no network.

The scoring and reporting functions take the answer as a callable, and the
pipeline is exercised through ``make_answer_fn`` with a fake retriever and a fake
chat client. Nothing here loads an index, calls a provider or reads the .env file.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

EVAL_DIR = Path(__file__).resolve().parents[2] / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import answer  # noqa: E402
import retrieve  # noqa: E402
import run_answer_eval as ev  # noqa: E402
import run_retrieval_eval  # noqa: E402

TITLE = "KSU Regulations of Study and Examinations"
URL = "https://dar.ksu.edu.sa/regulations.pdf"
GRADUATION_TEXT = "الحد الأدنى للمعدل التراكمي المطلوب للتخرج هو 2,75 من 5,00."


# --- fakes ----------------------------------------------------------------


class FakeCompletions:
    """Stands in for client.chat.completions and records every request."""

    def __init__(self, content=None, error=None):
        self.content = content
        self.error = error
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        usage = SimpleNamespace(prompt_tokens=1000, completion_tokens=100)
        message = SimpleNamespace(content=self.content, refusal=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


class FakeChatClient:
    """Stands in for openai.OpenAI, exposing only chat.completions."""

    def __init__(self, content=None, error=None):
        self.completions = FakeCompletions(content, error)
        self.chat = SimpleNamespace(completions=self.completions)

    @property
    def calls(self):
        return self.completions.calls


class FakeRetriever:
    """Returns fixed SearchResults and records the questions it was asked."""

    def __init__(self, results):
        self.results = list(results)
        self.queries = []

    def __call__(self, question, k=retrieve.DEFAULT_K):
        self.queries.append((question, k))
        return self.results[:k]


def search_result(number, text=GRADUATION_TEXT):
    chunk = retrieve.Chunk(
        index=number if number is not None else 0,
        article_number=number,
        heading=f"المادة {number}" if number is not None else "الملحقات",
        text=text,
        title=TITLE,
        url=URL,
    )
    return retrieve.SearchResult(score=0.9, chunk=chunk)


def make_config(**overrides):
    values = {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "temperature": 0.0,
        "max_output_tokens": 700,
        "price_per_1m_input": 0.15,
        "price_per_1m_output": 0.60,
        "source_id": "ref-01",
    }
    values.update(overrides)
    return answer.ChatConfig(**values)


def reply(supported, text):
    return json.dumps({"supported": supported, "answer": text}, ensure_ascii=False)


def make_question(qid, expected, question="سؤال"):
    return ev.Question(
        id=qid, question=question, expected_articles=tuple(expected), note=""
    )


def make_row(qid, expected, cited=(), *, used_fallback=False, latency_ms=100.0,
             cost_usd=None, answer_text="نص"):
    return ev.Row(
        question=make_question(qid, expected),
        answer=answer_text,
        cited_articles=tuple(cited),
        used_fallback=used_fallback,
        latency_ms=latency_ms,
        cost_usd=cost_usd,
    )


# --- the question set -----------------------------------------------------


def test_the_run_holds_the_golden_questions_plus_the_unanswerable_one():
    questions = ev.load_questions()

    assert [question.id for question in questions] == [
        f"q{i}" for i in range(1, 12)
    ]
    assert questions[-1] is ev.UNANSWERABLE_QUESTION
    assert questions[-1].question == "متى حفل التخرج؟"
    assert questions[-1].expected_articles == ()


def test_the_golden_file_itself_is_unchanged():
    """The unanswerable question is added by the eval, not written to the file."""
    assert len(run_retrieval_eval.load_questions()) == 10


# --- scoring --------------------------------------------------------------


def test_has_citation_reads_the_cited_articles():
    assert make_row("q1", [25], cited=[25]).has_citation is True
    assert make_row("q1", [25], cited=[]).has_citation is False


def test_expected_article_cited_is_true_for_any_expected_article():
    assert make_row("q1", [25, 26], cited=[26]).expected_article_cited is True
    assert make_row("q1", [25, 26], cited=[25, 47]).expected_article_cited is True


def test_expected_article_cited_is_false_when_only_other_articles_are_cited():
    assert make_row("q1", [25], cited=[12, 47]).expected_article_cited is False


def test_expected_article_cited_is_false_for_an_unanswerable_question():
    """No expected article, so citing anything is a wrong answer, not a hit."""
    assert make_row("q11", [], cited=[8]).expected_article_cited is False


def test_citation_presence_is_the_share_of_answers_with_a_citation():
    rows = [
        make_row("q1", [25], cited=[25]),
        make_row("q2", [32], cited=[]),
        make_row("q3", [54], cited=[54, 55]),
        make_row("q4", [56], cited=[]),
    ]

    assert ev.citation_presence(rows) == pytest.approx(0.5)


def test_citation_presence_of_an_empty_run_is_zero():
    assert ev.citation_presence([]) == 0.0


def test_expected_article_rate_ignores_unanswerable_questions():
    rows = [
        make_row("q1", [25], cited=[25]),
        make_row("q2", [32], cited=[12]),
        make_row("q11", [], cited=[]),
    ]

    assert ev.expected_article_rate(rows) == pytest.approx(0.5)


def test_expected_article_rate_of_no_answerable_questions_is_zero():
    assert ev.expected_article_rate([make_row("q11", [], cited=[])]) == 0.0


# --- latency --------------------------------------------------------------


def test_percentile_interpolates_like_numpy():
    assert ev.percentile([4, 1, 3, 2], 0.5) == pytest.approx(2.5)
    assert ev.percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 0.95) == pytest.approx(9.55)


def test_percentile_of_one_value_is_that_value():
    assert ev.percentile([42.0], 0.95) == 42.0


def test_percentile_of_no_values_is_zero():
    assert ev.percentile([], 0.5) == 0.0
    assert ev.median_latency([]) == 0.0
    assert ev.p95_latency([]) == 0.0


def test_percentile_rejects_a_fraction_outside_zero_to_one():
    with pytest.raises(ValueError, match="between 0 and 1"):
        ev.percentile([1.0], 1.5)


def test_median_and_p95_use_every_latency():
    rows = [make_row(f"q{i}", [1], latency_ms=float(i)) for i in range(1, 11)]

    assert ev.median_latency(rows) == pytest.approx(5.5)
    assert ev.p95_latency(rows) == pytest.approx(9.55)


# --- evaluation -----------------------------------------------------------


def test_evaluate_records_citations_latency_and_order():
    questions = [
        make_question("q1", [25], question="سؤال عن التخرج"),
        make_question("q2", [32], question="سؤال عن الاختبار البديل"),
    ]
    seen = []

    def fake_answer(question, k):
        seen.append((question, k))
        if question == "سؤال عن التخرج":
            return answer.Answer(
                answer="نص الإجابة (المادة 25)",
                citations=(answer.Citation(title=TITLE, article=25, url=URL),),
                cost_usd=0.0002,
            )
        return answer.Answer(
            answer=answer.FALLBACK_ANSWER, citations=(), used_fallback=True
        )

    rows = ev.evaluate(questions, fake_answer, k=3)

    assert [row.question.id for row in rows] == ["q1", "q2"]
    assert seen == [("سؤال عن التخرج", 3), ("سؤال عن الاختبار البديل", 3)]
    assert rows[0].cited_articles == (25,)
    assert rows[0].has_citation is True
    assert rows[0].cost_usd == pytest.approx(0.0002)
    assert rows[0].latency_ms >= 0.0
    assert rows[1].cited_articles == ()
    assert rows[1].used_fallback is True
    assert rows[1].cost_usd is None


def test_evaluate_records_a_model_failure_and_keeps_going():
    questions = [make_question("q1", [25]), make_question("q2", [32])]
    asked = []

    def flaky_answer(question, k):
        asked.append(question)
        if len(asked) == 1:
            raise answer.ModelUnavailable("the chat model gpt-4o-mini failed")
        return answer.Answer(
            answer="نص (المادة 32)",
            citations=(answer.Citation(title=TITLE, article=32, url=URL),),
        )

    rows = ev.evaluate(questions, flaky_answer)

    assert rows[0].error.startswith("the chat model")
    assert rows[0].answer == ""
    assert rows[0].has_citation is False
    assert rows[0].latency_ms >= 0.0
    assert rows[1].error == ""
    assert rows[1].cited_articles == (32,)

def test_answerable_question_cites_the_expected_article_and_is_priced():
    retriever = FakeRetriever([search_result(62)])
    client = FakeChatClient(
        reply(True, "الحد الأدنى للمعدل التراكمي للتخرج هو 2,75 (المادة 62).")
    )
    answer_fn = ev.make_answer_fn(make_config(), retriever=retriever, client=client)

    result = answer_fn("كم المعدل المطلوب عشان أتخرج؟", 5)

    assert result.used_fallback is False
    assert [citation.article for citation in result.citations] == [62]
    # 1000 prompt tokens at $0.15/1M + 100 completion tokens at $0.60/1M.
    assert result.cost_usd == pytest.approx(0.00021)
    assert retriever.queries == [("كم المعدل المطلوب عشان أتخرج؟", 5)]


def test_unsupported_reply_is_the_fallback_but_is_still_priced():
    """The model was called, so the run paid for it even though it fell back."""
    retriever = FakeRetriever([search_result(62)])
    client = FakeChatClient(reply(False, ""))
    answer_fn = ev.make_answer_fn(make_config(), retriever=retriever, client=client)

    result = answer_fn("كم رسوم الساعة المعتمدة؟", 5)

    assert result.answer == answer.FALLBACK_ANSWER
    assert result.citations == ()
    assert result.used_fallback is True
    assert result.cost_usd == pytest.approx(0.00021)


def test_unanswerable_question_returns_the_fallback_with_no_citations():
    retriever = FakeRetriever([search_result(8, "مدة الدراسة أربعة أعوام.")])
    client = FakeChatClient(reply(False, ""))
    answer_fn = ev.make_answer_fn(make_config(), retriever=retriever, client=client)

    result = answer_fn(ev.UNANSWERABLE_QUESTION.question, 5)

    assert result.answer == answer.FALLBACK_ANSWER
    assert result.citations == ()
    assert result.used_fallback is True


def test_pipeline_row_scores_the_unanswerable_question_as_a_fallback():
    retriever = FakeRetriever([search_result(8)])
    client = FakeChatClient(reply(False, ""))
    answer_fn = ev.make_answer_fn(make_config(), retriever=retriever, client=client)

    rows = ev.evaluate([ev.UNANSWERABLE_QUESTION], answer_fn, k=5)

    assert rows[0].used_fallback is True
    assert rows[0].has_citation is False
    assert rows[0].expected_article_cited is False
    assert ev.fallback_failures(rows) == []


def test_fallback_failures_lists_an_unanswerable_question_that_answered():
    rows = [
        make_row("q11", [], cited=[8]),
        make_row("q12", [], cited=[], used_fallback=True),
    ]

    assert [row.question.id for row in ev.fallback_failures(rows)] == ["q11"]


# --- cost -----------------------------------------------------------------


def test_total_cost_sums_only_the_rows_that_called_the_model():
    rows = [
        make_row("q1", [25], cited=[25], cost_usd=0.0002),
        make_row("q2", [32], cited=[], used_fallback=True, cost_usd=0.0001),
        make_row("q3", [54], cited=[]),
    ]

    assert ev.total_cost(rows) == pytest.approx(0.0003)
    assert ev.model_calls(rows) == 2
    assert ev.total_cost([]) == 0.0


# --- report ---------------------------------------------------------------


def test_report_prints_the_table_and_the_summary(capsys):
    rows = [
        make_row("q1", [25], cited=[25], latency_ms=100.0, cost_usd=0.0002,
                 answer_text="الحد الأدنى 2,75 (المادة 25)."),
        make_row("q2", [32], cited=[12], latency_ms=300.0, cost_usd=0.0001,
                 answer_text="إجابة عن المادة 12."),
        make_row("q11", [], cited=[], used_fallback=True, latency_ms=200.0),
    ]

    ev.report(rows, make_config(), k=5)

    out = capsys.readouterr().out
    assert "q1   yes  yes  no" in out
    assert "q2   yes  no" in out
    assert "q11  no   -    yes" in out
    assert "citation_presence 2/3 (0.67)" in out
    assert "expected_article_cited 1/2 (0.50)" in out
    assert "latency median 200 ms, p95 290 ms" in out
    assert "estimated cost $0.000300" in out
    assert "2 model calls" in out
    assert "gpt-4o-mini" in out
    assert "unanswerable questions: fallback with no citations on every one" in out


def test_report_names_an_unanswerable_question_that_did_not_fall_back(capsys):
    rows = [make_row("q11", [], cited=[8], answer_text="حفل التخرج في مايو (المادة 8).")]

    ev.report(rows, make_config())

    out = capsys.readouterr().out
    assert "unanswerable questions not returned as the bare fallback: q11" in out


def test_report_truncates_a_long_answer(capsys):
    rows = [make_row("q1", [25], cited=[25], answer_text="س" * 200)]

    ev.report(rows, make_config())

    out = capsys.readouterr().out
    assert "س" * 200 not in out
    assert "…" in out


def test_the_eval_defaults_to_the_retrieval_k():
    assert ev.DEFAULT_K == retrieve.DEFAULT_K
