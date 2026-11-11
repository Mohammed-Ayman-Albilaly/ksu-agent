"""Tests for the lexical (BM25) and hybrid (RRF) retrieval modes — no network.

The dense ranking is faked: a table client maps the cleaned query and each chunk text
to a vector chosen by the test, so the dense order is whatever the test needs it to be.
The lexical ranking is real BM25 over the chunk texts, so these tests also cover the
tokenizer. Nothing here loads an index from disk or calls the embedding provider.
"""

import hashlib
import json
import math
from types import SimpleNamespace

import numpy as np
import pytest

import retrieve

DIMENSIONS = 3
MODEL = "text-embedding-3-small"
TITLE = "KSU Regulations of Study and Examinations"
URL = "https://dar.ksu.edu.sa/regulations.pdf"

# The question the fake dense ranking is built to get wrong.
QUESTION = "كم نسبة الغياب اللي تمنعني من دخول الاختبار النهائي؟"

ARTICLES = [
    "الحد الأدنى للمعدل المطلوب للتخرج هو 2,75",  # article 1, dense distractor
    "نسبة الغياب التي تمنع الطالب من دخول الاختبار النهائي هي 25%",  # article 2
    "لا يجوز للطالب دخول الاختبار النهائي قبل سداد الرسوم",  # article 3
    "يعقد الاختبار النهائي في نهاية الفصل الدراسي",  # article 4
    "يجوز تأجيل الدراسة لمدة فصلين دراسيين على الأكثر",  # article 5
]


def unit_vector(cosine):
    """A vector whose cosine similarity with (1, 0, 0) is exactly ``cosine``."""
    return [cosine, math.sqrt(1 - cosine**2), 0.0]


def make_chunks(texts=ARTICLES):
    return [
        retrieve.Chunk(
            index=position,
            article_number=position + 1,
            heading=f"المادة {position + 1}",
            text=text,
            title=TITLE,
            url=URL,
        )
        for position, text in enumerate(texts)
    ]


class TableClient:
    """Stands in for openai.OpenAI, returning the vector the test chose."""

    def __init__(self, table):
        self.table = table
        self.inputs = []
        self.embeddings = self

    def create(self, *, model, input, dimensions=None, encoding_format=None):
        self.inputs.append(list(input))
        data = [
            SimpleNamespace(index=index, embedding=self.table[text])
            for index, text in enumerate(input)
        ]
        return SimpleNamespace(data=data)


