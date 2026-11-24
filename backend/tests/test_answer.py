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
    """Records every request the fake chat model is sent."""

    def __init__(self, content=None, error=None):
        self.contents = list(content) if isinstance(content, list) else [content]
        self.error = error
        self.calls = []

    def reply(self, **kwargs):
        """The request's reply: the next content, with its usage."""
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        content = self.contents.pop(0) if len(self.contents) > 1 else self.contents[0]
        return SimpleNamespace(
            content=content,
            usage_metadata={"input_tokens": 1200, "output_tokens": 80},
        )


class FakeChatClient:
    """Stands in for the chat model and records every request it is sent."""

    def __init__(self, content=None, error=None):
        self.completions = FakeCompletions(content, error)
        # Kept so a test can read the calls at the path the SDK shape had.
        self.chat = SimpleNamespace(completions=self.completions)

    def invoke(self, messages, **kwargs):
        """The LangChain call shape: the messages are the input, the rest a request."""
        return self.completions.reply(messages=messages, **kwargs)

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
    student_data=None,
    facts=None,
    extra_queries=(),
    needs_regulation=True,
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
        student_data=student_data,
        facts=facts,
        extra_queries=extra_queries,
        needs_regulation=needs_regulation,
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


# --- the request the model is sent ----------------------------------------


def test_the_answer_model_is_asked_for_a_json_object_not_a_schema(tmp_path):
    """The gateway does not offer json_schema, so the request must not send one.

    The strict parse in parse_model_answer is the guard, not the schema: a reply that is
    not the answer object still falls back. The JSON mode travels in the request's
    extra_body, which the SDK merges into the body, so a reply cut off at the output limit
    is returned to that parse rather than raised by the client.
    """
    client = FakeChatClient(reply(True, "المادة 25."))
    config = answer.load_config(write_config(tmp_path / "chat.toml"))

    answer.ask_model(config, client, [{"role": "user", "content": "سؤال"}])

    body = client.calls[0]["extra_body"]
    assert body["response_format"] == {"type": "json_object"}
    assert "json_schema" not in body["response_format"]
    # The fallback depends on this: a top-level response_format would send a reply cut
    # off at the output limit through LangChain's parse path, which raises instead of
    # returning the text parse_model_answer rejects.
    assert "response_format" not in client.calls[0]


def test_the_answer_model_is_asked_not_to_think(tmp_path):
    """Thinking is on by default on the gateway and would break the latency target."""
    client = FakeChatClient(reply(True, "المادة 25."))
    config = answer.load_config(
        write_config(tmp_path / "chat.toml", reasoning_effort="none")
    )

    answer.ask_model(config, client, [{"role": "user", "content": "سؤال"}])

    assert client.calls[0]["extra_body"]["reasoning_effort"] == "none"


# --- config and cost ------------------------------------------------------


def test_the_tracked_config_pins_the_documented_model_settings():
    """The shipped config, pinned: the gateway, its model and its JSON mode.

    The model id is pinned rather than the gateway's PRIMARY_MODEL alias, because an
    alias can be repointed at a different model without a change to this repository.
    """
    config = answer.load_config(answer.DEFAULT_CONFIG)

    assert config.provider == "gateway"
    assert config.base_url == "https://ai-gateway.seai-x.com/inference/v1"
    assert config.model == "DeepSeek-V4.1-Flash"
    assert config.api_key_env == "LLM_API_KEY"
    assert config.json_mode == "json_object"
    assert config.reasoning_effort == "none"
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


# --- the graduation template ---------------------------------------------


GRADUATION_PLAN = {
    "remaining_hours": 23,
    "remaining_courses": [{"name": "مشروع تخرج -1", "type": "إجباري"}],
}


def graduation_facts(remaining_hours, thresholds):
    from app import facts

    return facts.graduation_facts(
        {"get_plan_progress": dict(GRADUATION_PLAN, remaining_hours=remaining_hours)},
        thresholds,
    )


