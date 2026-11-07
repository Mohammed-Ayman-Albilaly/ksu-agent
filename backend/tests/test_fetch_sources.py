"""Tests for scripts/fetch_sources.py.

No network access: a local HTTP server serves a fixture PDF so downloads,
hashing and the lock file are exercised deterministically.
"""

import hashlib
import http.server
import json
import socketserver
import threading
from functools import partial

import pytest

import fetch_sources

PAYLOAD = b"%PDF-1.4\n% fixture regulation payload\n" + b"x" * 4096


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # keep pytest output clean
        pass


@pytest.fixture
def server(tmp_path):
    docroot = tmp_path / "www"
    docroot.mkdir()
    (docroot / "regulation.pdf").write_bytes(PAYLOAD)

    handler = partial(_QuietHandler, directory=str(docroot))
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as httpd:
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{httpd.server_address[1]}/regulation.pdf"
        finally:
            httpd.shutdown()
            thread.join(timeout=5)


def _write_config(path, url, source_id="ref-01"):
    path.write_text(
        "[[source]]\n"
        f'id = "{source_id}"\n'
        'title = "Test regulation"\n'
        f'url = "{url}"\n'
        'filename = "regulation.pdf"\n',
        encoding="utf-8",
    )
    return path


def _lock(tmp_path):
    """The lock file path, kept outside the download directory."""
    return tmp_path / "config" / "sources.lock.json"


def _read_lock(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_load_sources_reads_config(tmp_path):
    config = _write_config(tmp_path / "sources.toml", "https://example.test/a.pdf")

    sources = fetch_sources.load_sources(config)

    assert [s.id for s in sources] == ["ref-01"]
    assert sources[0].url == "https://example.test/a.pdf"
    assert sources[0].filename == "regulation.pdf"


def test_load_sources_rejects_duplicate_ids(tmp_path):
    config = tmp_path / "sources.toml"
    _write_config(config, "https://example.test/a.pdf")
    with config.open("a", encoding="utf-8") as fh:
        fh.write(
            "\n[[source]]\n"
            'id = "ref-01"\n'
            'title = "Duplicate"\n'
            'url = "https://example.test/b.pdf"\n'
            'filename = "b.pdf"\n'
        )

    with pytest.raises(ValueError, match="duplicate"):
        fetch_sources.load_sources(config)


def test_load_sources_rejects_missing_field(tmp_path):
    config = tmp_path / "sources.toml"
    config.write_text(
        '[[source]]\nid = "ref-01"\nurl = "https://example.test/a.pdf"\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="filename"):
        fetch_sources.load_sources(config)


def test_run_downloads_file_and_writes_lock(tmp_path, server):
    config = _write_config(tmp_path / "sources.toml", server)
    out_dir = tmp_path / "data" / "raw"
    lock = _lock(tmp_path)

    results = fetch_sources.run(
        fetch_sources.load_sources(config), out_dir, lock
    )

    assert [(r.source_id, r.status) for r in results] == [("ref-01", "downloaded")]

    saved = out_dir / "regulation.pdf"
    assert saved.read_bytes() == PAYLOAD
    assert not list(out_dir.glob("*.part")), "temp file must not survive a successful run"
    assert not (out_dir / "manifest.json").exists(), "lock file belongs outside the data dir"

    entry = _read_lock(lock)["documents"]["ref-01"]
    assert entry["url"] == server
    assert entry["title"] == "Test regulation"
    assert entry["filename"] == "regulation.pdf"
    assert entry["sha256"] == hashlib.sha256(PAYLOAD).hexdigest()
    assert entry["bytes"] == len(PAYLOAD)
    assert entry["downloaded_at"].endswith("Z")
    assert results[0].sha256 == entry["sha256"]


def test_run_skips_when_hash_is_unchanged(tmp_path, server):
    config = _write_config(tmp_path / "sources.toml", server)
    out_dir = tmp_path / "data" / "raw"
    lock = _lock(tmp_path)
    sources = fetch_sources.load_sources(config)

    first = fetch_sources.run(sources, out_dir, lock)
    lock_after_first = _read_lock(lock)
    second = fetch_sources.run(sources, out_dir, lock)

    assert [r.status for r in first] == ["downloaded"]
    assert [r.status for r in second] == ["skipped"]
    assert _read_lock(lock) == lock_after_first


def test_run_force_redownloads(tmp_path, server):
    config = _write_config(tmp_path / "sources.toml", server)
    out_dir = tmp_path / "data" / "raw"
    lock = _lock(tmp_path)
    sources = fetch_sources.load_sources(config)

    fetch_sources.run(sources, out_dir, lock)
    results = fetch_sources.run(sources, out_dir, lock, force=True)

    assert [r.status for r in results] == ["downloaded"]


def test_run_redownloads_when_saved_file_is_missing(tmp_path, server):
    config = _write_config(tmp_path / "sources.toml", server)
    out_dir = tmp_path / "data" / "raw"
    lock = _lock(tmp_path)
    sources = fetch_sources.load_sources(config)

    fetch_sources.run(sources, out_dir, lock)
    (out_dir / "regulation.pdf").unlink()
    results = fetch_sources.run(sources, out_dir, lock)

    assert [r.status for r in results] == ["downloaded"]


def test_run_reports_failure_without_writing_lock_entry(tmp_path):
    config = _write_config(tmp_path / "sources.toml", "http://127.0.0.1:1/missing.pdf")
    out_dir = tmp_path / "data" / "raw"
    lock = _lock(tmp_path)

    results = fetch_sources.run(
        fetch_sources.load_sources(config), out_dir, lock, timeout=2
    )

    assert [(r.source_id, r.status) for r in results] == [("ref-01", "failed")]
    assert results[0].error
    assert not (out_dir / "regulation.pdf").exists()
    assert _read_lock(lock)["documents"] == {}


def test_main_returns_nonzero_when_a_source_fails(tmp_path, capsys):
    config = _write_config(tmp_path / "sources.toml", "http://127.0.0.1:1/missing.pdf")

    exit_code = fetch_sources.main(
        [
            "--config",
            str(config),
            "--out-dir",
            str(tmp_path / "data" / "raw"),
            "--lock",
            str(_lock(tmp_path)),
            "--timeout",
            "2",
        ]
    )

    assert exit_code == 1
    assert "failed" in capsys.readouterr().out


def test_main_returns_zero_and_filters_by_source_id(tmp_path, server):
    config = tmp_path / "sources.toml"
    _write_config(config, "http://127.0.0.1:1/other.pdf", source_id="ref-02")
    with config.open("a", encoding="utf-8") as fh:
        fh.write(
            "\n[[source]]\n"
            'id = "ref-01"\n'
            'title = "Test regulation"\n'
            f'url = "{server}"\n'
            'filename = "regulation.pdf"\n'
        )
    out_dir = tmp_path / "data" / "raw"
    lock = _lock(tmp_path)

    exit_code = fetch_sources.main(
        [
            "--config",
            str(config),
            "--out-dir",
            str(out_dir),
            "--lock",
            str(lock),
            "--source-id",
            "ref-01",
        ]
    )

    assert exit_code == 0
    assert set(_read_lock(lock)["documents"]) == {"ref-01"}


def test_main_rejects_unknown_source_id(tmp_path):
    config = _write_config(tmp_path / "sources.toml", "https://example.test/a.pdf")

    exit_code = fetch_sources.main(
        [
            "--config",
            str(config),
            "--out-dir",
            str(tmp_path / "out"),
            "--lock",
            str(_lock(tmp_path)),
            "--source-id",
            "nope",
        ]
    )

    assert exit_code == 2
