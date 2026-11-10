#!/usr/bin/env python3
"""Turn one downloaded source PDF into cleaned text plus a meta file.

The source id is looked up in the sources list (backend/config/sources.toml) and
its SHA-256 in the lock file (backend/config/sources.lock.json); neither the URL
nor the file name is hard-coded here.

Outputs, under data/processed (git-ignored):
    <id>.txt         page text, each page preceded by a "[[page N]]" marker
    <id>.meta.json   source id, lock SHA-256, page count, char count

Usage:
    python backend/scripts/parse_source.py --source-id ref-01
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

import pymupdf

from fetch_sources import (
    DEFAULT_CONFIG,
    DEFAULT_LOCK,
    DEFAULT_OUT_DIR as DEFAULT_RAW_DIR,
    REPO_ROOT,
    Source,
    load_sources,
    read_lock,
    sha256_file,
)

DEFAULT_OUT_DIR = REPO_ROOT / "data" / "processed"
PAGE_MARKER = "[[page {number}]]"

TATWEEL = "\u0640"
ARABIC_INDIC_DIGITS = "\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669"
ARABIC_PERCENT = "\u066a"

_DIGIT_RUN_RE = re.compile(r"[\u0660-\u0669]+")
# The PDF draws the percent sign to the left of its number, so it is extracted
# first: "٪٥٢" is the visual order of "٢٥٪".
_PERCENT_BEFORE_NUMBER_RE = re.compile(r"\u066a(\s*)([0-9\u0660-\u0669]+)")
_DIGITS_TO_ASCII = str.maketrans(ARABIC_INDIC_DIGITS, "0123456789")


def fix_arabic_digits(text: str) -> str:
    """Reverse every maximal Arabic-Indic digit run, then map it to ASCII.

    The PDF stores these numbers visually, so a logical 1442 is extracted as ٢٤٤١;
    reversing the run restores the order and the mapping makes the digits searchable.
    Only runs of U+0660-U+0669 are touched, so ASCII runs such as "2,75" are
    returned unchanged.
    """
    return _DIGIT_RUN_RE.sub(
        lambda match: match.group(0)[::-1].translate(_DIGITS_TO_ASCII), text
    )


def fix_arabic_percent(text: str) -> str:
    """Move a percent sign that precedes its number to after it, as ASCII "%".

    "٪٥٢" is the visual order of "٢٥٪": the sign is put back on the right of
    the number and mapped to "%", so "لا تزيد عن 25%" keeps its meaning. A sign
    that does not directly precede a number is only mapped to "%".
    """
    moved = _PERCENT_BEFORE_NUMBER_RE.sub(
        lambda match: f"{match.group(2)}{match.group(1)}%", text
    )
    return moved.replace(ARABIC_PERCENT, "%")


def clean_text(text: str) -> str:
    """Normalise to NFKC, drop tatweel, then repair digits and percent signs.

    NFKC runs first so presentation forms and ligatures fold to their canonical
    letters; tatweel has no compatibility decomposition, so it survives that step
    and is removed explicitly. NFKC leaves Arabic-Indic digits alone, so they are
    fixed afterwards (see fix_arabic_digits).
    """
    normalised = unicodedata.normalize("NFKC", text).replace(TATWEEL, "")
    return fix_arabic_digits(fix_arabic_percent(normalised))


def extract_pages(pdf_path: Path) -> list[str]:
    """Raw text of every page, in document order."""
    with pymupdf.open(str(pdf_path)) as doc:
        if doc.needs_pass:
            doc.authenticate("")
        return [page.get_text() for page in doc]


def build_document(pages: list[str]) -> str:
    """Join cleaned pages with a page marker before each one."""
    parts: list[str] = []
    for number, text in enumerate(pages, start=1):
        parts.append(PAGE_MARKER.format(number=number))
        parts.append(text)

    return "\n".join(parts) + "\n"


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def parse(
    source: Source,
    expected_sha256: str,
    *,
    raw_dir: Path,
    out_dir: Path,
) -> dict:
    """Parse one downloaded PDF and write its text and meta files.

    ``expected_sha256`` is the hash recorded in the lock file. The file on disk is
    hashed again before parsing: if the two differ, the source is stale and the
    meta file would be wrong, so parsing stops.
    """
    pdf_path = Path(raw_dir) / source.filename
    if not pdf_path.exists():
        raise FileNotFoundError(
            f"{pdf_path} not found; run fetch_sources.py --source-id {source.id}"
        )

    actual_sha256 = sha256_file(pdf_path)
    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"hash mismatch for {pdf_path}: lock file has {expected_sha256}, "
            f"file has {actual_sha256}; re-run fetch_sources.py --source-id {source.id}"
        )

    pages = [clean_text(text) for text in extract_pages(pdf_path)]
    document = build_document(pages)

    out_dir = Path(out_dir)
    _write_text(out_dir / f"{source.id}.txt", document)

    meta = {
        "source_id": source.id,
        "sha256": expected_sha256,
        "page_count": len(pages),
        "char_count": len(document),
    }
    _write_text(
        out_dir / f"{source.id}.meta.json",
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
    )
    return meta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract cleaned, page-marked text from one downloaded source PDF."
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
        "--raw-dir",
        type=Path,
        default=DEFAULT_RAW_DIR,
        help=f"directory holding the downloaded PDFs (default: {DEFAULT_RAW_DIR})",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help=f"output directory (default: {DEFAULT_OUT_DIR})",
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
        meta = parse(
            source,
            entry["sha256"],
            raw_dir=args.raw_dir,
            out_dir=args.out_dir,
        )
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    txt_path = args.out_dir / f"{source.id}.txt"
    meta_path = args.out_dir / f"{source.id}.meta.json"
    print(
        f"parsed {meta['source_id']}: {meta['page_count']} pages, "
        f"{meta['char_count']} chars"
    )
    print(f"  {txt_path} ({txt_path.stat().st_size} bytes)")
    print(f"  {meta_path} ({meta_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
