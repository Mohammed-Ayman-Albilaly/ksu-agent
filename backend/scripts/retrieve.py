#!/usr/bin/env python3
"""Retrieve the chunks most similar to a query from one source's index.

The vectors come from embed_chunks.py (data/processed/index/<id>.npz) and the
chunks from chunk_source.py (data/processed/chunks/<id>.jsonl). The query is
cleaned with parse_source.clean_text — the same NFKC + tatweel removal applied
to the source text before it was chunked — then embedded with the model pinned
in backend/config/embeddings.toml, so the query and the chunks live in one
vector space. Embeddings from different models are never compared.

Ranking is cosine similarity over the stored float32 vectors, highest first.

Usage:
    python backend/scripts/retrieve.py --source-id ref-01 --query "..." --k 5
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from embed_chunks import (
    DEFAULT_CHUNKS_DIR,
    DEFAULT_CONFIG,
    DEFAULT_INDEX_DIR,
    EmbeddingConfig,
    load_config,
    make_client,
    make_tokenizer,
)
from fetch_sources import sha256_file
from parse_source import clean_text

VECTOR_KEY = "vectors"
DEFAULT_K = 5
SNIPPET_CHARS = 200


@dataclass(frozen=True)
class Chunk:
    """One indexed chunk, as read from the JSONL written by chunk_source.py."""

    index: int
    article_number: int | None
    heading: str
    text: str
    part: int = 1
    parts: int = 1

    @property
    def label(self) -> str:
        """How the chunk is named in output and error messages."""
        if self.article_number is not None:
            name = f"article {self.article_number}"
        else:
            name = f"chunk {self.index + 1} ({self.heading})"
        if self.parts > 1:
            return f"{name} part {self.part} of {self.parts}"
        return name


@dataclass(frozen=True)
class SearchResult:
    """A chunk and its similarity to the query."""

    score: float
    chunk: Chunk

    @property
    def article_number(self) -> int | None:
        return self.chunk.article_number

    @property
    def text(self) -> str:
        return self.chunk.text

    def snippet(self, limit: int = SNIPPET_CHARS) -> str:
        """One line of the chunk's text, cut at ``limit`` characters."""
        flat = " ".join(self.chunk.text.split())
        if len(flat) <= limit:
            return flat
        return flat[:limit].rstrip() + "…"


def normalize_query(text: str) -> str:
    """Clean a query exactly as parse_source cleans the source text.

    NFKC folds presentation forms and ligatures; tatweel (U+0640) is dropped.
    The chunks were embedded after this same cleaning, so an identical string
    embeds to an identical vector.
    """
    return clean_text(text)


def read_chunks(chunks_path: Path) -> list[Chunk]:
    """Load the JSONL chunks written by chunk_source.py."""
    chunks_path = Path(chunks_path)
    if not chunks_path.exists():
        raise FileNotFoundError(
            f"{chunks_path} not found; run chunk_source.py --source-id "
            f"{chunks_path.stem}"
        )

    chunks: list[Chunk] = []
    with chunks_path.open("r", encoding="utf-8") as fh:
        for line_number, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            text = record.get("text")
            if not isinstance(text, str) or not text.strip():
                raise ValueError(f"{chunks_path}:{line_number}: chunk has no text")
            chunks.append(
                Chunk(
                    index=len(chunks),
                    article_number=record.get("article_number"),
                    heading=str(record.get("heading", "")),
                    text=text,
                    part=int(record.get("part", 1)),
                    parts=int(record.get("parts", 1)),
                )
            )

    if not chunks:
        raise ValueError(f"{chunks_path}: no chunks found")
    return chunks


def load_index(
    source_id: str,
    config: EmbeddingConfig,
    *,
    chunks_dir: Path = DEFAULT_CHUNKS_DIR,
    index_dir: Path = DEFAULT_INDEX_DIR,
) -> tuple[np.ndarray, list[Chunk], dict]:
    """Load one source's vectors, chunks and metadata, checking they agree.

    A mismatch is an error rather than a warning: searching an index built from
    a different model, a different vector length or a stale chunk file would
    return confident nonsense.
    """
    chunks_path = Path(chunks_dir) / f"{source_id}.jsonl"
    npz_path = Path(index_dir) / f"{source_id}.npz"
    meta_path = Path(index_dir) / f"{source_id}.index.json"

    if not npz_path.exists() or not meta_path.exists():
        raise FileNotFoundError(
            f"index for {source_id} not found in {Path(index_dir)}; run "
            f"embed_chunks.py --source-id {source_id}"
        )

    chunks = read_chunks(chunks_path)
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))

    with np.load(npz_path) as data:
        if VECTOR_KEY not in data:
            raise ValueError(f"{npz_path}: no {VECTOR_KEY!r} array")
        vectors = data[VECTOR_KEY].astype(np.float32)

    if metadata.get("model") != config.model:
        raise ValueError(
            f"{npz_path} was built with model {metadata.get('model')!r}; "
            f"{DEFAULT_CONFIG.name} pins {config.model!r}. Re-embed the "
            f"source instead of mixing vectors from two models."
        )
    if vectors.ndim != 2 or vectors.shape[1] != config.dimensions:
        raise ValueError(
            f"{npz_path} holds {vectors.shape} vectors; config expects "
            f"{config.dimensions} dimensions"
        )
    if vectors.shape[0] != len(chunks):
        raise ValueError(
            f"{npz_path} holds {vectors.shape[0]} vectors but "
            f"{chunks_path.name} has {len(chunks)} chunks; re-run "
            f"embed_chunks.py"
        )
    if metadata.get("chunk_file_sha256") != sha256_file(chunks_path):
        raise ValueError(
            f"{chunks_path.name} changed after {npz_path.name} was built; "
            f"re-run embed_chunks.py"
        )

    return vectors, chunks, metadata


