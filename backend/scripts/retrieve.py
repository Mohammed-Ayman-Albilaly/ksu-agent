#!/usr/bin/env python3
"""Retrieve the chunks most similar to a query from one source's index.

The vectors come from embed_chunks.py (data/processed/index/<id>.npz) and the
chunks from chunk_source.py (data/processed/chunks/<id>.jsonl). The query is
cleaned with parse_source.clean_text — the same NFKC + tatweel removal applied
to the source text before it was chunked — then embedded with the model pinned
in backend/config/embeddings.toml, so the query and the chunks live in one
vector space. Embeddings from different models are never compared.

Three modes are available, selected with --mode:

* ``dense``   — cosine similarity over the stored vectors, highest first.
* ``lexical`` — BM25 over the chunk texts, with the same cleaning and an Arabic
  stopword-insensitive tokenizer, so a word the query shares with an article
  counts even when the vectors rank that article poorly.
* ``hybrid``  — the two rankings fused with Reciprocal Rank Fusion (k=60), so a
  chunk both rankers agree on outranks a chunk only one of them found.

The default is ``hybrid``. In hybrid mode the reported score is the RRF score,
not a cosine similarity, so scores are only comparable within one mode.

Usage:
    python backend/scripts/retrieve.py --source-id ref-01 --query "..." --k 5
"""

from __future__ import annotations

import argparse
import json
import math
import re
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

MODE_DENSE = "dense"
MODE_LEXICAL = "lexical"
MODE_HYBRID = "hybrid"
MODES = (MODE_DENSE, MODE_LEXICAL, MODE_HYBRID)
DEFAULT_MODE = MODE_HYBRID

# Reciprocal Rank Fusion constant from the original RRF paper: it flattens the
# weight of the very top ranks so one ranker cannot dominate the fusion.
RRF_K = 60

# BM25 defaults: k1 controls term-frequency saturation, b the length normalisation.
BM25_K1 = 1.5
BM25_B = 0.75

# A word, plus any decimal tail: "2,75" stays one token instead of splitting into
# two numbers that would then match every article mentioning either digit.
_WORD = re.compile(r"[^\W_]+(?:[.,][^\W_]+)*")

# Words that carry no retrieval signal in an Arabic student question. They are
# compared after the same folding the tokenizer applies (alef forms, ta marbuta left
# alone), so entries are written in their folded form.
_STOPWORD_SOURCE = """
من في على عن إلى الى مع هذا هذه هذي ذلك تلك هؤلاء الذي التي الذين اللاتي
اللذان اللتان ما ماذا لم لن لا قد كان كانت يكون تكون هو هي هم هن أنا أنت
نحن أن إن أو ثم بل لكن حتى إذا اذا حيث عند بعد قبل بين كل بعض غير سوى
نحو خلال ضمن وفق وفقا بناء بالنسبة أيضا ايضا فقط جدا عليه عليها منه منها فيه
فيها به بها له لها لدى لدي وهو وهي ومن وفي ولا هل أ لماذا لماذا أي اي
اللي وش ايش كيف متى أين اين كم كام
"""

_TASHKEEL = re.compile(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]")
_ALEF_FORMS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي"})


def fold_word(word: str) -> str:
    """One word reduced to its matching form: cleaned, no tashkeel, folded alef/ya."""
    return _TASHKEEL.sub("", clean_text(word)).translate(_ALEF_FORMS)


ARABIC_STOPWORDS = frozenset(
    fold_word(word) for word in _STOPWORD_SOURCE.split()
)


def tokenize(text: str) -> list[str]:
    """Content words of ``text`` for lexical matching.

    The text is cleaned exactly as the query is for embedding (NFKC + tatweel), then
    split into words, with tashkeel removed and alef/ya forms folded so "الحد" and
    "ألحد" match. Stopwords and one-letter words are dropped: they appear in
    nearly every article, so they separate nothing. Numbers are kept, because
    "2,75" and "25%" are exactly what a student asks about.
    """
    tokens: list[str] = []
    for word in _WORD.findall(clean_text(text)):
        token = fold_word(word)
        if not token:
            continue
        if token.isdigit():
            tokens.append(token)
        elif len(token) > 1 and token not in ARABIC_STOPWORDS:
            tokens.append(token)
    return tokens


def order_descending(scores: np.ndarray) -> list[int]:
    """Chunk positions, highest score first; equal scores keep index order."""
    if scores.ndim != 1:
        raise ValueError("scores must be a 1-D array")
    return [int(position) for position in np.argsort(-scores, kind="stable")]


@dataclass(frozen=True)
class BM25Index:
    """Term statistics for BM25 over one source's chunks."""

    term_frequencies: tuple[dict[str, int], ...]
    lengths: tuple[int, ...]
    document_frequency: dict[str, int]
    average_length: float
    k1: float = BM25_K1
    b: float = BM25_B

    @property
    def document_count(self) -> int:
        return len(self.term_frequencies)


