"""Tests for retrieve.py — no network and no real API key.

The embedding client is a fake with the OpenAI SDK's response shape. Its
vectors are derived from the raw text it is handed, so a query only lands on
the chunk's own vector when retrieve.py cleans the query first. That is what
makes the perfect-match test fail if the normalisation is removed.
"""

import hashlib
import json
from types import SimpleNamespace

import numpy as np
import pytest

import retrieve

DIMENSIONS = 64
MODEL = "text-embedding-3-small"
TITLE = "KSU Regulations of Study and Examinations"
URL = "https://dar.ksu.edu.sa/regulations.pdf"

# The sentence from the acceptance check. It is the indexed chunk's text.
PERFECT_SENTENCE = "الحد الأدنى للمعدل المطلوب للتخرج هو 2,75"
# The same sentence as it arrives from a PDF copy: tatweel inside "الحد" and
# a presentation form (U+FEDF, lam initial) instead of the plain lam.
PERFECT_QUERY = "ا\u0640ﻟحد الأدنى للمعدل المطلوب للتخرج هو 2,75"


class WordTokenizer:
    """One token per whitespace-separated word."""

    def encode(self, text):
        return text.split()


def _hash_vector(text, dimensions):
    """One-hot vector keyed by the raw text; any character change moves it."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    bucket = int.from_bytes(digest[:8], "big") % dimensions
    vector = [0.0] * dimensions
    vector[bucket] = 1.0
    return vector


def _bag_vector(text, dimensions):
    """Normalised bag of word hashes, so overlapping texts score between 0 and 1."""
    vector = np.zeros(dimensions, dtype=np.float32)
    for word in text.split():
        digest = hashlib.sha256(word.encode("utf-8")).digest()
        vector[int.from_bytes(digest[:4], "big") % dimensions] += 1.0
    norm = np.linalg.norm(vector)
    return (vector / norm if norm else vector).tolist()


class FakeClient:
    """Stands in for openai.OpenAI and records the inputs it is sent."""

    def __init__(self, dimensions=DIMENSIONS, embed=None):
        self.dimensions = dimensions
        self.embed = embed or _hash_vector
        self.inputs = []
        self.embeddings = self

    def create(self, *, model, input, dimensions=None, encoding_format=None):
        self.inputs.append(list(input))
        data = [
            SimpleNamespace(index=index, embedding=self.embed(text, self.dimensions))
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


def write_chunks(path, texts, *, article_numbers=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    records = [
        {
            "source_id": "ref-01",
            "title": TITLE,
            "url": URL,
            "kind": "article",
            "article_number": (
                article_numbers[index] if article_numbers else index + 1
            ),
            "heading": f"المادة {index + 1}",
            "text": text,
        }
        for index, text in enumerate(texts)
    ]
    path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
        encoding="utf-8",
    )
    return records


def write_index(
    tmp_path,
    texts,
    *,
    client=None,
    article_numbers=None,
    dimensions=DIMENSIONS,
    model=MODEL,
    chunk_file_sha256=None,
):
    """Chunk the texts, embed them with ``client`` and write the index files."""
    client = client or FakeClient(dimensions=dimensions)
    chunks_path = tmp_path / "chunks" / "ref-01.jsonl"
    write_chunks(chunks_path, texts, article_numbers=article_numbers)

    vectors = np.array(
        [client.embed(text, dimensions) for text in texts], dtype=np.float32
    )
    index_dir = tmp_path / "index"
    index_dir.mkdir(parents=True, exist_ok=True)
    np.savez(index_dir / "ref-01.npz", vectors=vectors)

    metadata = {
        "source_id": "ref-01",
        "model": model,
        "dimensions": dimensions,
        "vector_count": len(texts),
        "chunk_file": "ref-01.jsonl",
        "chunk_file_sha256": (
            chunk_file_sha256
            if chunk_file_sha256 is not None
            else hashlib.sha256(chunks_path.read_bytes()).hexdigest()
        ),
    }
    (index_dir / "ref-01.index.json").write_text(
        json.dumps(metadata, ensure_ascii=False), encoding="utf-8"
    )
    return client


def run(
    tmp_path,
    texts,
    query,
    *,
    k=5,
    mode=retrieve.MODE_DENSE,
    client=None,
    tokenizer=None,
    article_numbers=None,
    **config_overrides,
):
    """Dense retrieval by default: these tests assert cosine scores."""
    client = write_index(
        tmp_path, texts, client=client, article_numbers=article_numbers
    )
    return retrieve.retrieve(
        "ref-01",
        query,
        k=k,
        mode=mode,
        config_path=write_config(tmp_path / "embeddings.toml", **config_overrides),
        chunks_dir=tmp_path / "chunks",
        index_dir=tmp_path / "index",
        client=client,
        tokenizer=tokenizer or WordTokenizer(),
    )


def retrieve_with(tmp_path, query, *, client=None, tokenizer=None, **config_overrides):
    """Call retrieve() against an index already written under ``tmp_path``."""
    return retrieve.retrieve(
        "ref-01",
        query,
        config_path=write_config(tmp_path / "embeddings.toml", **config_overrides),
        chunks_dir=tmp_path / "chunks",
        index_dir=tmp_path / "index",
        client=client or FakeClient(),
        tokenizer=tokenizer or WordTokenizer(),
    )


# --- the acceptance check -------------------------------------------------


def test_perfect_match_returns_that_chunk_first_with_score_above_0_9(tmp_path):
    client = FakeClient()

    results = run(tmp_path, [PERFECT_SENTENCE], PERFECT_QUERY, k=1, client=client)

    assert results[0].chunk.text == PERFECT_SENTENCE
    assert results[0].score > 0.90
    assert results[0].score == pytest.approx(1.0)
    # The query reached the provider already cleaned: same string as the chunk.
    assert client.inputs == [[PERFECT_SENTENCE]]


def test_perfect_match_fixture_would_miss_without_cleaning():
    """Guards the test above: the raw query is not the chunk's vector."""
    raw = np.array(_hash_vector(PERFECT_QUERY, DIMENSIONS), dtype=np.float32)
    chunk = np.array(_hash_vector(PERFECT_SENTENCE, DIMENSIONS), dtype=np.float32)

    assert retrieve.cosine_scores(chunk.reshape(1, -1), raw)[0] == pytest.approx(0.0)


