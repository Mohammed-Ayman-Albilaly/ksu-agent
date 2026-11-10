"""Tests for answer.py — a fake LLM and a fake retriever, so no network.

The retriever returns fixed SearchResults and the chat client returns a fixed
JSON reply with the OpenAI SDK's response shape. Nothing here depends on the real
model, the real index or a real API key.
"""

import json
from types import SimpleNamespace

import pytest

import answer
import retrieve

TITLE = "KSU Regulations of Study and Examinations"
URL = "https://dar.ksu.edu.sa/regulations.pdf"
GRADUATION_TEXT = "الحد الأدنى للمعدل التراكمي المطلوب للتخرج هو 2,75 من 5,00."
ABSENCE_TEXT = "يعد الطالب محروما إذا تجاوزت نسبة غيابه 25% من محاضرات المقرر."


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
        usage = SimpleNamespace(prompt_tokens=1200, completion_tokens=80)
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
    """A retriever that returns fixed results and records the questions."""

    def __init__(self, results):
        self.results = list(results)
        self.queries = []

    def __call__(self, question, k=retrieve.DEFAULT_K):
        self.queries.append((question, k))
        return self.results[:k]


def make_result(number, text, *, score=0.9, heading=None, title=TITLE, url=URL):
    """A SearchResult as retrieve.py returns it, carrying its citation fields."""
    chunk = retrieve.Chunk(
        index=number if number is not None else 0,
        article_number=number,
        heading=heading or f"المادة {number}",
        text=text,
        title=title,
        url=url,
    )
    return retrieve.SearchResult(score=score, chunk=chunk)