@dataclass(frozen=True)
class Chunk:
    """One indexed chunk, as read from the JSONL written by chunk_source.py.

    ``title`` and ``url`` are the source's provenance, copied from the same
    record, so a caller can cite the chunk without loading the sources list.
    """

    index: int
    article_number: int | None
    heading: str
    text: str
    title: str = ""
    url: str = ""
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


def build_bm25_index(
    chunks: list[Chunk], *, k1: float = BM25_K1, b: float = BM25_B
) -> BM25Index:
    """Tokenise every chunk once and keep the term statistics BM25 needs."""
    if not chunks:
        raise ValueError("cannot build a BM25 index from no chunks")
    if k1 <= 0:
        raise ValueError("k1 must be positive")
    if not 0.0 <= b <= 1.0:
        raise ValueError("b must be between 0 and 1")

    term_frequencies: list[dict[str, int]] = []
    lengths: list[int] = []
    document_frequency: dict[str, int] = {}
    for chunk in chunks:
        tokens = tokenize(chunk.text)
        counts: dict[str, int] = {}
        for token in tokens:
            counts[token] = counts.get(token, 0) + 1
        term_frequencies.append(counts)
        lengths.append(len(tokens))
        for token in counts:
            document_frequency[token] = document_frequency.get(token, 0) + 1

    average_length = sum(lengths) / len(lengths)
    return BM25Index(
        term_frequencies=tuple(term_frequencies),
        lengths=tuple(lengths),
        document_frequency=document_frequency,
        average_length=average_length,
        k1=k1,
        b=b,
    )


def bm25_scores(index: BM25Index, query: str) -> np.ndarray:
    """BM25 score of every chunk for ``query``, in chunk order.

    A word the corpus never contains scores nothing; a query with no content words
    after tokenisation scores every chunk zero. A word repeated in the query counts
    once, so a student repeating themselves does not tilt the ranking.
    """
    scores = np.zeros(index.document_count, dtype=np.float32)
    terms = list(dict.fromkeys(tokenize(query)))
    if not terms or index.average_length == 0:
        return scores

    for term in terms:
        frequency = index.document_frequency.get(term, 0)
        if frequency == 0:
            continue
        # BM25's probabilistic idf, always positive for a term the corpus contains.
        idf = math.log(
            1 + (index.document_count - frequency + 0.5) / (frequency + 0.5)
        )
        for position, counts in enumerate(index.term_frequencies):
            term_frequency = counts.get(term, 0)
            if term_frequency == 0:
                continue
            length_norm = 1 - index.b + index.b * (
                index.lengths[position] / index.average_length
            )
            scores[position] += (
                idf
                * (term_frequency * (index.k1 + 1))
                / (term_frequency + index.k1 * length_norm)
            )
    return scores


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[int]], *, rrf_k: int = RRF_K
) -> list[tuple[int, float]]:
    """Fuse ranked chunk positions into ``(chunk position, score)``, best first.

    Each list contributes 1 / (rrf_k + rank) to a chunk, with ranks starting at 1,
    so a chunk that both rankers place near the top beats one that only a single
    ranker found. Equal fused scores keep the lower chunk position first, which
    makes a run repeatable.
    """
    if rrf_k < 1:
        raise ValueError("rrf_k must be at least 1")

    fused: dict[int, float] = {}
    for ranking in rankings:
        for position, chunk_position in enumerate(ranking, start=1):
            if chunk_position < 0:
                raise ValueError("rankings hold chunk positions, not negatives")
            fused[chunk_position] = fused.get(chunk_position, 0.0) + 1.0 / (
                rrf_k + position
            )
    return sorted(fused.items(), key=lambda item: (-item[1], item[0]))


def fuse(
    rankings: Sequence[Sequence[int]],
    chunks: list[Chunk],
    k: int,
    *,
    rrf_k: int = RRF_K,
) -> list[SearchResult]:
    """The top ``k`` chunks of the fused ranking, scored by their RRF score."""
    if k < 1:
        raise ValueError("k must be at least 1")

    fused = reciprocal_rank_fusion(rankings, rrf_k=rrf_k)
    for chunk_position, _score in fused:
        if chunk_position >= len(chunks):
            raise ValueError(
                f"ranking holds chunk position {chunk_position} but there are "
                f"{len(chunks)} chunks"
            )
    return [
        SearchResult(score=score, chunk=chunks[chunk_position])
        for chunk_position, score in fused[:k]
    ]


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
                    title=str(record.get("title", "")),
                    url=str(record.get("url", "")),
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


