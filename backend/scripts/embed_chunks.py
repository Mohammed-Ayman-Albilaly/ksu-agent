#!/usr/bin/env python3
"""Embed one source's chunks and write a vector index.

Input is the per-article JSONL written by chunk_source.py
(data/processed/chunks/<id>.jsonl). Every chunk is counted with the tokenizer
named in backend/config/embeddings.toml before anything is sent, and the run
aborts — naming the offending articles — when a chunk is longer than the model's
input limit. Chunks are never truncated: a truncated chunk would be embedded and
cited as if it were the whole article.

Chunks are sent in batches and the vectors are written under
data/processed/index (git-ignored):

    <id>.npz         key "vectors", float32, shape (chunks, dimensions)
    <id>.index.json  model, dimensions, vector count, chunk-file sha256,
                     total tokens and estimated cost

The model, its dimensions, its input limit and its price all come from the
embedding config; none of them is hard-coded here. The API key is read from
OPENAI_API_KEY in the repo-root .env (git-ignored, see .env.example) and is
never written out, logged or committed.

Usage:
    python backend/scripts/embed_chunks.py --source-id ref-01
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tomllib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from fetch_sources import REPO_ROOT, sha256_file

DEFAULT_CONFIG = REPO_ROOT / "backend" / "config" / "embeddings.toml"
DEFAULT_CHUNKS_DIR = REPO_ROOT / "data" / "processed" / "chunks"
DEFAULT_INDEX_DIR = REPO_ROOT / "data" / "processed" / "index"
DEFAULT_ENV_FILE = REPO_ROOT / ".env"
ENV_KEY = "OPENAI_API_KEY"
VECTOR_KEY = "vectors"
TOKENS_PER_PRICE_UNIT = 1_000_000
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_MAX_RETRIES = 3
REQUIRED_FIELDS = (
    "provider",
    "model",
    "dimensions",
    "max_input_tokens",
    "price_per_1m_tokens",
    "tokenizer",
)


@dataclass(frozen=True)
class EmbeddingConfig:
    """The embedding model, its limits and its price, as configured."""

    provider: str
    model: str
    dimensions: int
    max_input_tokens: int
    price_per_1m_tokens: float
    tokenizer: str
    batch_size: int
    batch_max_tokens: int


@dataclass(frozen=True)
class Chunk:
    """One chunk of a source, ready to be embedded."""

    index: int
    article_number: int | None
    heading: str
    text: str
    part: int = 1
    parts: int = 1

    @property
    def label(self) -> str:
        """How the chunk is named in error messages."""
        if self.article_number is not None:
            name = f"article {self.article_number}"
        else:
            name = f"chunk {self.index + 1} ({self.heading})"
        if self.parts > 1:
            return f"{name} part {self.part} of {self.parts}"
        return name


class InputTooLongError(ValueError):
    """A chunk is longer than the model accepts; nothing was embedded."""

    def __init__(self, limit: int, oversized: list[tuple[Chunk, int]]) -> None:
        self.limit = limit
        self.oversized = oversized
        detail = ", ".join(
            f"{chunk.label} ({tokens} tokens)" for chunk, tokens in oversized
        )
        super().__init__(
            f"{len(oversized)} chunk(s) exceed the model's {limit}-token input "
            f"limit: {detail}. Re-chunk with smaller pieces; nothing was "
            f"truncated or embedded."
        )


def load_config(config_path: Path) -> EmbeddingConfig:
    """Read and validate the embedding config."""
    with Path(config_path).open("rb") as fh:
        data = tomllib.load(fh)

    section = data.get("embedding")
    if not isinstance(section, dict):
        raise ValueError(f"{config_path}: no [embedding] table found")

    missing = [field for field in REQUIRED_FIELDS if section.get(field) is None]
    if missing:
        raise ValueError(
            f"{config_path}: [embedding] is missing {', '.join(missing)}"
        )

    config = EmbeddingConfig(
        provider=str(section["provider"]).strip(),
        model=str(section["model"]).strip(),
        dimensions=int(section["dimensions"]),
        max_input_tokens=int(section["max_input_tokens"]),
        price_per_1m_tokens=float(section["price_per_1m_tokens"]),
        tokenizer=str(section["tokenizer"]).strip(),
        batch_size=int(section.get("batch_size", 64)),
        batch_max_tokens=int(section.get("batch_max_tokens", 200_000)),
    )

    if not config.provider or not config.model or not config.tokenizer:
        raise ValueError(f"{config_path}: provider, model and tokenizer are required")
    if config.dimensions <= 0:
        raise ValueError(f"{config_path}: dimensions must be positive")
    if config.max_input_tokens <= 0:
        raise ValueError(f"{config_path}: max_input_tokens must be positive")
    if config.price_per_1m_tokens < 0:
        raise ValueError(f"{config_path}: price_per_1m_tokens must not be negative")
    if config.batch_size < 1 or config.batch_max_tokens < 1:
        raise ValueError(f"{config_path}: batch limits must be at least 1")

    return config


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


def count_tokens(chunks: list[Chunk], encode) -> list[int]:
    """Token count of every chunk's text, using the configured tokenizer."""
    return [len(encode(chunk.text)) for chunk in chunks]