def write_config(path, **overrides):
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
    lines = ["[chat]"]
    lines += [f"{key} = {json.dumps(value)}" for key, value in values.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def reply(supported, text):
    """The model's structured reply as it arrives in message.content."""
    return json.dumps({"supported": supported, "answer": text}, ensure_ascii=False)


def run(
    tmp_path,
    question,
    results,
    content=None,
    *,
    error=None,
    k=retrieve.DEFAULT_K,
    **config_overrides,
):
    """Call answer_question with fakes; returns the Answer and the fake client."""
    client = FakeChatClient(content, error)
    retriever = FakeRetriever(results)
    result = answer.answer_question(
        question,
        retriever=retriever,
        client=client,
        config=answer.load_config(write_config(tmp_path / "chat.toml", **config_overrides)),
        k=k,
    )
    return result, client, retriever


# --- the two required behaviours -------------------------------------------


def test_answerable_question_returns_the_answer_with_citations(tmp_path):
    results = [
        make_result(62, GRADUATION_TEXT),
        make_result(26, ABSENCE_TEXT),
    ]

    result, client, retriever = run(
        tmp_path,
        "كم المعدل المطلوب عشان أتخرج؟",
        results,
        reply(True, "الحد الأدنى للمعدل التراكمي للتخرج هو 2,75 من 5,00 (المادة 62)."),
    )

    assert result.used_fallback is False
    assert "2,75" in result.answer
    assert [citation.article for citation in result.citations] == [62]
    assert result.citations[0].title == TITLE
    assert result.citations[0].url == URL
    assert retriever.queries == [("كم المعدل المطلوب عشان أتخرج؟", retrieve.DEFAULT_K)]
    assert len(client.calls) == 1


def test_unsupported_question_returns_the_fallback_without_citations(tmp_path):
    results = [make_result(62, GRADUATION_TEXT)]

    result, client, _retriever = run(
        tmp_path,
        "كم رسوم الساعة المعتمدة في التخصص؟",
        results,
        reply(False, ""),
    )

    assert result.answer == answer.FALLBACK_ANSWER
    assert result.citations == ()
    assert result.used_fallback is True
    # The fallback is the system's fixed text, not something the model wrote.
    assert "عمادة القبول والتسجيل" in result.answer
    assert client.calls[0]["model"] == "gpt-4o-mini"


def test_fallback_is_the_exact_text_and_is_cited_nowhere(tmp_path):
    result, _client, _retriever = run(
        tmp_path,
        "هل فيه مكافأة تفوق؟",
        [make_result(62, GRADUATION_TEXT)],
        reply(False, ""),
    )

    assert result.answer == (
        "لا تتوفر هذه المعلومة في لائحة الدراسة والاختبارات. "
        "يرجى التواصل مع عمادة القبول والتسجيل للاستفسار."
    )
    assert result.citations == ()


# --- the prompt -----------------------------------------------------------


def test_prompt_holds_only_the_retrieved_articles(tmp_path):
    results = [make_result(62, GRADUATION_TEXT)]
    other_article = "نص مادة لم تسترجع"

    _result, client, _retriever = run(
        tmp_path,
        "كم المعدل المطلوب عشان أتخرج؟",
        results,
        reply(True, "الحد الأدنى 2,75 (المادة 62)."),
    )

    messages = client.calls[0]["messages"]
    assert [message["role"] for message in messages] == ["system", "user"]
    assert messages[0]["content"] == answer.SYSTEM_PROMPT

    prompt = messages[1]["content"]
    assert "كم المعدل المطلوب عشان أتخرج؟" in prompt
    assert GRADUATION_TEXT in prompt
    # Article number, heading and URL, exactly as the prompt was specified.
    assert "المادة 62" in prompt
    assert "العنوان: المادة 62" in prompt
    assert URL in prompt
    assert other_article not in prompt

def test_system_prompt_asks_for_arabic_and_article_numbers():
    assert "أجب باللغة العربية" in answer.SYSTEM_PROMPT
    assert "المادة 62" in answer.SYSTEM_PROMPT
    assert "supported" in answer.SYSTEM_PROMPT


def test_system_prompt_applies_the_ccis_executive_rule():
    """The executive rules carry the CCIS-specific numbers (e.g. 2,75 to graduate)."""
    assert "قاعدة تنفيذية" in answer.SYSTEM_PROMPT
    assert "كلية علوم الحاسب والمعلومات" in answer.SYSTEM_PROMPT
    assert "supported" in answer.SYSTEM_PROMPT


def test_chunks_without_an_article_number_are_left_out(tmp_path):
    annex = make_result(None, "نص الملحق", heading="الملحقات")

    _result, client, _retriever = run(
        tmp_path,
        "سؤال",
        [annex],
        reply(False, ""),
    )

    # Nothing citable was retrieved, so the model is never called.
    assert client.calls == []


def test_annex_is_not_put_in_the_prompt_but_the_articles_are(tmp_path):
    annex = make_result(None, "نص الملحق", heading="الملحقات")

    _result, client, _retriever = run(
        tmp_path,
        "سؤال",
        [make_result(62, GRADUATION_TEXT), annex],
        reply(True, "الحد الأدنى 2,75 (المادة 62)."),
    )

    prompt = client.calls[0]["messages"][1]["content"]
    assert GRADUATION_TEXT in prompt
    assert "نص الملحق" not in prompt


# --- citations ------------------------------------------------------------


def test_citations_are_limited_to_the_articles_the_answer_names(tmp_path):
    results = [
        make_result(62, GRADUATION_TEXT),
        make_result(26, ABSENCE_TEXT),
    ]

    result, _client, _retriever = run(
        tmp_path,
        "كم المعدل المطلوب عشان أتخرج؟",
        results,
        reply(True, "الحد الأدنى 2,75 (المادة 62)."),
    )

    assert [citation.article for citation in result.citations] == [62]


def test_answer_naming_no_article_is_cited_against_the_retrieved_articles(tmp_path):
    results = [make_result(62, GRADUATION_TEXT), make_result(26, ABSENCE_TEXT)]

    result, _client, _retriever = run(
        tmp_path,
        "كم المعدل المطلوب عشان أتخرج؟",
        results,
        reply(True, "الحد الأدنى 2,75 من 5,00."),
    )

    assert [citation.article for citation in result.citations] == [62, 26]


def test_a_number_that_is_not_an_article_reference_is_not_cited(tmp_path):
    results = [make_result(62, GRADUATION_TEXT), make_result(26, ABSENCE_TEXT)]

    result, _client, _retriever = run(
        tmp_path,
        "كم المعدل المطلوب عشان أتخرج؟",
        results,
        reply(True, "المعدل 2,75 من 5,00 (المادة 62)."),
    )

    assert [citation.article for citation in result.citations] == [62]


def test_cited_article_numbers_reads_arabic_digits():
    assert answer.cited_article_numbers("(المادة ٦٢)") == {62}
    # A decimal such as 2,75 is not an article reference.
    assert answer.cited_article_numbers("المعدل 2,75 من 5,00") == set()
    assert answer.cited_article_numbers("(المادة 62) و(المادة ٢٦)") == {62, 26}


# --- failure handling -----------------------------------------------------


def test_unparseable_reply_returns_the_fallback(tmp_path):
    for content in (None, "", "ليس JSON", '{"supported": true}', '{"answer": "x"}'):
        result, _client, _retriever = run(
            tmp_path,
            "سؤال",
            [make_result(62, GRADUATION_TEXT)],
            content,
        )
        assert result.answer == answer.FALLBACK_ANSWER
        assert result.citations == ()
        assert result.used_fallback is True


def test_fenced_json_reply_is_accepted(tmp_path):
    content = "```json\n" + reply(True, "الحد الأدنى 2,75 (المادة 62).") + "\n```"

    result, _client, _retriever = run(
        tmp_path,
        "كم المعدل المطلوب عشان أتخرج؟",
        [make_result(62, GRADUATION_TEXT)],
        content,
    )

    assert result.used_fallback is False
    assert [citation.article for citation in result.citations] == [62]


def test_a_supported_answer_with_no_text_is_the_fallback(tmp_path):
    result, _client, _retriever = run(
        tmp_path,
        "سؤال",
        [make_result(62, GRADUATION_TEXT)],
        reply(True, "   "),
    )

    assert result.answer == answer.FALLBACK_ANSWER
    assert result.citations == ()


def test_model_failure_raises_instead_of_answering(tmp_path):
    with pytest.raises(answer.ModelUnavailable, match="gpt-4o-mini"):
        run(
            tmp_path,
            "سؤال",
            [make_result(62, GRADUATION_TEXT)],
            error=TimeoutError("connection timed out"),
        )


def test_model_failure_does_not_echo_the_prompt(tmp_path):
    with pytest.raises(answer.ModelUnavailable) as excinfo:
        run(
            tmp_path,
            "سؤال",
            [make_result(62, GRADUATION_TEXT)],
            error=RuntimeError("bad request"),
        )

    assert GRADUATION_TEXT not in str(excinfo.value)


# --- request guards -------------------------------------------------------


def test_empty_question_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="question is empty"):
        run(tmp_path, "   ", [make_result(62, GRADUATION_TEXT)], reply(True, "x"))


