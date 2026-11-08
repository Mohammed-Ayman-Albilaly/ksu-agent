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

## Parsing

```bash
python -m pip install -r backend/requirements.txt
python backend/scripts/parse_source.py --source-id ref-01
```

Writes `data/processed/<id>.txt` (each page preceded by a `[[page N]]` marker)
and `<id>.meta.json` (source id, lock SHA-256, page count, char count). Text is
NFKC-normalised and stripped of tatweel (U+0640). Both files are git-ignored.
The PDF is hashed again before parsing; a mismatch with the lock file stops the
run instead of producing a meta file that lies.

Tests: `python -m pytest backend/tests` (no network needed).