def embed_query(
    query: str,
    config: EmbeddingConfig,
    client,
    *,
    tokenizer=None,
) -> tuple[str, np.ndarray]:
    """Normalise and embed one query; returns the text sent and its vector."""
    normalized = normalize_query(query)
    if not normalized.strip():
        raise ValueError("query is empty after cleaning")

    if tokenizer is not None:
        tokens = len(tokenizer.encode(normalized))
        if tokens > config.max_input_tokens:
            raise ValueError(
                f"query is {tokens} tokens; {config.model} accepts at most "
                f"{config.max_input_tokens}"
            )

    response = client.embeddings.create(
        model=config.model,
        input=[normalized],
        dimensions=config.dimensions,
        encoding_format="float",
    )
    if len(response.data) != 1:
        raise ValueError(
            f"{config.model} returned {len(response.data)} vectors for 1 input"
        )
    vector = np.asarray(response.data[0].embedding, dtype=np.float32)
    if vector.shape != (config.dimensions,):
        raise ValueError(
            f"{config.model} returned {vector.size} dimensions; config expects "
            f"{config.dimensions}"
        )
    return normalized, vector


def cosine_scores(vectors: np.ndarray, query_vector: np.ndarray) -> np.ndarray:
    """Cosine similarity of every row to the query vector."""
    if vectors.ndim != 2 or vectors.shape[0] == 0:
        raise ValueError("vectors must be a non-empty 2-D array")
    if query_vector.shape != (vectors.shape[1],):
        raise ValueError("query vector and index vectors differ in length")

    index_norms = np.linalg.norm(vectors, axis=1)
    query_norm = float(np.linalg.norm(query_vector))
    if np.any(index_norms == 0) or query_norm == 0:
        raise ValueError("cannot compute cosine similarity with a zero vector")

    return (vectors @ query_vector) / (index_norms * query_norm)


def rank(scores: np.ndarray, chunks: list[Chunk], k: int) -> list[SearchResult]:
    """The ``k`` highest scores, highest first, as SearchResults."""
    if k < 1:
        raise ValueError("k must be at least 1")
    if len(scores) != len(chunks):
        raise ValueError("scores must have one entry per chunk")

    order = np.argsort(scores)[::-1][:k]
    return [
        SearchResult(score=float(scores[position]), chunk=chunks[position])
        for position in order
    ]


def retrieve(
    source_id: str,
    query: str,
    *,
    k: int = DEFAULT_K,
    config_path: Path = DEFAULT_CONFIG,
    chunks_dir: Path = DEFAULT_CHUNKS_DIR,
    index_dir: Path = DEFAULT_INDEX_DIR,
    client=None,
    tokenizer=None,
) -> list[SearchResult]:
    """Embed ``query`` and return the top ``k`` chunks for one source."""
    config = load_config(config_path)
    vectors, chunks, _metadata = load_index(
        source_id, config, chunks_dir=chunks_dir, index_dir=index_dir
    )

    client = client or make_client(config)
    if tokenizer is None:
        tokenizer = make_tokenizer(config)

    _normalized, query_vector = embed_query(
        query, config, client, tokenizer=tokenizer
    )
    return rank(cosine_scores(vectors, query_vector), chunks, k)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Search one source's chunk index with a single query."
    )
    parser.add_argument(
        "--source-id",
        required=True,
        help="id of the source, e.g. ref-01 (names <id>.jsonl and <id>.npz)",
    )
    parser.add_argument("--query", required=True, help="query text")
    parser.add_argument(
        "--k",
        type=int,
        default=DEFAULT_K,
        help=f"number of chunks to return (default: {DEFAULT_K})",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"embedding config file (default: {DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "--chunks-dir",
        type=Path,
        default=DEFAULT_CHUNKS_DIR,
        help=f"chunk directory (default: {DEFAULT_CHUNKS_DIR})",
    )
    parser.add_argument(
        "--index-dir",
        type=Path,
        default=DEFAULT_INDEX_DIR,
        help=f"index directory (default: {DEFAULT_INDEX_DIR})",
    )
    args = parser.parse_args(argv)

    try:
        results = retrieve(
            args.source_id,
            args.query,
            k=args.k,
            config_path=args.config,
            chunks_dir=args.chunks_dir,
            index_dir=args.index_dir,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    for position, result in enumerate(results, start=1):
        article = (
            str(result.article_number)
            if result.article_number is not None
            else "annex"
        )
        print(
            f"#{position}  article {article}  score {result.score:.4f}  "
            f"{result.snippet()}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