def check_mode(mode: str) -> str:
    """The mode, or a ValueError naming the ones that exist."""
    if mode not in MODES:
        raise ValueError(
            f"unknown mode {mode!r}; choose from {', '.join(MODES)}"
        )
    return mode


def search_chunks(
    query: str,
    *,
    vectors: np.ndarray,
    chunks: list[Chunk],
    bm25: BM25Index,
    mode: str = DEFAULT_MODE,
    config: EmbeddingConfig | None = None,
    client=None,
    tokenizer=None,
    k: int = DEFAULT_K,
) -> list[SearchResult]:
    """Rank one source's chunks for ``query`` in the requested mode.

    ``dense`` and ``hybrid`` embed the query, so they need the embedding config, a
    client and a tokenizer; ``lexical`` needs none of them and never calls the
    provider. In hybrid mode a query with no content words has nothing to match
    lexically, so the dense ranking stands alone rather than failing the search.
    """
    check_mode(mode)
    if k < 1:
        raise ValueError("k must be at least 1")
    if len(vectors) != len(chunks):
        raise ValueError("vectors must have one row per chunk")

    dense_scores: np.ndarray | None = None
    lexical_scores: np.ndarray | None = None

    if mode in (MODE_DENSE, MODE_HYBRID):
        if config is None or client is None or tokenizer is None:
            raise ValueError(
                f"{mode} mode needs the embedding config, a client and a tokenizer"
            )
        _normalized, query_vector = embed_query(
            query, config, client, tokenizer=tokenizer
        )
        dense_scores = cosine_scores(vectors, query_vector)

    if mode in (MODE_LEXICAL, MODE_HYBRID):
        if not tokenize(query):
            if mode == MODE_LEXICAL:
                raise ValueError("query has no searchable words after cleaning")
        else:
            lexical_scores = bm25_scores(bm25, query)

    if mode == MODE_DENSE:
        return rank(dense_scores, chunks, k)
    if mode == MODE_LEXICAL:
        return rank(lexical_scores, chunks, k)

    rankings = [order_descending(dense_scores)]
    if lexical_scores is not None:
        rankings.append(order_descending(lexical_scores))
    return fuse(rankings, chunks, k)


def retrieve(
    source_id: str,
    query: str,
    *,
    k: int = DEFAULT_K,
    mode: str = DEFAULT_MODE,
    config_path: Path = DEFAULT_CONFIG,
    chunks_dir: Path = DEFAULT_CHUNKS_DIR,
    index_dir: Path = DEFAULT_INDEX_DIR,
    client=None,
    tokenizer=None,
) -> list[SearchResult]:
    """Search one source's index for ``query`` and return the top ``k`` chunks."""
    check_mode(mode)
    config = load_config(config_path)
    vectors, chunks, _metadata = load_index(
        source_id, config, chunks_dir=chunks_dir, index_dir=index_dir
    )
    bm25 = build_bm25_index(chunks)

    needs_embeddings = mode in (MODE_DENSE, MODE_HYBRID)
    client = client or (make_client(config) if needs_embeddings else None)
    if needs_embeddings and tokenizer is None:
        tokenizer = make_tokenizer(config)

    return search_chunks(
        query,
        vectors=vectors,
        chunks=chunks,
        bm25=bm25,
        mode=mode,
        config=config,
        client=client,
        tokenizer=tokenizer,
        k=k,
    )


def make_searcher(
    source_id: str,
    *,
    mode: str = DEFAULT_MODE,
    config_path: Path = DEFAULT_CONFIG,
    chunks_dir: Path = DEFAULT_CHUNKS_DIR,
    index_dir: Path = DEFAULT_INDEX_DIR,
    client=None,
    tokenizer=None,
):
    """Load one source's index once and return ``search(query, k)``.

    The index and the BM25 statistics are read on the first call and kept in
    memory, so a long-running caller (the API) pays the load cost once instead of
    per question.
    """
    check_mode(mode)
    config = load_config(config_path)
    vectors, chunks, _metadata = load_index(
        source_id, config, chunks_dir=chunks_dir, index_dir=index_dir
    )
    bm25 = build_bm25_index(chunks)

    needs_embeddings = mode in (MODE_DENSE, MODE_HYBRID)
    client = client or (make_client(config) if needs_embeddings else None)
    tokenizer = tokenizer or (
        make_tokenizer(config) if needs_embeddings else None
    )

    def search(query: str, k: int = DEFAULT_K) -> list[SearchResult]:
        return search_chunks(
            query,
            vectors=vectors,
            chunks=chunks,
            bm25=bm25,
            mode=mode,
            config=config,
            client=client,
            tokenizer=tokenizer,
            k=k,
        )

    return search


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
        "--mode",
        choices=MODES,
        default=DEFAULT_MODE,
        help=f"ranking to use (default: {DEFAULT_MODE})",
    )
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
            mode=args.mode,
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
