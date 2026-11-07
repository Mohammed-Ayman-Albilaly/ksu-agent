#!/usr/bin/env python3
"""Download the KSU source documents listed in backend/config/sources.toml.

Each file is saved under the output directory (default: data/raw, which is
git-ignored) and its provenance — URL, download date and SHA-256 — is recorded
in the lock file (default: backend/config/sources.lock.json), which is tracked
in git so the downloaded documents can be verified after the fact.

URLs are never hard-coded here: they come from the sources list, so a new or
replaced document is a config change, not a code change.

Usage:
    python backend/scripts/fetch_sources.py
    python backend/scripts/fetch_sources.py --source-id ref-01 --force
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "backend" / "config" / "sources.toml"
DEFAULT_OUT_DIR = REPO_ROOT / "data" / "raw"
DEFAULT_LOCK = REPO_ROOT / "backend" / "config" / "sources.lock.json"
LOCK_VERSION = 1
MANIFEST_VERSION = 1
CHUNK_SIZE = 64 * 1024
DEFAULT_TIMEOUT = 60
USER_AGENT = "ksu-agent-ingest/1.0"
REQUIRED_FIELDS = ("id", "url", "filename")


@dataclass(frozen=True)
class Source:
    """One document to download, as declared in the sources list."""

    id: str
    url: str
    filename: str
    title: str = ""


@dataclass
class Result:
    """Outcome of one source: status is 'downloaded', 'skipped' or 'failed'."""

    source_id: str
    filename: str
    status: str
    sha256: str | None = None
    error: str | None = None


def load_sources(config_path: Path) -> list[Source]:
    """Read and validate the sources list."""
    with Path(config_path).open("rb") as fh:
        data = tomllib.load(fh)

    raw_sources = data.get("source", [])
    if not isinstance(raw_sources, list) or not raw_sources:
        raise ValueError(f"{config_path}: no [[source]] entries found")

    sources: list[Source] = []
    seen: set[str] = set()
    for index, entry in enumerate(raw_sources, start=1):
        missing = [field for field in REQUIRED_FIELDS if not entry.get(field)]
        if missing:
            raise ValueError(
                f"{config_path}: [[source]] #{index} is missing {', '.join(missing)}"
            )

        source_id = str(entry["id"]).strip()
        if source_id in seen:
            raise ValueError(f"{config_path}: duplicate source id {source_id!r}")
        seen.add(source_id)

        filename = str(entry["filename"]).strip()
        if Path(filename).name != filename:
            raise ValueError(
                f"{config_path}: source {source_id!r} filename must be a bare "
                f"file name, got {filename!r}"
            )

        url = str(entry["url"]).strip()
        if not url.lower().startswith(("http://", "https://")):
            raise ValueError(
                f"{config_path}: source {source_id!r} url must be http(s), got {url!r}"
            )

        sources.append(
            Source(
                id=source_id,
                url=url,
                filename=filename,
                title=str(entry.get("title", "")).strip(),
            )
        )

    return sources


def sha256_file(path: Path) -> str:
    """SHA-256 of an existing file, read in chunks."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_lock(lock_path: Path) -> dict:
    """Load the lock file, returning an empty one when it does not exist yet."""
    lock_path = Path(lock_path)
    if not lock_path.exists():
        return {"version": LOCK_VERSION, "documents": {}}

    data = json.loads(lock_path.read_text(encoding="utf-8"))
    data.setdefault("version", LOCK_VERSION)
    data.setdefault("documents", {})
    return data