def thresholds():
    from app import facts

    return {
        "max_term_load": facts.Threshold(value=20, article=24),
        "max_term_load_exception": facts.Threshold(value=24, article=24),
    }


ARTICLE_24 = make_result(
    24,
    "يكون الحد الأدنى للعبء الدراسي للطالب في الفصل الدراسي اثنتا عشرة وحدة دراسية "
    "والحد الأعلى عشرون وحدة دراسية، ولعمادة شؤون القبول والتسجيل زيادة الحد الأعلى "
    "لعبء الطالب في الفصل الدراسي بما لا يتجاوز أربعاً وعشرين وحدة دراسية.",
)


def test_the_template_for_twenty_three_hours_names_the_deanship_and_article_24():
    text = answer.template_answer(
        graduation_facts(23, thresholds()), "كم يتبقى لي؟", [ARTICLE_24]
    )

    assert "20" in text
    assert "24" in text
    assert "(المادة 24)" in text
    assert "عمادة شؤون القبول والتسجيل" in text


def test_the_template_for_eighteen_hours_says_one_term_without_promising_it():
    text = answer.template_answer(
        graduation_facts(18, thresholds()), "كم يتبقى لي؟", [ARTICLE_24]
    )

    assert "فيمكن تسجيلها في فصل واحد، بشرط المتطلبات السابقة" in text
    assert "فتتخرج" not in text
    assert "عمادة شؤون القبول والتسجيل" not in text


def test_the_template_for_twenty_three_hours_asks_for_approval_and_keeps_the_conditions():
    text = answer.template_answer(
        graduation_facts(23, thresholds()), "كم يتبقى لي؟", [ARTICLE_24]
    )

    assert "فيمكن تسجيل الساعات المتبقية في فصل واحد بموافقتها" in text
    assert "بشرط ألا تمنع المتطلبات السابقة ذلك" in text
    assert "فتتخرج" not in text


def test_two_sequential_courses_warn_that_one_term_may_not_work():
    """Article 24 does not override the prerequisites, so the answer warns before the student asks."""
    from app import facts

    plan = {
        "remaining_hours": 23,
        "remaining_courses": [
            {"name": "مشروع تخرج -1", "type": "إجباري"},
            {"name": "مشروع تخرج -2", "type": "إجباري"},
        ],
    }
    computed = facts.graduation_facts({"get_plan_progress": plan}, thresholds())

    text = answer.template_answer(computed, "كم يتبقى لي؟", [ARTICLE_24])

    assert computed["sequence_pairs"]
    assert (
        "تنبيه: وجود مقررين متتابعين قد يجعل التخرج في فصل واحد غير ممكن حتى مع الموافقة."
        in text
    )
    assert "فتتخرج" not in text


def test_the_template_for_twenty_five_hours_says_no_approval_holds_it():
    text = answer.template_answer(
        graduation_facts(25, thresholds()), "كم يتبقى لي؟", [ARTICLE_24]
    )

    assert "24" in text
    assert "بموافقتها" not in text


def test_the_graduation_prompt_explains_the_exception():
    messages = answer.build_messages(
        "كم يتبقى لي؟", [ARTICLE_24], facts=graduation_facts(23, thresholds())
    )

    assert answer.GRADUATION_RULES in messages[0]["content"]
    assert "needs_exception" in messages[0]["content"]


def test_another_kind_gets_no_graduation_rule():
    messages = answer.build_messages(
        "كم غيابي؟",
        [ARTICLE_24],
        facts={"kind": "absences", "limit_percent": 25, "courses": []},
    )

    assert answer.GRADUATION_RULES not in messages[0]["content"]


# --- the verdict templates ------------------------------------------------

ABSENCE_COURSES = [
    {"code": "430", "name": "تفاضل وتكامل", "absence_percent": 21, "absences": 5},
    {"code": "431", "name": "قواعد البيانات", "absence_percent": 11.86, "absences": 3},
]


