# Dataset policy

This directory contains manifests and small, synthetic fixtures only. Full MIRACL Thai and RAGTruth releases are intentionally not committed. The manifests record verified source revisions, upstream statistics, formats, and local commands; no complete external dataset is checked into Git.

The `thai-rag-eval-200` fixture is a schema and pipeline seed, not a 200-case benchmark. New cases must be manually curated, reviewed, and validated before being added. Ground truth must never be edited to improve a system score.

External snapshots belong under the ignored `datasets/external/` path. Preparation scripts are explicit about their source and destination, compute SHA-256, and refuse to overwrite an existing destination with different content.

## RAGTruth storage

`evalops dataset prepare ragtruth` downloads the pinned official
`response.jsonl` and `source_info.jsonl` files into the explicitly named
ignored output directory and writes a preparation manifest. Use
`evalops dataset prepare ragtruth --mini` for the offline synthetic fixture;
its results must never be presented as official RAGTruth results. See
[`docs/ragtruth-benchmark.md`](../docs/ragtruth-benchmark.md) for the human
annotation policy, quality filter, evaluator boundary, and leakage notes.

## MIRACL Thai storage

`evalops dataset prepare miracl --language th --split dev` downloads pinned
topics/qrels and corpus shards into the explicitly named ignored output path.
Use `--topics-qrels-only` when validating the small topic/qrels artifacts without
downloading the approximately 542k-passage corpus. Use
`evalops dataset prepare miracl --language th --split dev --mini` for the
offline fixture; it is synthetic and must never be reported as an official
MIRACL result.