def write_lock(lock_path: Path, lock: dict) -> None:
    """Write the lock file atomically, with a stable key order for clean diffs."""
    lock_path = Path(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock["documents"] = dict(sorted(lock["documents"].items()))

    tmp_path = lock_path.with_name(f"{lock_path.name}.part")
    tmp_path.write_text(
        json.dumps(lock, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp_path, lock_path)


def _already_downloaded(source: Source, out_dir: Path, lock: dict) -> bool:
    """True when the saved file still matches the hash recorded for it."""
    entry = lock["documents"].get(source.id)
    if not entry or entry.get("url") != source.url:
        return False

    path = out_dir / source.filename
    if not path.exists() or entry.get("sha256") != sha256_file(path):
        return False

    return True


def download(source: Source, out_dir: Path, timeout: float = DEFAULT_TIMEOUT) -> dict:
    """Stream the source to disk and return its lock entry.

    The body is written to a ``.part`` file and only moved into place once the
    full response has been read, so a failed download never leaves a truncated
    file behind.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    request = Request(source.url, headers={"User-Agent": USER_AGENT})
    digest = hashlib.sha256()
    size = 0

    handle = tempfile.NamedTemporaryFile(
        dir=out_dir,
        prefix=f"{source.filename}.",
        suffix=".part",
        delete=False,
    )
    tmp_path = Path(handle.name)
    try:
        with handle, urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type", "")
            for chunk in iter(lambda: response.read(CHUNK_SIZE), b""):
                digest.update(chunk)
                size += len(chunk)
                handle.write(chunk)
        os.replace(tmp_path, out_dir / source.filename)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise

    return {
        "source_id": source.id,
        "title": source.title,
        "filename": source.filename,
        "url": source.url,
        "downloaded_at": _utc_now(),
        "sha256": digest.hexdigest(),
        "bytes": size,
        "content_type": content_type,
    }


def run(
    sources: list[Source],
    out_dir: Path,
    lock_path: Path,
    *,
    force: bool = False,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[Result]:
    """Download every source, updating the lock file as it goes."""
    out_dir = Path(out_dir)
    lock = read_lock(lock_path)
    results: list[Result] = []

    for source in sources:
        if not force and _already_downloaded(source, out_dir, lock):
            results.append(
                Result(
                    source_id=source.id,
                    filename=source.filename,
                    status="skipped",
                    sha256=lock["documents"][source.id]["sha256"],
                )
            )
            continue

        try:
            entry = download(source, out_dir, timeout=timeout)
        except (HTTPError, URLError, OSError, ValueError) as exc:
            results.append(
                Result(
                    source_id=source.id,
                    filename=source.filename,
                    status="failed",
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
            continue

        lock["documents"][source.id] = entry
        write_lock(lock_path, lock)
        results.append(
            Result(
                source_id=source.id,
                filename=source.filename,
                status="downloaded",
                sha256=entry["sha256"],
            )
        )

    write_lock(lock_path, lock)
    return results


def _report(results: list[Result]) -> None:
    for result in results:
        if result.status == "failed":
            print(f"failed      {result.source_id}  {result.error}")
        elif result.status == "skipped":
            print(f"skipped     {result.source_id}  {result.filename}  (unchanged)")
        else:
            print(
                f"downloaded  {result.source_id}  {result.filename}  "
                f"sha256={result.sha256}"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download the documents listed in the sources list and "
        "record their URL, download date and SHA-256 in the lock file."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"sources list file (default: {DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help=f"download directory (default: {DEFAULT_OUT_DIR})",
    )
    parser.add_argument(
        "--lock",
        type=Path,
        default=DEFAULT_LOCK,
        help=f"provenance lock file (default: {DEFAULT_LOCK})",
    )
    parser.add_argument(
        "--source-id",
        action="append",
        metavar="ID",
        help="only download this source (repeatable)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-download even when the saved file still matches the lock hash",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"network timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )
    args = parser.parse_args(argv)

    try:
        sources = load_sources(args.config)
    except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.source_id:
        known = {source.id for source in sources}
        unknown = sorted(set(args.source_id) - known)
        if unknown:
            print(
                f"error: unknown source id(s) {', '.join(unknown)}; "
                f"known: {', '.join(sorted(known))}",
                file=sys.stderr,
            )
            return 2
        wanted = set(args.source_id)
        sources = [source for source in sources if source.id in wanted]

    results = run(
        sources,
        args.out_dir,
        args.lock,
        force=args.force,
        timeout=args.timeout,
    )
    _report(results)

    failures = [result for result in results if result.status == "failed"]
    if failures:
        print(
            f"error: {len(failures)} of {len(results)} source(s) failed",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