def test_question_over_the_limit_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="1000"):
        run(tmp_path, "س" * 1001, [make_result(62, GRADUATION_TEXT)], reply(True, "x"))


def test_question_at_the_limit_is_accepted(tmp_path):
    result, _client, _retriever = run(
        tmp_path,
        "س" * 1000,
        [make_result(62, GRADUATION_TEXT)],
        reply(True, "الحد الأدنى 2,75 (المادة 62)."),
    )

    assert result.used_fallback is False


# --- config and cost ------------------------------------------------------


def test_the_tracked_config_pins_the_documented_model_settings():
    config = answer.load_config(answer.DEFAULT_CONFIG)

    assert config.model == "gpt-4o-mini"
    assert config.temperature == 0.0
    assert config.max_output_tokens == 700
    assert config.price_per_1m_input > 0
    assert config.price_per_1m_output > 0
    assert config.source_id == "ref-01"


def test_config_missing_a_field_is_rejected(tmp_path):
    path = tmp_path / "chat.toml"
    path.write_text('[chat]\nmodel = "gpt-4o-mini"\n', encoding="utf-8")

    with pytest.raises(ValueError, match="missing"):
        answer.load_config(path)


def test_config_without_a_chat_table_is_rejected(tmp_path):
    path = tmp_path / "chat.toml"
    path.write_text('[embedding]\nmodel = "text-embedding-3-small"\n', encoding="utf-8")

    with pytest.raises(ValueError, match="no \\[chat\\] table"):
        answer.load_config(path)


def test_cost_uses_the_configured_prices(tmp_path):
    config = answer.load_config(write_config(tmp_path / "chat.toml"))
    usage = SimpleNamespace(prompt_tokens=1000, completion_tokens=500)

    cost = answer.estimate_cost(usage, config)

    assert cost == pytest.approx(
        1000 / 1_000_000 * 0.15 + 500 / 1_000_000 * 0.60
    )
    assert answer.estimate_cost(None, config) is None
    assert answer.estimate_cost(SimpleNamespace(), config) is None
