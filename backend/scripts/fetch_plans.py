#!/usr/bin/env python3
"""Download the study plan sources listed in backend/config/plans.toml.

Each source is saved under the raw directory (default: data/raw/plans, which is
git-ignored) as ``<id>.<ext>`` — ``.pdf`` for a PDF, ``.json`` for a JSON:API
node — next to a ``<id>.meta.json`` recording the URL, the download date and the
SHA-256, the same provenance ``fetch_sources.py`` keeps for the regulation.

URLs are never hard-coded here: they come from the plans list, so a new or
replaced plan is a config change, not a code change. Re-running when the saved
file still matches the hash in its meta file is a no-op; ``--force`` re-downloads.

Usage:
    python backend/scripts/fetch_plans.py
    python backend/scripts/fetch_plans.py --plan swe --force
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
DEFAULT_CONFIG = REPO_ROOT / "backend" / "config" / "plans.toml"
DEFAULT_OUT_DIR = REPO_ROOT / "data" / "raw" / "plans"
CHUNK_SIZE = 64 * 1024
DEFAULT_TIMEOUT = 60
USER_AGENT = "ksu-agent-ingest/1.0"
REQUIRED_FIELDS = ("id", "title", "program_url", "source_url", "form", "language")

# The form decides the file extension: a PDF is parsed with pymupdf, a JSON:API
# node is JSON whose body.value holds the HTML tables.
FORM_EXTENSIONS = {"pdf": ".pdf", "html_table": ".json"}
LANGUAGES = ("en", "ar")


@dataclass(frozen=True)
class PlanSource:
    """One study plan source, as declared in the plans list."""

    id: str
    title: str
    program_url: str
    source_url: str
    form: str
    language: str
    stale_risk: bool = False

    @property
    def extension(self) -> str:
        return FORM_EXTENSIONS[self.form]

    @property
    def filename(self) -> str:
        return f"{self.id}{self.extension}"

    @property
    def meta_filename(self) -> str:
        return f"{self.id}.meta.json"


@dataclass
class Result:
    """Outcome of one plan: status is 'downloaded', 'skipped' or 'failed'."""

    plan_id: str
    filename: str
    status: str
    sha256: str | None = None
    error: str | None = None


def _check_http_url(config_path: Path, plan_id: str, field: str, value: str) -> str:
    value = str(value).strip()
    if not value.lower().startswith(("http://", "https://")):
        raise ValueError(
            f"{config_path}: plan {plan_id!r} {field} must be http(s), got {value!r}"
        )
    return value


def load_plans(config_path: Path) -> list[PlanSource]:
    """Read and validate the plans list."""
    with Path(config_path).open("rb") as fh:
        data = tomllib.load(fh)

    raw_plans = data.get("plan", [])
    if not isinstance(raw_plans, list) or not raw_plans:
        raise ValueError(f"{config_path}: no [[plan]] entries found")

    plans: list[PlanSource] = []
    seen: set[str] = set()
    for index, entry in enumerate(raw_plans, start=1):
        missing = [field for field in REQUIRED_FIELDS if not entry.get(field)]
        if missing:
            raise ValueError(
                f"{config_path}: [[plan]] #{index} is missing {', '.join(missing)}"
            )

        plan_id = str(entry["id"]).strip()
        if plan_id in seen:
            raise ValueError(f"{config_path}: duplicate plan id {plan_id!r}")
        if Path(plan_id).name != plan_id or "." in plan_id:
            raise ValueError(
                f"{config_path}: plan id {plan_id!r} must be a bare name without "
                f"a dot, because it names the downloaded file"
            )
        seen.add(plan_id)

        form = str(entry["form"]).strip()
        if form not in FORM_EXTENSIONS:
            raise ValueError(
                f"{config_path}: plan {plan_id!r} form must be one of "
                f"{', '.join(sorted(FORM_EXTENSIONS))}, got {form!r}"
            )

        language = str(entry["language"]).strip()
        if language not in LANGUAGES:
            raise ValueError(
                f"{config_path}: plan {plan_id!r} language must be one of "
                f"{', '.join(LANGUAGES)}, got {language!r}"
            )

        plans.append(
            PlanSource(
                id=plan_id,
                title=str(entry["title"]).strip(),
                program_url=_check_http_url(
                    config_path, plan_id, "program_url", entry["program_url"]
                ),
                source_url=_check_http_url(
                    config_path, plan_id, "source_url", entry["source_url"]
                ),
                form=form,
                language=language,
                stale_risk=bool(entry.get("stale_risk", False)),
            )
        )

    return plans


def sha256_file(path: Path) -> str:
    """SHA-256 of an existing file, read in chunks."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_meta(path: Path) -> dict | None:
    """The meta file for one plan, or None when it is absent or unreadable."""
    path = Path(path)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_meta(path: Path, meta: dict) -> None:
    """Write a meta file atomically, with a stable key order for clean diffs."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.part")
    tmp_path.write_text(
        json.dumps(meta, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp_path, path)


def _already_downloaded(plan: PlanSource, out_dir: Path) -> dict | None:
    """The existing meta file when the saved file still matches its hash."""
    meta = read_meta(out_dir / plan.meta_filename)
    if not meta or meta.get("source_url") != plan.source_url:
        return None

    path = out_dir / plan.filename
    if not path.exists() or meta.get("sha256") != sha256_file(path):
        return None

    return meta


def download(
    plan: PlanSource, out_dir: Path, timeout: float = DEFAULT_TIMEOUT
) -> dict:
    """Stream the source to disk and return its meta entry.

    The body is written to a ``.part`` file and only moved into place once the
    full response has been read, so a failed download never leaves a truncated
    file behind.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    request = Request(plan.source_url, headers={"User-Agent": USER_AGENT})
    digest = hashlib.sha256()
    size = 0
    content_type = ""

    handle = tempfile.NamedTemporaryFile(
        dir=out_dir,
        prefix=f"{plan.filename}.",
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
        os.replace(tmp_path, out_dir / plan.filename)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise

    return {
        "plan_id": plan.id,
        "title": plan.title,
        "program_url": plan.program_url,
        "source_url": plan.source_url,
        "form": plan.form,
        "language": plan.language,
        "stale_risk": plan.stale_risk,
        "filename": plan.filename,
        "downloaded_at": _utc_now(),
        "sha256": digest.hexdigest(),
        "bytes": size,
        "content_type": content_type,
    }


def run(
    plans: list[PlanSource],
    out_dir: Path,
    *,
    force: bool = False,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[Result]:
    """Download every plan, writing a meta file as each one lands."""
    out_dir = Path(out_dir)
    results: list[Result] = []

    for plan in plans:
        existing = None if force else _already_downloaded(plan, out_dir)
        if existing is not None:
            results.append(
                Result(
                    plan_id=plan.id,
                    filename=plan.filename,
                    status="skipped",
                    sha256=existing["sha256"],
                )
            )
            continue

        try:
            meta = download(plan, out_dir, timeout=timeout)
        except (HTTPError, URLError, OSError, ValueError) as exc:
            results.append(
                Result(
                    plan_id=plan.id,
                    filename=plan.filename,
                    status="failed",
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
            continue

        write_meta(out_dir / plan.meta_filename, meta)
        results.append(
            Result(
                plan_id=plan.id,
                filename=plan.filename,
                status="downloaded",
                sha256=meta["sha256"],
            )
        )

    return results


def _report(results: list[Result]) -> None:
    for result in results:
        if result.status == "failed":
            print(f"failed      {result.plan_id}  {result.error}")
        elif result.status == "skipped":
            print(f"skipped     {result.plan_id}  {result.filename}  (unchanged)")
        else:
            print(
                f"downloaded  {result.plan_id}  {result.filename}  "
                f"sha256={result.sha256}"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download the study plan sources listed in the plans list and "
        "record their URL, download date and SHA-256 in a meta file per plan."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"plans list file (default: {DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help=f"download directory (default: {DEFAULT_OUT_DIR})",
    )
    parser.add_argument(
        "--plan",
        action="append",
        metavar="ID",
        help="only download this plan (repeatable)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-download even when the saved file still matches its meta hash",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"network timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )
    args = parser.parse_args(argv)

    try:
        plans = load_plans(args.config)
    except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.plan:
        known = {plan.id for plan in plans}
        unknown = sorted(set(args.plan) - known)
        if unknown:
            print(
                f"error: unknown plan id(s) {', '.join(unknown)}; "
                f"known: {', '.join(sorted(known))}",
                file=sys.stderr,
            )
            return 2
        wanted = set(args.plan)
        plans = [plan for plan in plans if plan.id in wanted]

    results = run(plans, args.out_dir, force=args.force, timeout=args.timeout)
    _report(results)

    failures = [result for result in results if result.status == "failed"]
    if failures:
        print(
            f"error: {len(failures)} of {len(results)} plan(s) failed",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
