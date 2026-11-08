#!/usr/bin/env python3
"""Split one parsed source into article-level chunks for retrieval.

Input is the text written by parse_source.py (data/processed/<id>.txt), which is
page-marked but otherwise flat. The text is split on article headings — a line
that is exactly "المادة <ordinal>" and no longer than four tokens — so that the
chunk boundaries follow the document's own structure rather than a token count.

Two structural rules apply:

* Table-of-contents lines (the dotted leader lines at the front of the file) are
  dropped before anything else; they repeat every heading and would otherwise be
  mistaken for content.
* An executive-rule block ("القاعدة التنفيذية للمادة X") is never its own chunk:
  it is attached to the chunk of article X, whether it follows that article
  directly or not. Everything from the annex section heading onwards is emitted
  as a single chunk with kind "annex".

Provenance (title, url, sha256) comes from the sources list and the lock file;
nothing is hard-coded here.

Output, under data/processed/chunks (git-ignored), one JSON object per line:
    <id>.jsonl   source_id, title, url, sha256, kind, article_number, heading,
                 text, char_count

Usage:
    python backend/scripts/chunk_source.py --source-id ref-01
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from fetch_sources import (
    DEFAULT_CONFIG,
    DEFAULT_LOCK,
    REPO_ROOT,
    Source,
    load_sources,
    read_lock,
)

DEFAULT_PROCESSED_DIR = REPO_ROOT / "data" / "processed"
DEFAULT_CHUNKS_DIR = DEFAULT_PROCESSED_DIR / "chunks"

KIND_ARTICLE = "article"
KIND_ANNEX = "annex"

TOC_MARKER = "....."
ARTICLE_WORD = "المادة"
RULE_WORDS = ("القاعدة", "التنفيذية")
MAX_HEADING_TOKENS = 4
ANNEX_WORD = "الملحق"

_TATWEEL = "\u0640"
_DIACRITICS = re.compile(r"[\u064b-\u065f\u0670]")
# Letter variants that carry no meaning for a heading comparison.
_VARIANTS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي"})

# Definite feminine ordinals used on their own, 1-10 and the tens 20-70.
_STANDALONE = {
    "الاولي": 1,  # الأولى
    "الثانية": 2,
    "الثالثة": 3,
    "الرابعة": 4,
    "الخامسة": 5,
    "السادسة": 6,
    "السابعة": 7,
    "الثامنة": 8,
    "التاسعة": 9,
    "العاشرة": 10,
    "العشرون": 20,
    "الثلاثون": 30,
    "الاربعون": 40,  # الأربعون
    "الخمسون": 50,
    "الستون": 60,
    "السبعون": 70,
}

# The unit inside a compound ordinal is "الحادية", not "الأولى".
_COMPOUND_UNITS = {
    "الحادية": 1,
    "الثانية": 2,
    "الثالثة": 3,
    "الرابعة": 4,
    "الخامسة": 5,
    "السادسة": 6,
    "السابعة": 7,
    "الثامنة": 8,
    "التاسعة": 9,
}

_TEENS = {"عشرة": 10, "عشر": 10}
_TENS = {
    "العشرون": 20,
    "الثلاثون": 30,
    "الاربعون": 40,
    "الخمسون": 50,
    "الستون": 60,
    "السبعون": 70,
}
_CONJUNCTION = "و"

_ANNEX_HEADING_RE = re.compile(
    r"^\(?\s*[0-9\u0660-\u0669]+\s*\)?\s*" + ANNEX_WORD
)
_PAGE_MARKER_RE = re.compile(r"^\[\[page [0-9]+\]\]$")


@dataclass(frozen=True)
class Chunk:
    """One retrievable unit of the source."""

    kind: str
    article_number: int | None
    heading: str
    text: str

    @property
    def char_count(self) -> int:
        return len(self.text)


@dataclass
class _Draft:
    """A chunk under construction: its lines are still being collected."""

    kind: str
    article_number: int | None
    heading: str
    lines: list[str] = field(default_factory=list)


def normalise_arabic(text: str) -> str:
    """Fold letter variants and drop tatweel/diacritics before matching.

    Only used for comparisons; the text that is written out keeps its original
    spelling.
    """
    folded = unicodedata.normalize("NFKC", text).replace(_TATWEEL, "")
    return _DIACRITICS.sub("", folded).translate(_VARIANTS)


def parse_ordinal(text: str) -> int | None:
    """Arabic ordinal (1-73) to int, or None when ``text`` is not one.

    Handles the three shapes used in the source: a single word ("العشرون" = 20),
    a teen ("الحادية عشرة" = 11) and a compound ("الثالثة والعشرون" = 23). Both
    "عشر" and "عشرة" are accepted as ten, because the executive-rule headings use
    the short form ("للمادة السابعة عشر").
    """
    tokens = normalise_arabic(text).split()

    if len(tokens) == 1:
        return _STANDALONE.get(tokens[0])

    if len(tokens) == 2:
        unit_word, tail = tokens
        if unit_word in _COMPOUND_UNITS and tail in _TEENS:
            return _COMPOUND_UNITS[unit_word] + _TEENS[tail]
        if unit_word in _COMPOUND_UNITS and tail.startswith(_CONJUNCTION):
            tens = _TENS.get(tail[len(_CONJUNCTION) :])
            if tens is not None:
                return _COMPOUND_UNITS[unit_word] + tens
        return None

    if len(tokens) == 3:
        unit_word, conjunction, tens_word = tokens
        if (
            unit_word in _COMPOUND_UNITS
            and conjunction == _CONJUNCTION
            and tens_word in _TENS
        ):
            return _COMPOUND_UNITS[unit_word] + _TENS[tens_word]
        return None

    return None


def is_toc_line(line: str) -> bool:
    """True for the dotted-leader table-of-contents lines."""
    return TOC_MARKER in line


def parse_article_heading(line: str) -> tuple[int, str] | None:
    """``(article number, heading)`` when ``line`` is an article heading.

    The whole line must be the heading: "المادة" followed by an ordinal that
    parses completely. That keeps cross-references such as
    "المادة السابعة والأربعون   .أ" inside the text they belong to.
    """
    tokens = normalise_arabic(line).split()
    if not 2 <= len(tokens) <= MAX_HEADING_TOKENS:
        return None
    if tokens[0] != ARTICLE_WORD:
        return None

    number = parse_ordinal(" ".join(tokens[1:]))
    if number is None:
        return None
    return number, line.strip()


def parse_rule_heading(line: str) -> tuple[int, str] | None:
    """``(article number, heading)`` for a "القاعدة التنفيذية للمادة X" line."""
    tokens = normalise_arabic(line).split()
    if len(tokens) < 4 or tuple(tokens[:2]) != RULE_WORDS:
        return None
    if not tokens[2].startswith("للمادة"):
        return None

    number = parse_ordinal(" ".join(tokens[3:]))
    if number is None:
        return None
    return number, line.strip()


def is_annex_heading(line: str) -> bool:
    """True for the annex section heading ("... الملحقات" or "(1) الملحق")."""
    stripped = normalise_arabic(line).strip()
    if ANNEX_WORD not in stripped:
        return False
    return stripped.startswith("القسم") or bool(_ANNEX_HEADING_RE.match(stripped))


def _build_text(lines: list[str]) -> str:
    """Join a chunk's lines, dropping trailing spaces and blank edges.

    A page marker left at the very end of a chunk marks a page whose text belongs
    to the next chunk, so it goes with the blank lines around it.
    """
    cleaned = [line.rstrip() for line in lines]
    while cleaned and not cleaned[0].strip():
        cleaned.pop(0)
    while cleaned and (
        not cleaned[-1].strip() or _PAGE_MARKER_RE.match(cleaned[-1].strip())
    ):
        cleaned.pop()
    return "\n".join(cleaned).strip()


def split_chunks(lines: list[str]) -> list[Chunk]:
    """Split document lines into article chunks plus one annex chunk.
    Lines before the first article heading (cover page, table of contents) are
    dropped. Executive-rule blocks are attached to the article they name, even
    when they follow a different article; a block naming an article that does not
    exist is kept where it stands.
    """
    drafts: list[_Draft] = []
    annex: _Draft | None = None
    current: _Draft | None = None
    # Rule blocks whose article is not the one they follow, keyed by article.
    detached: dict[int, list[str]] = {}

    index = 0
    while index < len(lines):
        line = lines[index]

        if is_toc_line(line):
            index += 1
            continue

        if annex is not None:
            annex.lines.append(line)
            index += 1
            continue

        if is_annex_heading(line):
            current = None
            annex = _Draft(KIND_ANNEX, None, line.strip(), [line])
            index += 1
            continue

        heading = parse_article_heading(line)
        if heading is not None:
            number, heading_text = heading
            current = _Draft(KIND_ARTICLE, number, heading_text, [line])
            drafts.append(current)
            index += 1
            continue

        rule = parse_rule_heading(line)
        if rule is not None and current is not None and rule[0] != current.article_number:
            end = _rule_block_end(lines, index + 1)
            detached.setdefault(rule[0], []).extend(lines[index:end])
            index = end
            continue

        if current is not None:
            current.lines.append(line)
        index += 1

    chunks: list[Chunk] = []
    for draft in drafts:
        lines_of_chunk = list(draft.lines)
        extra = detached.pop(draft.article_number, None)
        if extra:
            lines_of_chunk.extend(extra)
        chunks.append(
            Chunk(
                kind=draft.kind,
                article_number=draft.article_number,
                heading=draft.heading,
                text=_build_text(lines_of_chunk),
            )
        )

    # A rule block naming an article the document does not have stays where it
    # was written rather than being lost.
    for orphan_lines in detached.values():
        chunks.append(
            Chunk(
                kind=KIND_ARTICLE,
                article_number=None,
                heading=orphan_lines[0].strip(),
                text=_build_text(orphan_lines),
            )
        )

    if annex is not None:
        chunks.append(
            Chunk(
                kind=KIND_ANNEX,
                article_number=None,
                heading=annex.heading,
                text=_build_text(annex.lines),
            )
        )

    return chunks


def _rule_block_end(lines: list[str], start: int) -> int:
    """Index just past the rule block that starts before ``start``."""
    index = start
    while index < len(lines):
        line = lines[index]
        if (
            parse_article_heading(line) is not None
            or parse_rule_heading(line) is not None
            or is_annex_heading(line)
        ):
            break
        index += 1
    return index


def build_records(
    source: Source, sha256: str, chunks: list[Chunk]
) -> list[dict]:
    """One output record per chunk, carrying the source's provenance."""
    return [
        {
            "source_id": source.id,
            "title": source.title,
            "url": source.url,
            "sha256": sha256,
            "kind": chunk.kind,
            "article_number": chunk.article_number,
            "heading": chunk.heading,
            "text": chunk.text,
            "char_count": chunk.char_count,
        }
        for chunk in chunks
    ]