def test_query_is_cleaned_with_the_parser_rules():
    assert retrieve.normalize_query(PERFECT_QUERY) == PERFECT_SENTENCE
    assert "\u0640" not in retrieve.normalize_query(PERFECT_QUERY)
    assert retrieve.normalize_query("ﻻ") == "لا"  # U+FEFB -> NFKC


def test_empty_query_after_cleaning_is_rejected(tmp_path):
    write_index(tmp_path, ["one two three"])

    with pytest.raises(ValueError, match="empty after cleaning"):
        retrieve_with(tmp_path, " \u0640 ")


# --- ranking --------------------------------------------------------------


def test_results_are_sorted_by_cosine_similarity(tmp_path):
    client = FakeClient(embed=_bag_vector)
    texts = ["one two three", "four five six", "one two"]

    results = run(tmp_path, texts, "one two", k=3, client=client)

    assert results[0].chunk.text == "one two"
    assert results[0].score == pytest.approx(1.0)
    scores = [result.score for result in results]
    assert scores == sorted(scores, reverse=True)
    assert results[0].score > results[1].score


def test_k_limits_the_results_and_is_clamped_to_the_index(tmp_path):
    texts = ["one", "two", "three", "four"]

    assert len(run(tmp_path / "a", texts, "one", k=2)) == 2
    assert len(run(tmp_path / "b", texts, "one", k=99)) == 4


def test_k_must_be_positive(tmp_path):
    write_index(tmp_path, ["one", "two"])
    chunks = retrieve.read_chunks(tmp_path / "chunks" / "ref-01.jsonl")

    with pytest.raises(ValueError, match="k must be at least 1"):
        retrieve.rank(np.array([0.5, 0.5]), chunks, 0)


def test_article_number_and_snippet_are_exposed(tmp_path):
    client = FakeClient(embed=_bag_vector)
    long_text = "one two " * 100

    results = run(tmp_path, [long_text, "three four"], "one two", k=1, client=client)

    assert results[0].article_number == 1
    assert len(results[0].snippet(limit=20)) <= 21
    assert "\n" not in results[0].snippet()


