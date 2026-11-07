# Backend
FastAPI server, RAG pipeline and ingestion scripts.

## Source documents

Documents are downloaded, never committed. The URL of each one lives in
[`config/sources.toml`](config/sources.toml); the download date and SHA-256 of
each downloaded file live in [`config/sources.lock.json`](config/sources.lock.json),
which is tracked so the corpus can be verified.

```bash
python backend/scripts/fetch_sources.py              # download everything listed
python backend/scripts/fetch_sources.py --source-id ref-01
python backend/scripts/fetch_sources.py --force      # re-download regardless
```

Files land in `data/raw/` (git-ignored). A source whose saved file still matches
the hash in the lock file is skipped, so re-running is cheap.

Tests: `python -m pytest backend/tests` (no network needed).
