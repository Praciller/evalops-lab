# MIRACL Thai mini fixture

**SYNTHETIC TEST FIXTURE — NOT MIRACL BENCHMARK RESULTS.**

This fixture mirrors the upstream MIRACL shapes without redistributing
upstream content. It is intentionally tiny and exists only for offline
integration tests, CLI verification, and reproducibility checks.

- `topics.tsv`: `query_id<TAB>query`
- `qrels.tsv`: `query_id Q0 document_id relevance`
- `corpus.jsonl`: upstream-shaped `docid`, `title`, and `text` records
