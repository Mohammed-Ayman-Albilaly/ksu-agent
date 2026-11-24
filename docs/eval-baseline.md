# Eval baseline

Measured on the golden question sets in `eval/`. The question set did not change, so
a movement here is the model's or the embedder's, not the corpus's.

## Retrieval — `eval/run_retrieval_eval.py`

10 questions, k=5, mode=hybrid, index `ref-01` (75 chunks).

| Metric | Hybrid + `text-embedding-3-small` (1536) | Hybrid + `local-embedding-model` (1024) |
| :--- | :--- | :--- |
| hit@1 | 0.60 | **0.70** |
| hit@3 | 0.80 | 0.80 |
| hit@5 | 0.80 | 0.80 |
| missed at k=5 | q3, q5 | q3, q5 |

The embedder moved hit@1 by +0.10 and held hit@3 and hit@5. The two questions
that miss at k=5 are the same two: their wording is dialect, and neither embedder
finds the article the regulation words differently. That is a corpus and query-set
limit, not an embedder one.

## Answers — `eval/run_answer_eval.py`

11 questions, k=5, `DeepSeek-V4.1-Flash` on the gateway.

| Metric | Value |
| :--- | :--- |
| citation_presence | 8/11 (0.73) |
| expected_article_cited | 8/10 (0.80) |
| latency median | 1587 ms |
| latency p95 | 3281 ms |
| estimated cost | $0.018612 (11 calls, $0.3/1.2 per 1M) |

The three answers without a citation are q3, q5 and q11: the first two are the
retrieval misses above, and q11 is the set's unanswerable question. All three
returned the fallback answer, which is what the contract requires, and the unanswerable
question returned no citation on every run.

This is the first recorded answer baseline. There is no earlier number to compare
against, because the previous index was built with a different embedder and could not
be re-measured after the swap.

## What this settles

The Arabic corpus was never the reason retrieval was weak at hit@1. A stronger
embedder moved it from 0.60 to 0.70 with the corpus untouched, so replacing
Arabic with English would have spent a slice on the wrong suspect. The English corpus
stays out of scope until a query-set or corpus problem is the measured cause.
