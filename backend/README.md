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
## Retrieval

```bash
python backend/scripts/retrieve.py --source-id ref-01 --query "..." --mode hybrid
python eval/run_retrieval_eval.py --source-id ref-01 --mode hybrid
```

`--mode` is `dense` (cosine over the stored vectors), `lexical` (BM25 over the
chunk texts, same NFKC + tatweel cleaning, Arabic stopwords ignored) or `hybrid`
(the two rankings fused with Reciprocal Rank Fusion, k=60). `hybrid` is the default
and what `answer.py` retrieves with; `lexical` never calls the embedding provider,
so it works without a key. The eval prints hit@1, hit@3 and hit@5 for the mode it ran.

## Answering

```bash
python backend/scripts/answer.py --source-id ref-01 --question "كم المعدل المطلوب عشان أتخرج؟" --json
```

Retrieves the top 5 chunks with `retrieve.py` and puts **only** those articles —
article number, heading, URL and text — in the prompt, asking the model pinned in
[`config/chat.toml`](config/chat.toml) for an Arabic answer that cites the article
numbers. When the retrieved articles do not support an answer, the fixed fallback
text is returned with no citations. The key is `OPENAI_API_KEY` from `.env`.

## HTTP API

```bash
uvicorn app.main:app --app-dir backend
```

`POST /chat` per [`../docs/api-contract.md`](../docs/api-contract.md): `{message,
session_id}` in, `{answer, citations: [{title, article, url}]}` out. A message that is
empty (or blank) or over 1000 characters is a 422; a model or index failure is a 503,
so "the service is down" is never reported as "the regulation does not say". `article`
is `null` for the annex chunk, which has no article number.