def check_input_limits(
    chunks: list[Chunk], token_counts: list[int], max_input_tokens: int
) -> None:
    """Raise InputTooLongError listing every chunk over the model's limit."""
    oversized = [
        (chunk, tokens)
        for chunk, tokens in zip(chunks, token_counts)
        if tokens > max_input_tokens
    ]
    if oversized:
        raise InputTooLongError(max_input_tokens, oversized)


def make_batches(
    token_counts: list[int], *, batch_size: int, batch_max_tokens: int
) -> list[list[int]]:
    """Group chunk positions, capping both the count and the tokens per batch."""
    batches: list[list[int]] = []
    current: list[int] = []
    current_tokens = 0

    for position, tokens in enumerate(token_counts):
        if current and (
            len(current) >= batch_size or current_tokens + tokens > batch_max_tokens
        ):
            batches.append(current)
            current = []
            current_tokens = 0
        current.append(position)
        current_tokens += tokens

    if current:
        batches.append(current)
    return batches


def estimate_cost(total_tokens: int, price_per_1m_tokens: float) -> float:
    """Cost in USD of embedding ``total_tokens`` input tokens."""
    return total_tokens / TOKENS_PER_PRICE_UNIT * price_per_1m_tokens


def embed_chunks(
    config: EmbeddingConfig,
    chunks: list[Chunk],
    token_counts: list[int],
    client,
    *,
    batch_size: int | None = None,
    batch_max_tokens: int | None = None,
) -> np.ndarray:
    """Embed every chunk, returning float32 vectors in chunk order.

    ``client`` is any object exposing ``embeddings.create(...)`` with the OpenAI
    SDK's shape, which keeps the network out of the tests.
    """
    if len(token_counts) != len(chunks):
        raise ValueError("token_counts must have one entry per chunk")

    vectors = np.zeros((len(chunks), config.dimensions), dtype=np.float32)
    batches = make_batches(
        token_counts,
        batch_size=batch_size or config.batch_size,
        batch_max_tokens=batch_max_tokens or config.batch_max_tokens,
    )

    for batch in batches:
        response = client.embeddings.create(
            model=config.model,
            input=[chunks[position].text for position in batch],
            dimensions=config.dimensions,
            encoding_format="float",
        )
        if len(response.data) != len(batch):
            raise ValueError(
                f"{config.model} returned {len(response.data)} vectors for "
                f"{len(batch)} inputs"
            )

        seen: set[int] = set()
        for item in response.data:
            if item.index in seen or not 0 <= item.index < len(batch):
                raise ValueError(f"{config.model} returned an unexpected index")
            seen.add(item.index)
            position = batch[item.index]
            vector = np.asarray(item.embedding, dtype=np.float32)
            if vector.shape != (config.dimensions,):
                raise ValueError(
                    f"{config.model} returned {vector.size} dimensions for "
                    f"{chunks[position].label}; config expects {config.dimensions}"
                )
            vectors[position] = vector

        if len(seen) != len(batch):
            raise ValueError(f"{config.model} did not return every vector")

    return vectors


def build_metadata(
    source_id: str,
    chunks_path: Path,
    config: EmbeddingConfig,
    token_counts: list[int],
    vector_count: int,
) -> dict:
    """The sidecar written next to the vectors, so an index is reproducible."""
    total_tokens = sum(token_counts)
    return {
        "source_id": source_id,
        "provider": config.provider,
        "model": config.model,
        "dimensions": config.dimensions,
        "vector_count": vector_count,
        "chunk_file": Path(chunks_path).name,
        "chunk_file_sha256": sha256_file(chunks_path),
        "total_tokens": total_tokens,
        "max_chunk_tokens": max(token_counts),
        "price_per_1m_tokens": config.price_per_1m_tokens,
        "estimated_cost_usd": round(
            estimate_cost(total_tokens, config.price_per_1m_tokens), 8
        ),
        "created_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
    }


