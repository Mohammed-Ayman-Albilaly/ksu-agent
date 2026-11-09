"""Tests for embed_chunks.py — no network and no real API key.

The embedding client is a fake with the OpenAI SDK's response shape, and the
tokenizer counts words, so every assertion is deterministic.
"""

import hashlib
import json
from types import SimpleNamespace

import numpy as np
import pytest

import embed_chunks

DIMENSIONS = 8


class WordTokenizer:
    """One token per whitespace-separated word."""

    def encode(self, text):
        return text.split()


class FakeClient:
    """Stands in for openai.OpenAI and records the batches it is sent."""

    def __init__(self, dimensions=DIMENSIONS):
        self.dimensions = dimensions
        self.batches = []
        self.embeddings = self

    def create(self, *, model, input, dimensions=None, encoding_format=None):
        self.batches.append(list(input))
        data = [
            SimpleNamespace(index=index, embedding=_vector(text, self.dimensions))
            for index, text in enumerate(input)
        ]
        return SimpleNamespace(data=data)


def _vector(text, dimensions):
    """A stable pseudo-vector, so a re-run can be compared exactly."""
    seed = sum(ord(char) for char in text)
    return [((seed + position) % 97) / 97 for position in range(dimensions)]


def write_config(path, **overrides):
    values = {
        "provider": "openai",
        "model": "text-embedding-3-small",
        "dimensions": DIMENSIONS,
        "max_input_tokens": 8191,
        "price_per_1m_tokens": 0.02,
        "tokenizer": "cl100k_base",
        "batch_size": 2,
        "batch_max_tokens": 1000,
    }
    values.update(overrides)
    lines = ["[embedding]"]
    lines += [f"{key} = {json.dumps(value)}" for key, value in values.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_chunks(path, texts):
    path.parent.mkdir(parents=True, exist_ok=True)
    records = [
        {
            "source_id": "ref-01",
            "kind": "article",
            "article_number": index + 1,
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


def run(tmp_path, texts, *, client=None, tokenizer=None, **config_overrides):
    config = write_config(tmp_path / "embeddings.toml", **config_overrides)
    chunks_dir = tmp_path / "chunks"
    write_chunks(chunks_dir / "ref-01.jsonl", texts)
    return embed_chunks.run(
        "ref-01",
        config_path=config,
        chunks_dir=chunks_dir,
        out_dir=tmp_path / "index",
        client=client if client is not None else FakeClient(),
        tokenizer=tokenizer if tokenizer is not None else WordTokenizer(),
    )


def test_vector_count_equals_chunk_count(tmp_path):
    meta = run(tmp_path, ["one two three", "four five", "six seven eight nine"])

    vectors = np.load(tmp_path / "index" / "ref-01.npz")["vectors"]

    assert vectors.shape[0] == 3
    assert meta["vector_count"] == 3 == vectors.shape[0]


@pytest.mark.parametrize("dimensions", [4, 16])
def test_vector_dimensions_come_from_config(tmp_path, dimensions):
    meta = run(
        tmp_path,
        ["one two", "three four"],
        client=FakeClient(dimensions=dimensions),
        dimensions=dimensions,
    )

    vectors = np.load(tmp_path / "index" / "ref-01.npz")["vectors"]

    assert vectors.dtype == np.float32
    assert vectors.shape == (2, dimensions)
    assert meta["dimensions"] == dimensions


def test_rerun_produces_identical_vectors(tmp_path):
    texts = ["one two three", "four five", "six seven eight"]
    run(tmp_path, texts)
    first = np.load(tmp_path / "index" / "ref-01.npz")["vectors"].copy()

    run(tmp_path, texts)
    second = np.load(tmp_path / "index" / "ref-01.npz")["vectors"]

    assert np.array_equal(first, second)


def test_oversized_chunk_aborts_and_lists_articles(tmp_path):
    client = FakeClient()

    with pytest.raises(embed_chunks.InputTooLongError) as excinfo:
        run(
            tmp_path,
            ["one two three", "four five six seven eight"],
            client=client,
            max_input_tokens=4,
        )

    message = str(excinfo.value)
    assert "article 2" in message
    assert "4-token input limit" in message
    assert "5 tokens" in message
    assert "article 1" not in message
    # Aborted before any request, and nothing was written.
    assert client.batches == []
    assert not (tmp_path / "index" / "ref-01.npz").exists()
    assert not (tmp_path / "index" / "ref-01.index.json").exists()


def test_chunks_are_sent_in_batches_in_order(tmp_path):
    client = FakeClient()
    texts = ["one", "two", "three", "four", "five"]

    run(tmp_path, texts, client=client, batch_size=2, batch_max_tokens=1000)

    assert [len(batch) for batch in client.batches] == [2, 2, 1]
    assert [text for batch in client.batches for text in batch] == texts


def test_batch_max_tokens_splits_batches(tmp_path):
    client = FakeClient()
    texts = ["one two", "three four", "five six", "seven eight"]

    run(tmp_path, texts, client=client, batch_size=10, batch_max_tokens=4)

    assert [len(batch) for batch in client.batches] == [2, 2]


def test_metadata_records_model_tokens_sha_and_cost(tmp_path):
    texts = ["one two three", "four five"]
    meta = run(tmp_path, texts)

    chunks_path = tmp_path / "chunks" / "ref-01.jsonl"
    expected_sha = hashlib.sha256(chunks_path.read_bytes()).hexdigest()

    assert meta["source_id"] == "ref-01"
    assert meta["model"] == "text-embedding-3-small"
    assert meta["dimensions"] == DIMENSIONS
    assert meta["vector_count"] == 2
    assert meta["chunk_file"] == "ref-01.jsonl"
    assert meta["chunk_file_sha256"] == expected_sha
    assert meta["total_tokens"] == 5
    assert meta["max_chunk_tokens"] == 3
    assert meta["price_per_1m_tokens"] == 0.02
    assert meta["estimated_cost_usd"] == pytest.approx(5 * 0.02 / 1_000_000, rel=1e-6)

    written = json.loads((tmp_path / "index" / "ref-01.index.json").read_text("utf-8"))
    assert written == meta


def test_vectors_of_wrong_dimensions_are_rejected(tmp_path):
    client = FakeClient(dimensions=DIMENSIONS + 1)

    with pytest.raises(ValueError, match="config expects 8"):
        run(tmp_path, ["one two", "three four"], client=client)

    assert not (tmp_path / "index" / "ref-01.npz").exists()


def test_shipped_config_pins_the_embedding_model():
    config = embed_chunks.load_config(embed_chunks.DEFAULT_CONFIG)

    assert config.provider == "openai"
    assert config.model == "text-embedding-3-small"
    assert config.dimensions == 1536
    assert config.max_input_tokens == 8191
    assert config.price_per_1m_tokens == 0.02


def test_api_key_is_read_from_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv(embed_chunks.ENV_KEY, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=sk-test-value\n", encoding="utf-8")

    assert embed_chunks.api_key(env_file) == "sk-test-value"


def test_missing_api_key_error_names_the_variable(tmp_path, monkeypatch):
    monkeypatch.delenv(embed_chunks.ENV_KEY, raising=False)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        embed_chunks.api_key(tmp_path / "absent.env")


def test_missing_chunk_file_points_at_chunk_source(tmp_path):
    config = write_config(tmp_path / "embeddings.toml")

    with pytest.raises(FileNotFoundError, match="chunk_source.py"):
        embed_chunks.run(
            "ref-01",
            config_path=config,
            chunks_dir=tmp_path / "chunks",
            out_dir=tmp_path / "index",
            client=FakeClient(),
            tokenizer=WordTokenizer(),
        )
