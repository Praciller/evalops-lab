# MIRACL Thai benchmark

MIRACL Thai is the first real external retrieval benchmark in EvalOps Lab. It
was selected because it provides native-language passage retrieval queries,
TREC-style qrels, and a large Thai Wikipedia passage corpus suitable for
testing dataset provenance, retrieval execution, and regression analysis.

The official MIRACL sources describe the Thai corpus as 542,166 passages from
128,179 articles. The Thai train split has 2,972 queries and 21,293 judgments;
the dev split has 733 queries and 7,573 judgments. EvalOps records these
figures in `datasets/manifests/miracl-th.json` together with the verified
source revisions used by the preparation defaults.

## Source and normalization

Topics are upstream TSV records of `qid<TAB>query`. Qrels are standard TREC
records of `qid Q0 docid relevance`. Corpus shards are gzip-compressed JSONL
records with `docid`, `title`, and `text`. The adapter maps these into
`RetrievalQuery`, `RelevanceJudgment`-compatible mappings, and
`CorpusDocument`; the BM25 retriever never receives MIRACL-specific records.

The full corpus is streamed from gzip files during validation and then loaded
once for the intentionally simple in-memory baseline. Run artifacts contain
query-level rankings and scores, not duplicate corpus text.

The upstream Thai corpus listing shows two shards totaling about 110 MB
compressed. That download size is not the same as the expanded Python BM25
index size; the current environment was not used for the full in-memory run
because its available memory was not established safely. The real topics/qrels
path is verified, while full corpus preparation and execution remain explicit
owner-run steps.

## Preparation

For local development without network access:

```bash
evalops dataset prepare miracl --language th --split dev --mini
```

For real topic/qrels preparation without downloading corpus shards:

```bash
evalops dataset prepare miracl \
  --language th \
  --split dev \
  --topics-qrels-only
```

For a full local preparation, use the explicit ignored output path:

```bash
evalops dataset prepare miracl \
  --language th \
  --split dev \
  --output-dir datasets/external/miracl/th/dev
```

Preparation is idempotent for unchanged local artifacts, uses pinned direct
file URLs rather than arbitrary remote Python dataset code, records SHA-256
checksums, and refuses ambiguous overwrites.

## Mini versus full dev

`datasets/fixtures/miracl-th-mini/` is a synthetic MIRACL-shaped fixture. It is
committed for offline CI and contains five queries, eleven qrel rows, and six
documents. Its results are integration-test evidence only and are **not
MIRACL benchmark results**.

The real dev run is opt-in and is never part of normal CI:

```bash
evalops benchmark miracl \
  --language th \
  --split dev \
  --retriever bm25 \
  --k 10 \
  --data-dir datasets/external/miracl/th/dev \
  --output reports/miracl-th-dev-bm25.json \
  --trec-run reports/miracl-th-dev-bm25.trec
```

The repository does not claim a full-dev score until that command completes
against the prepared real corpus. It also does not call the local score an
official leaderboard score; the benchmark protocol and evaluator compatibility
would need to be independently verified first.

## Baseline and Thai tokenization

The initial baseline is a local BM25 implementation with deterministic
document-ID tie-breaking. It uses Unicode normalization, Thai character
bigrams/trigrams, and Latin/number runs. This avoids silently assuming that
whitespace separates Thai words while avoiding a large NLP dependency stack.
The exact strategy and BM25 parameters are stored in every benchmark artifact.

## Metrics and failure analysis

The benchmark reuses EvalOps' existing deterministic metric evaluator. It
reports Precision@K, Recall@K, Hit Rate@K, MRR, and nDCG for each configured K
(1, 5, and 10 when the run top-k supports them). Mapping-based qrels preserve
positive graded labels for nDCG; sequence-based callers retain the Phase 1
binary behavior. Per-query results include retrieved IDs, scores, relevant IDs,
relevance labels, metrics, and `RETRIEVAL_MISS`/`PASS` classifications.

Saved JSON artifacts can be compared with an explicit policy:

```bash
evalops regression compare \
  --baseline reports/miracl-th-mini-baseline.json \
  --candidate reports/miracl-th-mini-candidate.json \
  --policy datasets/fixtures/miracl-mini-baseline-policy.json
```

The fixture policy is a demonstration of the comparison interface, not a
production-quality threshold derived from five synthetic queries.