def absence_facts(*percents):
    from app import facts

    courses = [
        {**course, "absence_percent": percent}
        for course, percent in zip(ABSENCE_COURSES, percents)
    ]
    return facts.absences_facts(
        {"get_absences": {"courses": courses}},
        {"absence_limit_percent": facts.Threshold(value=25, article=25)},
    )


ARTICLE_25 = make_result(
    25,
    "يعد الطالب محروما إذا تجاوزت نسبة غيابه 25% من محاضرات المقرر.",
)


def test_the_absences_template_states_each_course_and_its_remaining_margin():
    text = answer.template_answer(absence_facts(21, 11.86), "هل أنا قريب من الحرمان؟", [ARTICLE_25])

    assert "تفاضل وتكامل (430): 21% — المتبقي قبل الحد 4%" in text
    assert "قواعد البيانات (431): 11.86% — المتبقي قبل الحد 13.14%" in text
    # Article 25's own words: attendance of the contact hours, not a paraphrase of them.
    assert "يُحرم الطالب من دخول الاختبار النهائي" in text
    assert "75% من مجموع ساعات الاتصال لجميع أنشطة المقرر" in text
    assert "أي إذا زاد غيابه عن 25% (المادة 25)" in text


def test_the_english_absences_template_follows_article_25_too():
    text = answer.template_answer(
        absence_facts(21, 11.86), "Am I close to being barred?", [ARTICLE_25]
    )

    assert (
        "barred from the final exam if attendance falls below 75% of the course's total "
        "contact hours across all its activities, i.e. more than 25% absence (Article 25)."
        in text
    )


def test_the_absences_template_names_the_near_course_without_calling_it_over():
    text = answer.template_answer(absence_facts(21, 11.86), "هل أنا قريب من الحرمان؟", [ARTICLE_25])

    assert "لا يوجد مقرر تجاوز الحد" in text
    assert "قريب من الحد" in text
    assert "تفاضل وتكامل" in text.split("قريب من الحد")[1]
    assert "قواعد البيانات" not in text.split("قريب من الحد")[1]


def test_the_absences_template_names_the_course_over_the_limit():
    text = answer.template_answer(absence_facts(27, 11), "هل أنا قريب من الحرمان؟", [ARTICLE_25])

    assert "تجاوزت الحد في: تفاضل وتكامل" in text
    assert "لا يوجد مقرر تجاوز الحد" not in text


# --- academic warning -----------------------------------------------------


def warning_facts(gpa, thresholds=None):
    from app import facts

    return facts.academic_warning_facts(
        {"get_gpa": {"cumulative_gpa": gpa, "scale": "5"}}, thresholds or {}
    )


def test_the_warning_template_does_not_answer_when_the_regulation_is_silent():
    """No threshold in the regulation: the template must not say yes or no."""
    text = answer.template_answer(warning_facts("4.21"), "هل أنا تحت الإنذار؟")

    assert "4.21" in text
    assert "من 5" in text
    assert "نعم" not in text
    assert "لا،" not in text
    assert "Edugate" in text
    assert "مرشدك الأكاديمي" in text


def test_the_warning_template_gives_the_verdict_when_the_threshold_is_known():
    from app import facts

    text = answer.template_answer(
        warning_facts("1.75", {"warning_gpa": facts.Threshold(value=2, article=58)}),
        "هل أنا تحت الإنذار؟",
        [make_result(58, "يُنذر الطالب إذا كان معدله التراكمي أقل من 2,00.")],
    )

    assert "1.75" in text
    assert "2" in text
    assert "أنت تحت الحد" in text
    assert "(المادة 58)" in text


# --- GPA target -----------------------------------------------------------


def target_facts(target=4.5):
    from app import facts

    return facts.gpa_target_facts(
        {"get_gpa": {"cumulative_gpa": "4.21", "scale": "5", "earned_hours": 96}},
        {},
        f"كم أحتاج عشان يصير معدلي {target}؟",
    )


