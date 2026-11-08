"""Tests for scripts/parse_source.py.

No network access: test PDFs are written with PyMuPDF so page counting and the
output files are exercised without shipping a fixture document.
"""

import hashlib
import json
import re

import pymupdf
import pytest

import parse_source
from fetch_sources import Source

TATWEEL = "\u0640"
PRESENTATION_FORM_RANGE = ("\ufe70", "\ufeff")
MARKER_RE = re.compile(r"\[\[page (\d+)\]\]")


def _pdf(path, page_texts):
    """Write a PDF with one page per entry in ``page_texts``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open() as doc:
        for text in page_texts:
            page = doc.new_page(width=595, height=842)
            if text:
                page.insert_text((72, 100), text)
        doc.save(str(path))
    return path


@pytest.fixture
def three_page_pdf(tmp_path):
    return _pdf(tmp_path / "raw" / "doc.pdf", ["Article 1", "Article 2", "Article 3"])


def test_clean_text_removes_tatweel():
    assert parse_source.clean_text(f"م{TATWEEL * 3}ادة") == "مادة"
    assert TATWEEL not in parse_source.clean_text(f"ا{TATWEEL}لجامعة")


def test_clean_text_applies_nfkc():
    # Arabic presentation forms and ligatures fold to their canonical letters.
    assert parse_source.clean_text("\ufedb") == "\u0643"  # ARABIC LETTER KAF, initial form
    assert parse_source.clean_text("\ufdf2") == "الله"
    assert parse_source.clean_text("\ufb01") == "fi"


def test_clean_text_leaves_clean_text_unchanged():
    text = "المادة الرابعة: يشترط الحصول على 2.00 من 5.00\n\n"
    assert parse_source.clean_text(text) == text


def test_build_document_keeps_page_order():
    document = parse_source.build_document(["first page", "second page", "third page"])

    assert document.splitlines()[:6] == [
        "[[page 1]]",
        "first page",
        "[[page 2]]",
        "second page",
        "[[page 3]]",
        "third page",
    ]
    assert [int(n) for n in MARKER_RE.findall(document)] == [1, 2, 3]


def test_build_document_marks_empty_pages():
    document = parse_source.build_document(["", "text"])
    assert document.splitlines()[:4] == ["[[page 1]]", "", "[[page 2]]", "text"]


def test_cleaned_document_has_no_presentation_forms_or_tatweel():
    pages = [
        f"الم{TATWEEL}ادة الرابعة",
        "\ufedb\ufe8e\ufedf\ufedf\ufee0",  # كلم in presentation forms
        "\ufdf2 \ufb01",
    ]

    document = parse_source.build_document(
        [parse_source.clean_text(text) for text in pages]
    )

    low, high = PRESENTATION_FORM_RANGE
    leftovers = [
        char
        for char in document
        if low <= char <= high or char == TATWEEL
    ]
    assert leftovers == []

    # Markers survive cleaning and stay in page order.
    numbers = [int(n) for n in MARKER_RE.findall(document)]
    assert numbers == [1, 2, 3]
    positions = [document.index(f"[[page {n}]]") for n in numbers]
    assert positions == sorted(positions)


def test_extract_pages_reads_text_in_page_order(three_page_pdf):
    pages = parse_source.extract_pages(three_page_pdf)

    assert len(pages) == 3
    assert "Article 1" in pages[0]
    assert "Article 2" in pages[1]
    assert "Article 3" in pages[2]


def test_parse_writes_txt_and_meta(tmp_path, three_page_pdf):
    out_dir = tmp_path / "processed"
    source = Source(id="ref-01", url="https://example.test/a.pdf", filename="doc.pdf")
    sha = hashlib.sha256(three_page_pdf.read_bytes()).hexdigest()

    meta = parse_source.parse(source, sha, raw_dir=three_page_pdf.parent, out_dir=out_dir)

    txt_path = out_dir / "ref-01.txt"
    meta_path = out_dir / "ref-01.meta.json"
    assert txt_path.exists() and meta_path.exists()

    document = txt_path.read_text(encoding="utf-8")
    assert [int(n) for n in MARKER_RE.findall(document)] == [1, 2, 3]
    assert document.startswith("[[page 1]]")
    assert document.endswith("\n")

    assert meta == {
        "source_id": "ref-01",
        "sha256": sha,
        "page_count": 3,
        "char_count": len(document),
    }
    assert json.loads(meta_path.read_text(encoding="utf-8")) == meta


def test_parse_rejects_hash_mismatch(tmp_path, three_page_pdf):
    source = Source(id="ref-01", url="https://example.test/a.pdf", filename="doc.pdf")

    with pytest.raises(ValueError, match="hash"):
        parse_source.parse(
            source, "0" * 64, raw_dir=three_page_pdf.parent, out_dir=tmp_path / "out"
        )


def test_parse_reports_missing_pdf(tmp_path):
    source = Source(id="ref-01", url="https://example.test/a.pdf", filename="doc.pdf")

    with pytest.raises(FileNotFoundError):
        parse_source.parse(source, "0" * 64, raw_dir=tmp_path, out_dir=tmp_path / "out")


def test_main_rejects_unknown_source_id(tmp_path):
    config = tmp_path / "sources.toml"
    config.write_text(
        "[[source]]\n"
        'id = "ref-01"\n'
        'url = "https://example.test/a.pdf"\n'
        'filename = "doc.pdf"\n',
        encoding="utf-8",
    )

    exit_code = parse_source.main(
        [
            "--source-id",
            "nope",
            "--config",
            str(config),
            "--lock",
            str(tmp_path / "lock.json"),
            "--raw-dir",
            str(tmp_path),
            "--out-dir",
            str(tmp_path / "out"),
        ]
    )

    assert exit_code == 2


def test_main_requires_source_id(tmp_path):
    with pytest.raises(SystemExit) as excinfo:
        parse_source.main(["--config", str(tmp_path / "sources.toml")])

    assert excinfo.value.code == 2