def write_config(path, **overrides):
    values = {
        "provider": "openai",
        "model": MODEL,
        "dimensions": DIMENSIONS,
        "max_input_tokens": 8191,
        "price_per_1m_tokens": 0.02,
        "tokenizer": "cl100k_base",
        "batch_size": 64,
        "batch_max_tokens": 200000,
    }
    values.update(overrides)
    lines = ["[embedding]"]
    lines += [f"{key} = {json.dumps(value)}" for key, value in values.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_index(tmp_path, texts, vectors):
    """Write the chunk JSONL and the vector index for ``texts``."""
    chunks_dir = tmp_path / "chunks"
    index_dir = tmp_path / "index"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    index_dir.mkdir(parents=True, exist_ok=True)

    chunks_path = chunks_dir / "ref-01.jsonl"
    chunks_path.write_text(
        "\n".join(
            json.dumps(
                {
                    "source_id": "ref-01",
                    "title": TITLE,
                    "url": URL,
                    "kind": "article",
                    "article_number": position + 1,
                    "heading": f"المادة {position + 1}",
                    "text": text,
                },
                ensure_ascii=False,
            )
            for position, text in enumerate(texts)
        )
        + "\n",
        encoding="utf-8",
    )

    np.savez(index_dir / "ref-01.npz", vectors=np.array(vectors, dtype=np.float32))
    (index_dir / "ref-01.index.json").write_text(
        json.dumps(
            {
                "source_id": "ref-01",
                "model": MODEL,
                "dimensions": DIMENSIONS,
                "vector_count": len(texts),
                "chunk_file": "ref-01.jsonl",
                "chunk_file_sha256": hashlib.sha256(
                    chunks_path.read_bytes()
                ).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    return chunks_dir, index_dir


def dense_table(texts, cosines, query=QUESTION):
    """The query's vector plus one vector per chunk, at the requested cosines."""
    table = {retrieve.normalize_query(query): [1.0, 0.0, 0.0]}
    for text, cosine in zip(texts, cosines):
        table[text] = unit_vector(cosine)
    return table


def search(
    tmp_path,
    mode,
    *,
    k=5,
    query=QUESTION,
    client=None,
    texts=ARTICLES,
    cosines=None,
):
    """Run one query through retrieve() with a fake dense order set by ``cosines``."""
    if cosines is None:
        cosines = [0.9 - 0.1 * position for position in range(len(texts))]
    chunks_dir, index_dir = write_index(
        tmp_path, texts, [unit_vector(cosine) for cosine in cosines]
    )
    return retrieve.retrieve(
        "ref-01",
        query,
        k=k,
        mode=mode,
        config_path=write_config(tmp_path / "embeddings.toml"),
        chunks_dir=chunks_dir,
        index_dir=index_dir,
        client=client or TableClient(dense_table(texts, cosines, query)),
        tokenizer=SimpleNamespace(encode=str.split),
    )


# --- tokenizer ------------------------------------------------------------


def test_tokenizer_cleans_and_drops_stopwords():
    tokens = retrieve.tokenize("كم نسبة الغياب اللي تمنعني من دخول الاختبار النهائي؟")

    assert tokens == ["نسبة", "الغياب", "تمنعني", "دخول", "الاختبار", "النهائي"]


def test_tokenizer_applies_the_parser_cleaning():
    """Tatweel and a presentation form must not split a word from itself."""
    assert retrieve.tokenize("ا\u0640ﻟحد") == retrieve.tokenize("الحد") == ["الحد"]


def test_tokenizer_folds_alef_forms_so_hamza_variants_match():
    assert retrieve.tokenize("الأدنى") == retrieve.tokenize("الادنى") == ["الادني"]


def test_tokenizer_keeps_numbers_whole():
    assert "2,75" in retrieve.tokenize("الحد الأدنى 2,75")
    assert "25" in retrieve.tokenize("النسبة 25%")


def test_tokenizer_returns_nothing_for_a_stopword_only_query():
    assert retrieve.tokenize("كم من في اللي") == []


# --- BM25 -----------------------------------------------------------------


def test_bm25_scores_the_chunk_that_shares_the_query_words_highest():
    index = retrieve.build_bm25_index(make_chunks())

    scores = retrieve.bm25_scores(index, QUESTION)

    assert retrieve.order_descending(scores)[0] == 1
    assert scores[1] > 0
    assert scores[0] == 0 and scores[4] == 0


def test_bm25_scores_are_zero_for_an_unseen_word():
    index = retrieve.build_bm25_index(
        make_chunks(["نسبة الغياب 25"])
    )

    assert retrieve.bm25_scores(index, "كلمة غريبة تماما").tolist() == [0.0]


def test_bm25_counts_a_repeated_query_word_once():
    index = retrieve.build_bm25_index(make_chunks(["الغياب 25", "المعدل 2,75"]))

    once = retrieve.bm25_scores(index, "الغياب")
    twice = retrieve.bm25_scores(index, "الغياب الغياب")

    assert twice.tolist() == once.tolist()


def test_bm25_index_rejects_an_empty_corpus():
    with pytest.raises(ValueError, match="no chunks"):
        retrieve.build_bm25_index([])


# --- RRF ------------------------------------------------------------------


def test_rrf_ranks_by_the_sum_of_reciprocal_ranks():
    fused = retrieve.reciprocal_rank_fusion([[0, 1, 2], [2, 0, 1]], rrf_k=60)

    scores = dict(fused)
    assert scores[0] == pytest.approx(1 / 61 + 1 / 62)
    assert scores[2] == pytest.approx(1 / 63 + 1 / 61)
    assert scores[1] == pytest.approx(1 / 62 + 1 / 63)
    assert [position for position, _score in fused] == [0, 2, 1]


def test_rrf_uses_the_rank_not_the_raw_score():
    """A ranker's score scale cannot leak into the fusion: only ranks count."""
    assert retrieve.reciprocal_rank_fusion([[5], [5]], rrf_k=10) == [
        (5, pytest.approx(2 / 11))
    ]


def test_rrf_keeps_equal_scores_in_chunk_order():
    fused = retrieve.reciprocal_rank_fusion([[3, 1], [1, 3]], rrf_k=60)

    assert [position for position, _score in fused] == [1, 3]


def test_rrf_rejects_a_non_positive_constant():
    with pytest.raises(ValueError, match="rrf_k"):
        retrieve.reciprocal_rank_fusion([[0]], rrf_k=0)


def test_fuse_rejects_a_ranking_position_past_the_chunks():
    with pytest.raises(ValueError, match="1 chunks"):
        retrieve.fuse([[0, 1]], make_chunks(["one"]), 2)


def test_hybrid_puts_first_the_article_dense_alone_misses():
    """Dense ranks article 1 first and article 2 third; lexical ranks 2 first."""
    chunks = make_chunks()
    dense = [0, 2, 1, 3, 4]
    lexical = [1, 2, 3, 0, 4]

    dense_only = retrieve.fuse([dense], chunks, 2)
    hybrid = retrieve.fuse([dense, lexical], chunks, 2)

    assert 2 not in [result.article_number for result in dense_only]
    assert hybrid[0].article_number == 2
    assert hybrid[0].score == pytest.approx(1 / 61 + 1 / 63)


# --- modes end to end -----------------------------------------------------
def test_dense_mode_misses_the_article_hybrid_finds(tmp_path):
    """The fake dense order is article 1, 3, 2, 4, 5; BM25 puts article 2 first."""
    dense_cosines = [0.9, 0.7, 0.8, 0.6, 0.5]

    dense = search(
        tmp_path / "dense", retrieve.MODE_DENSE, k=2, cosines=dense_cosines
    )
    hybrid = search(
        tmp_path / "hybrid", retrieve.MODE_HYBRID, k=2, cosines=dense_cosines
    )

    assert [result.article_number for result in dense] == [1, 3]
    assert [result.article_number for result in hybrid] == [2, 3]
    assert hybrid[0].chunk.text == ARTICLES[1]


def test_lexical_mode_needs_no_embedding_call(tmp_path):
    class NoClient:
        def __getattr__(self, name):  # pragma: no cover - only reached on misuse
            raise AssertionError("lexical mode must not touch the embedding client")

    results = search(
        tmp_path, retrieve.MODE_LEXICAL, k=2, client=NoClient()
    )

    assert [result.article_number for result in results] == [2, 3]


def test_lexical_mode_rejects_a_query_without_content_words(tmp_path):
    with pytest.raises(ValueError, match="no searchable words"):
        search(tmp_path, retrieve.MODE_LEXICAL, query="كم من في")


def test_hybrid_falls_back_to_dense_for_a_query_without_content_words(tmp_path):
    results = search(tmp_path, retrieve.MODE_HYBRID, query="كم من في", k=2)

    assert [result.article_number for result in results] == [1, 2]


def test_unknown_mode_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="unknown mode"):
        search(tmp_path, "bm25", query="الغياب", k=1)


def test_cli_defaults_to_hybrid_and_prints_the_fused_score(
    tmp_path, monkeypatch, capsys
):
    texts = ARTICLES
    cosines = [0.9, 0.8, 0.7, 0.6, 0.5]
    chunks_dir, index_dir = write_index(
        tmp_path, texts, [unit_vector(cosine) for cosine in cosines]
    )
    config = write_config(tmp_path / "embeddings.toml")
    client = TableClient(dense_table(texts, cosines))

    monkeypatch.setattr(retrieve, "make_client", lambda _config: client)
    monkeypatch.setattr(
        retrieve, "make_tokenizer", lambda _config: SimpleNamespace(encode=str.split)
    )

    code = retrieve.main(
        [
            "--source-id",
            "ref-01",
            "--query",
            QUESTION,
            "--k",
            "1",
            "--config",
            str(config),
            "--chunks-dir",
            str(chunks_dir),
            "--index-dir",
            str(index_dir),
        ]
    )

    assert code == 0
    out = capsys.readouterr().out
    assert "article 2" in out
    assert "score 0.0325" in out  # 1/61 + 1/62, the fused score, not a cosine