def test_the_target_template_states_the_average_for_twelve_fifteen_and_eighteen_hours():
    text = answer.template_answer(target_facts(), "كم أحتاج عشان يصير معدلي 4.5؟")

    assert "12 ساعة" in text and "6.82" in text
    assert "15 ساعة" in text and "6.36" in text
    assert "18 ساعة" in text and "6.05" in text


def test_the_target_template_says_an_average_over_the_scale_is_impossible():
    text = answer.template_answer(target_facts(), "كم أحتاج عشان يصير معدلي 4.5؟")

    assert "أعلى من المقياس 5" in text
    assert "غير ممكن" in text


def test_a_reachable_target_is_not_called_impossible():
    text = answer.template_answer(target_facts(2.5), "كم أحتاج عشان يصير معدلي 2.5؟")

    assert "غير ممكن" not in text


# --- exam conflicts -------------------------------------------------------


def exam_facts(exams):
    from app import facts

    return facts.exam_conflicts_facts({"get_final_exams": {"exams": exams}})


def test_the_conflicts_template_names_the_pair_and_the_time():
    text = answer.template_answer(
        exam_facts(
            [
                {"name": "قواعد البيانات", "date": "6-07-1448", "time": "08:00"},
                {"name": "هندسة البرمجيات", "date": "6-07-1448", "time": "08:00"},
            ]
        ),
        "هل عندي تعارض في الاختبارات النهائية؟",
    )

    assert "6-07-1448" in text
    assert "08:00" in text
    assert "قواعد البيانات" in text and "هندسة البرمجيات" in text


def test_the_conflicts_template_says_so_when_there_is_none():
    text = answer.template_answer(
        exam_facts([{"name": "قواعد البيانات", "date": "6-07-1448", "time": "08:00"}]),
        "هل عندي تعارض في الاختبارات النهائية؟",
    )

    assert "لا يوجد تعارض" in text


# --- planning the week ----------------------------------------------------


def week_facts():
    from datetime import datetime, timedelta, timezone

    from app import facts

    riyadh = timezone(timedelta(hours=3))
    return facts.plan_week_facts(
        {
            "get_assignments": {
                "items": [
                    {
                        "title": "واجب 3",
                        "course": "SWE 483",
                        "due_at": "2026-11-21T23:59:00+03:00",
                    },
                    {
                        "title": "كويز",
                        "course": "SWE 444",
                        "due_at": "2026-11-24T12:00:00+03:00",
                    },
                ]
            },
            "get_schedule": {
                "classes": [
                    {
                        "code": "SWE 483",
                        "name": "هندسة البرمجيات",
                        "activity": "محاضرة",
                        "days": [1, 3],
                        "start": "11:00",
                        "end": "11:50",
                    }
                ]
            },
        },
        now=datetime(2026, 11, 20, 10, 0, tzinfo=riyadh),
    )


def test_the_week_template_puts_the_classes_before_the_due_item_of_each_day():
    text = answer.template_answer(week_facts(), "كيف أوزع وقتي هالأسبوع؟")

    saturday = text.split("- السبت 21 نوفمبر")[1].split("- الأحد")[0]
    assert "واجب 3" in saturday
    assert "11:59 م" in saturday

    tuesday = text.split("- الثلاثاء 24 نوفمبر")[1].split("- الأربعاء")[0]
    assert "هندسة البرمجيات" in tuesday
    assert "11:00 ص-11:50 ص" in tuesday
    assert "كويز" in tuesday


def test_the_week_template_puts_schedule_day_one_on_sunday():
    """Edugate numbers 1 as Sunday, so the class listed on day 1 is a Sunday class."""
    text = answer.template_answer(week_facts(), "كيف أوزع وقتي هالأسبوع؟")

    sunday = text.split("- الأحد 22 نوفمبر")[1].split("- الاثنين")[0]
    assert "هندسة البرمجيات" in sunday
    assert "لا محاضرات ولا واجبات" not in sunday