def test_annex_chunks_have_no_article_number(tmp_path):
    results = run(tmp_path, ["annex text"], "annex", article_numbers=[None])

    assert results[0].article_number is None



def test_chunks_carry_the_source_title_and_url_for_citations(tmp_path):
    write_index(tmp_path, ["one two"])

    chunks = retrieve.read_chunks(tmp_path / "chunks" / "ref-01.jsonl")

    assert chunks[0].title == TITLE
    assert chunks[0].url == URL


def test_make_searcher_searches_a_loaded_index(tmp_path):
    client = write_index(tmp_path, ["one two three", "four five six"])

    search = retrieve.make_searcher(
        "ref-01",
        config_path=write_config(tmp_path / "embeddings.toml"),
        chunks_dir=tmp_path / "chunks",
        index_dir=tmp_path / "index",
        client=client,
        tokenizer=WordTokenizer(),
    )

    assert search("one two three", 1)[0].chunk.text == "one two three"
    assert search("four five six", 1)[0].chunk.text == "four five six"

# --- guards ---------------------------------------------------------------


def test_model_mismatch_is_rejected(tmp_path):
    write_index(tmp_path, ["one two"], model="text-embedding-3-large")

    with pytest.raises(ValueError, match="two models"):
        retrieve_with(tmp_path, "one")


def test_dimension_mismatch_is_rejected(tmp_path):
    write_index(tmp_path, ["one two"], dimensions=DIMENSIONS + 1)

    with pytest.raises(ValueError, match="dimensions"):
        retrieve_with(tmp_path, "one")


def test_vector_count_mismatch_is_rejected(tmp_path):
    write_index(tmp_path, ["one two", "three four"])
    np.savez(
        tmp_path / "index" / "ref-01.npz",
        vectors=np.ones((3, DIMENSIONS), dtype=np.float32),
    )

    with pytest.raises(ValueError, match="2 chunks"):
        retrieve_with(tmp_path, "one")


def test_stale_index_is_rejected(tmp_path):
    write_index(tmp_path, ["one two"], chunk_file_sha256="0" * 64)

    with pytest.raises(ValueError, match="changed after"):
        retrieve_with(tmp_path, "one")


def test_missing_index_points_at_embed_chunks(tmp_path):
    with pytest.raises(FileNotFoundError, match="embed_chunks.py"):
        retrieve_with(tmp_path, "one")


def test_missing_chunk_file_points_at_chunk_source(tmp_path):
    index_dir = tmp_path / "index"
    index_dir.mkdir(parents=True)
    np.savez(index_dir / "ref-01.npz", vectors=np.ones((1, DIMENSIONS), dtype=np.float32))
    (index_dir / "ref-01.index.json").write_text("{}", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="chunk_source.py"):
        retrieve_with(tmp_path, "one")


def test_query_over_the_token_limit_is_rejected(tmp_path):
    write_index(tmp_path, ["one two three four five"])

    with pytest.raises(ValueError, match="accepts at most 3"):
        retrieve_with(tmp_path, "one two three four", max_input_tokens=3)


def test_query_vector_of_wrong_dimensions_is_rejected(tmp_path):
    write_index(tmp_path, ["one two"])

    with pytest.raises(ValueError, match="config expects 64"):
        retrieve_with(tmp_path, "one", client=FakeClient(dimensions=DIMENSIONS + 1))


# --- CLI ------------------------------------------------------------------


def test_cli_prints_article_score_and_snippet(tmp_path, monkeypatch, capsys):
    client = write_index(tmp_path, ["one two three", "four five six"])
    config = write_config(tmp_path / "embeddings.toml")

    monkeypatch.setattr(retrieve, "make_client", lambda _config: client)
    monkeypatch.setattr(retrieve, "make_tokenizer", lambda _config: WordTokenizer())

    code = retrieve.main(
        [
            "--source-id",
            "ref-01",
            "--query",
            "one two three",
            "--k",
            "1",
            "--mode",
            "dense",
            "--config",
            str(config),
            "--chunks-dir",
            str(tmp_path / "chunks"),
            "--index-dir",
            str(tmp_path / "index"),
        ]
    )

    assert code == 0
    out = capsys.readouterr().out
    assert "#1" in out
    assert "article 1" in out
    assert "score 1.0000" in out
    assert "one two three" in out
