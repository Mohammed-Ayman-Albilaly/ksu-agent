"""Tests for scripts/chunk_source.py.

The documents are synthetic: chunking is structural, so a few lines with the same
shape as the parsed source exercise it without a PDF or network access.
"""

import json

import pytest

import chunk_source
from fetch_sources import Source

TOC_LINES = [
    "  القسم العام:  التعريفات والأهداف والنطاق1 ................................................",
    "  المادة الأولى1 ............................................................................",
    "  المادة الثانية6............................................................................",
    "  المادة الثالثة6............................................................................",
]

DOCUMENT = [
    "[[page 1]]",
    *TOC_LINES,
    "[[page 7]]",
    " القسم العام:  التعريفات والأهداف والنطاق",
    " المادة الأولى",
    " تعريفات المادة الأولى.",
    " المادة الثانية",
    " نص المادة الثانية.",
]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("الأولى", 1),
        ("الحادية عشرة", 11),
        ("العشرون", 20),
        ("الثالثة والعشرون", 23),
        ("الثالثة والسبعون", 73),
        ("الثانية", 2),
        ("العاشرة", 10),
        ("السابعة عشر", 17),
        ("الحادية والعشرون", 21),
        ("الثلاثون", 30),
        ("الأربعون", 40),
        ("الحادية والسبعون", 71),
    ],
)
def test_parse_ordinal(text, expected):
    assert chunk_source.parse_ordinal(text) == expected


@pytest.mark.parametrize(
    "text",
    ["", "الدراسية", "الثالثة والثلاثون .أ", "الملحقات", "المادة"],
)
def test_parse_ordinal_rejects_non_ordinals(text):
    assert chunk_source.parse_ordinal(text) is None


def test_parse_article_heading_accepts_heading_line():
    assert chunk_source.parse_article_heading(" المادة الثالثة والسبعون") == (
        73,
        "المادة الثالثة والسبعون",
    )


def test_parse_article_heading_rejects_cross_reference():
    # Four tokens, but the ordinal does not consume the trailing marker.
    assert (
        chunk_source.parse_article_heading("   المادة السابعة والأربعون   .أ          ")
        is None
    )


def test_parse_article_heading_rejects_prose():
    line = (
        "  المادة الدراسية الإجبارية أو الاختيارية أو الحرة في خطة كل برنامج "
        "ذات محتوى:المقرر الدراسي"
    )
    assert chunk_source.parse_article_heading(line) is None


def test_toc_lines_are_dropped():
    chunks = chunk_source.split_chunks(DOCUMENT)

    assert [chunk.article_number for chunk in chunks] == [1, 2]
    assert all("....." not in chunk.text for chunk in chunks)
    assert "التعريفات والأهداف" not in chunks[0].text


def test_cover_and_preamble_are_dropped():
    chunks = chunk_source.split_chunks(DOCUMENT)

    assert "[[page 1]]" not in chunks[0].text
    assert chunks[0].text == "المادة الأولى\n تعريفات المادة الأولى."


def test_rule_block_stays_with_its_article():
    lines = [
        " المادة الأولى",
        " نص الأولى.",
        " القاعدة التنفيذية للمادة الأولى",
        " تفاصيل القاعدة.",
        " المادة الثانية",
        " نص الثانية.",
    ]

    chunks = chunk_source.split_chunks(lines)

    assert [chunk.article_number for chunk in chunks] == [1, 2]
    assert "القاعدة التنفيذية للمادة الأولى" in chunks[0].text
    assert "تفاصيل القاعدة." in chunks[0].text
    assert "القاعدة التنفيذية" not in chunks[1].text


def test_rule_block_naming_another_article_moves_to_that_article():
    lines = [
        " المادة الأولى",
        " نص الأولى.",
        " المادة الثانية",
        " نص الثانية.",
        " القاعدة التنفيذية للمادة الأولى",
        " تفاصيل القاعدة.",
    ]

    chunks = chunk_source.split_chunks(lines)

    assert [chunk.article_number for chunk in chunks] == [1, 2]
    assert "تفاصيل القاعدة." in chunks[0].text
    assert "تفاصيل القاعدة." not in chunks[1].text


def test_text_after_last_article_is_one_annex_chunk():
    lines = [
        " المادة الأولى",
        " نص الأولى.",
        " القسم الثالث عشر: الملحقات",
        " (1) الملحق",
        " جدول التقديرات.",
        " (٢) الملحق",
        " جدول آخر.",
    ]

    chunks = chunk_source.split_chunks(lines)

    assert [chunk.kind for chunk in chunks] == ["article", "annex"]
    annex = chunks[-1]
    assert annex.article_number is None
    assert annex.heading == "القسم الثالث عشر: الملحقات"
    assert "جدول التقديرات." in annex.text and "جدول آخر." in annex.text
    assert "الملحق" not in chunks[0].text


def test_build_records_carries_source_provenance():
    source = Source(
        id="ref-01",
        url="https://example.test/a.pdf",
        filename="a.pdf",
        title="Example regulation",
    )
    chunks = chunk_source.split_chunks(DOCUMENT)

    records = chunk_source.build_records(source, "a" * 64, chunks)

    assert len(records) == 2
    first = records[0]
    assert list(first) == [
        "source_id",
        "title",
        "url",
        "sha256",
        "kind",
        "article_number",
        "heading",
        "text",
        "char_count",
    ]
    assert first["source_id"] == "ref-01"
    assert first["title"] == "Example regulation"
    assert first["url"] == "https://example.test/a.pdf"
    assert first["sha256"] == "a" * 64
    assert first["kind"] == "article"
    assert first["article_number"] == 1
    assert first["heading"] == "المادة الأولى"
    assert first["char_count"] == len(first["text"])


def test_chunk_source_writes_one_json_object_per_line(tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir()
    (processed / "ref-01.txt").write_text(
        "\n".join(DOCUMENT) + "\n", encoding="utf-8"
    )
    source = Source(id="ref-01", url="https://example.test/a.pdf", filename="a.pdf")

    records = chunk_source.chunk_source(
        source,
        "a" * 64,
        processed_dir=processed,
        out_dir=tmp_path / "chunks",
    )

    path = tmp_path / "chunks" / "ref-01.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(records) == 2
    assert [json.loads(line)["article_number"] for line in lines] == [1, 2]


def test_chunk_source_rejects_stale_parsed_text(tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir()
    (processed / "ref-01.txt").write_text("\n".join(DOCUMENT), encoding="utf-8")
    (processed / "ref-01.meta.json").write_text(
        json.dumps({"sha256": "b" * 64}), encoding="utf-8"
    )
    source = Source(id="ref-01", url="https://example.test/a.pdf", filename="a.pdf")

    with pytest.raises(ValueError, match="re-run parse_source"):
        chunk_source.chunk_source(
            source, "a" * 64, processed_dir=processed, out_dir=tmp_path / "chunks"
        )


def test_main_rejects_unknown_source_id(tmp_path):
    config = tmp_path / "sources.toml"
    config.write_text(
        "[[source]]\n"
        'id = "ref-01"\n'
        'url = "https://example.test/a.pdf"\n'
        'filename = "a.pdf"\n',
        encoding="utf-8",
    )

    exit_code = chunk_source.main(
        [
            "--source-id",
            "nope",
            "--config",
            str(config),
            "--lock",
            str(tmp_path / "lock.json"),
            "--processed-dir",
            str(tmp_path),
            "--out-dir",
            str(tmp_path / "chunks"),
        ]
    )

    assert exit_code == 2