def test_the_week_template_suggests_a_free_block_before_the_due_time():
    text = answer.template_answer(week_facts(), "كيف أوزع وقتي هالأسبوع؟")

    assert "8:00 ص-11:00 ص" in text
    assert "(3 ساعات)" in text
    assert "180 دقيقة" not in text


def test_the_week_template_states_no_iso_date():
    text = answer.template_answer(week_facts(), "كيف أوزع وقتي هالأسبوع؟")

    assert "2026-11-21" not in text
    assert not __import__("re").search(r"\d{4}-\d{2}-\d{2}", text)


def test_the_week_template_says_which_days_have_nothing():
    text = answer.template_answer(week_facts(), "كيف أوزع وقتي هالأسبوع؟")

    assert "لا محاضرات ولا واجبات" in text


# --- answering a verdict kind from the template ----------------------------


def test_a_verdict_kind_is_answered_from_the_template_without_a_model():
    """No client is even passed: a verdict kind has no model call to make."""
    searcher = FakeRetriever([ARTICLE_25])

    result = answer.answer_from_facts(
        "absences",
        "هل أنا قريب من الحرمان؟",
        retriever=searcher,
        facts=absence_facts(21, 11.86),
        extra_queries=("نسبة الغياب والحرمان",),
    )

    assert "المتبقي قبل الحد" in result.answer
    assert [query for query, _k in searcher.queries] == [
        "هل أنا قريب من الحرمان؟",
        "نسبة الغياب والحرمان",
    ]


def test_a_retrieved_article_is_cited_from_its_own_chunk():
    result = answer.answer_from_facts(
        "absences",
        "هل أنا قريب من الحرمان؟",
        retriever=FakeRetriever([ARTICLE_25]),
        facts=absence_facts(21, 11.86),
    )

    assert result.citations == (
        answer.Citation(title=TITLE, article=25, url=URL),
    )


def test_an_article_that_was_not_retrieved_is_cited_from_the_source_config():
    """The template names article 25, so the citation points at the regulation itself."""
    source = answer.SourceRef(title="لائحة الدراسة والاختبارات", url="https://dar.ksu.edu.sa/r.pdf")

    result = answer.answer_from_facts(
        "absences",
        "هل أنا قريب من الحرمان؟",
        retriever=FakeRetriever([]),
        facts=absence_facts(21, 11.86),
        source=source,
    )

    assert result.citations == (
        answer.Citation(title=source.title, article=25, url=source.url),
    )


def test_an_article_the_template_does_not_state_is_not_cited():
    """The graduation template says nothing about article 25, so it is not cited."""
    result = answer.answer_from_facts(
        "graduation",
        "هل أقدر أتخرج الفصل القادم؟",
        retriever=FakeRetriever([ARTICLE_25]),
        facts=graduation_facts(18, thresholds()),
    )

    assert result.citations == ()


def test_a_kind_with_no_regulation_cites_nothing():
    result = answer.answer_from_facts(
        "exam_conflicts",
        "هل عندي تعارض في الاختبارات النهائية؟",
        retriever=FakeRetriever([ARTICLE_25]),
        facts=exam_facts([{"name": "قواعد البيانات", "date": "6-07-1448", "time": "08:00"}]),
        needs_regulation=False,
    )

    assert result.citations == ()
    assert result.answer.endswith(answer.NO_REGULATION_NOTE)


def test_the_shipped_sources_config_names_the_regulation():
    source = answer.load_source("ref-01")

    assert source is not None
    assert source.title.startswith("KSU Regulations")
    assert source.url.startswith("https://dar.ksu.edu.sa/")


def test_an_unknown_source_id_is_no_source():
    assert answer.load_source("ref-99") is None