def write_jsonl(path: Path, records: list[dict]) -> None:
    """Write one JSON object per line, UTF-8, LF endings."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def chunk_source(
    source: Source,
    expected_sha256: str,
    *,
    processed_dir: Path,
    out_dir: Path,
) -> list[dict]:
    """Read the parsed text of ``source`` and write its chunks."""
    processed_dir = Path(processed_dir)
    txt_path = processed_dir / f"{source.id}.txt"
    if not txt_path.exists():
        raise FileNotFoundError(
            f"{txt_path} not found; run parse_source.py --source-id {source.id}"
        )

    meta_path = processed_dir / f"{source.id}.meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        parsed_sha256 = meta.get("sha256")
        if parsed_sha256 and parsed_sha256 != expected_sha256:
            raise ValueError(
                f"{meta_path} was parsed from sha256 {parsed_sha256}, lock file "
                f"has {expected_sha256}; re-run parse_source.py "
                f"--source-id {source.id}"
            )

    lines = txt_path.read_text(encoding="utf-8").splitlines()
    records = build_records(source, expected_sha256, split_chunks(lines))

    write_jsonl(Path(out_dir) / f"{source.id}.jsonl", records)
    return records


def summarise(records: list[dict]) -> dict:
    """Counts reported after a run."""
    article_numbers = sorted(
        {
            record["article_number"]
            for record in records
            if record["article_number"] is not None
        }
    )
    counts = [record["char_count"] for record in records]
    return {
        "chunks": len(records),
        "articles": sum(1 for r in records if r["kind"] == KIND_ARTICLE),
        "annex": sum(1 for r in records if r["kind"] == KIND_ANNEX),
        "distinct_articles": len(article_numbers),
        "min_char_count": min(counts) if counts else 0,
        "max_char_count": max(counts) if counts else 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Split one parsed source into article-level JSONL chunks."
    )
    parser.add_argument(
        "--source-id",
        required=True,
        help="id of the source in the sources list, e.g. ref-01",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"sources list file (default: {DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "--lock",
        type=Path,
        default=DEFAULT_LOCK,
        help=f"provenance lock file (default: {DEFAULT_LOCK})",
    )
    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=DEFAULT_PROCESSED_DIR,
        help=f"directory holding the parsed text (default: {DEFAULT_PROCESSED_DIR})",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_CHUNKS_DIR,
        help=f"chunk output directory (default: {DEFAULT_CHUNKS_DIR})",
    )
    args = parser.parse_args(argv)

    try:
        sources = load_sources(args.config)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    source = next((s for s in sources if s.id == args.source_id), None)
    if source is None:
        known = ", ".join(sorted(s.id for s in sources))
        print(
            f"error: unknown source id {args.source_id!r}; known: {known}",
            file=sys.stderr,
        )
        return 2

    try:
        lock = read_lock(args.lock)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    entry = lock["documents"].get(source.id)
    if not entry or not entry.get("sha256"):
        print(
            f"error: {source.id} has no entry in {args.lock}; "
            f"run fetch_sources.py --source-id {source.id} first",
            file=sys.stderr,
        )
        return 2

    try:
        records = chunk_source(
            source,
            entry["sha256"],
            processed_dir=args.processed_dir,
            out_dir=args.out_dir,
        )
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    stats = summarise(records)
    out_path = Path(args.out_dir) / f"{source.id}.jsonl"
    print(
        f"chunked {source.id}: {stats['chunks']} chunks "
        f"({stats['articles']} article, {stats['annex']} annex)"
    )
    print(
        f"  distinct article_number values: {stats['distinct_articles']}; "
        f"char_count min {stats['min_char_count']}, max {stats['max_char_count']}"
    )
    print(f"  {out_path} ({out_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