def write_index(vectors: np.ndarray, metadata: dict, out_dir: Path) -> tuple[Path, Path]:
    """Write <id>.npz and <id>.index.json atomically."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    source_id = metadata["source_id"]

    npz_path = out_dir / f"{source_id}.npz"
    meta_path = out_dir / f"{source_id}.index.json"

    npz_tmp = npz_path.with_name(f"{npz_path.name}.part")
    with npz_tmp.open("wb") as fh:
        np.savez(fh, **{VECTOR_KEY: vectors.astype(np.float32)})
    os.replace(npz_tmp, npz_path)

    meta_tmp = meta_path.with_name(f"{meta_path.name}.part")
    meta_tmp.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(meta_tmp, meta_path)

    return npz_path, meta_path


def load_env_file(env_path: Path) -> dict[str, str]:
    """Read simple KEY=VALUE lines from ``env_path``; empty when absent."""
    env_path = Path(env_path)
    if not env_path.exists():
        return {}

    values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip()
        if name.startswith("export "):
            name = name[len("export ") :].strip()
        values[name] = value.strip().strip('"').strip("'")
    return values


def api_key(env_file: Path = DEFAULT_ENV_FILE) -> str:
    """OPENAI_API_KEY from .env, else from the environment.

    The value is never returned to a log or an error message.
    """
    key = load_env_file(env_file).get(ENV_KEY, "").strip()
    if not key:
        key = os.environ.get(ENV_KEY, "").strip()
    if not key:
        raise RuntimeError(
            f"{ENV_KEY} is not set; add it to {Path(env_file).name} "
            f"(git-ignored, see .env.example) or export it"
        )
    return key


def make_tokenizer(config: EmbeddingConfig):
    """The tokenizer named in the config."""
    import tiktoken

    try:
        return tiktoken.get_encoding(config.tokenizer)
    except Exception as exc:  # unknown name or no cached encoding file
        raise RuntimeError(
            f"cannot load tokenizer {config.tokenizer!r}: {exc}"
        ) from exc


def make_client(config: EmbeddingConfig):
    """OpenAI client for the configured provider."""
    from openai import OpenAI

    return OpenAI(
        api_key=api_key(),
        timeout=DEFAULT_TIMEOUT_SECONDS,
        max_retries=DEFAULT_MAX_RETRIES,
    )


def run(
    source_id: str,
    *,
    config_path: Path = DEFAULT_CONFIG,
    chunks_dir: Path = DEFAULT_CHUNKS_DIR,
    out_dir: Path = DEFAULT_INDEX_DIR,
    client=None,
    tokenizer=None,
) -> dict:
    """Embed one source's chunks and write its index; returns the metadata."""
    config = load_config(config_path)
    chunks_path = Path(chunks_dir) / f"{source_id}.jsonl"
    chunks = read_chunks(chunks_path)

    tokenizer = tokenizer or make_tokenizer(config)
    token_counts = count_tokens(chunks, tokenizer.encode)
    check_input_limits(chunks, token_counts, config.max_input_tokens)

    client = client or make_client(config)
    vectors = embed_chunks(config, chunks, token_counts, client)

    metadata = build_metadata(
        source_id, chunks_path, config, token_counts, len(vectors)
    )
    write_index(vectors, metadata, out_dir)
    return metadata


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Embed one source's JSONL chunks into a float32 vector index."
    )
    parser.add_argument(
        "--source-id",
        required=True,
        help="id of the source, e.g. ref-01 (names <id>.jsonl and <id>.npz)",
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
        "--out-dir",
        type=Path,
        default=DEFAULT_INDEX_DIR,
        help=f"index output directory (default: {DEFAULT_INDEX_DIR})",
    )
    args = parser.parse_args(argv)

    try:
        metadata = run(
            args.source_id,
            config_path=args.config,
            chunks_dir=args.chunks_dir,
            out_dir=args.out_dir,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    npz_path = Path(args.out_dir) / f"{args.source_id}.npz"
    meta_path = Path(args.out_dir) / f"{args.source_id}.index.json"
    print(
        f"embedded {metadata['source_id']}: {metadata['vector_count']} chunks x "
        f"{metadata['dimensions']} dims ({metadata['model']})"
    )
    print(
        f"  total tokens {metadata['total_tokens']}; "
        f"largest chunk {metadata['max_chunk_tokens']} tokens"
    )
    print(
        f"  estimated cost ${metadata['estimated_cost_usd']} "
        f"({metadata['model']} @ ${metadata['price_per_1m_tokens']}/1M tokens)"
    )
    print(f"  {npz_path} ({npz_path.stat().st_size} bytes)")
    print(f"  {meta_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
