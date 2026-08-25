# Verified benchmark results

This page is the canonical summary of measured EvalOps Lab results. It keeps
real external-benchmark runs separate from synthetic fixture checks and from
benchmarks that have not been run.

## MIRACL Thai

Full real MIRACL Thai dev BM25 benchmark: **NOT RUN**.

The current BM25 implementation expands the corpus into an in-memory index;
its full resource requirements were not safely established. This limitation is
intentional and remains documented in [`miracl-benchmark.md`](miracl-benchmark.md).

The committed mini benchmark is a **synthetic fixture only**. Its k=5 results
are Precision `0.24`, Recall `1.0`, Hit Rate `1.0`, MRR `1.0`, and nDCG `1.0`.
These are integration-test values, not MIRACL performance claims.

## RAGTruth heuristic baseline

Protocol: RAGTruth revision
`c103204b9ce28d6bbad859304bf30de72b8ed8fe`, test split, annotation policy
`strict-groundedness`, quality `good`, and fixed heuristic threshold `0.4`.

Population: 2,675 included responses; 25 excluded responses (24
`incorrect_refusal`, 1 `truncated`).

| Metric | Result |
| --- | ---: |
| Accuracy | 0.6920 |
| Precision | 0.7767 |
| Recall | 0.1771 |
| F1 | 0.2884 |
| Specificity | 0.9723 |

Confusion matrix: TP `167`, TN `1684`, FP `48`, FN `776`.

Task F1: Data2txt `0.3937`, QA `0.1675`, Summary `0.0098`.

## RAGTruth HHEM-2.1-Open

Protocol: the same population and annotation policy, model revision
`8e4a2e6e96c708cc76c2344f7e4757df2515292c`, tokenizer revision
`7bcac572ce56db69c1ea7c8af255c5d7c9672fc2`, context strategy
`ragtruth-source-context-v1`, CPU, batch size `16`, threshold `0.5`, and
threshold source `fixed-probability-boundary-v1`.

Population: 2,675 included responses; 25 excluded responses. Included IDs
are identical to the heuristic run.

| Metric | Result |
| --- | ---: |
| Accuracy | 0.7566 |
| Precision | 0.7160 |
| Recall | 0.5133 |
| F1 | 0.5979 |
| Balanced accuracy | 0.7012 |

Confusion matrix: TP `484`, TN `1540`, FP `192`, FN `459`.

Task F1: Data2txt `0.6391`, QA `0.6000`, Summary `0.4483`.

The pinned model manifest and security boundary are documented in
[`hhem-evaluator.md`](hhem-evaluator.md). HHEM weights are not committed.

## Paired comparison

The comparison uses the same included example IDs and preserved human labels.

- HHEM-only correct: `391`
- Heuristic-only correct: `218`
- Heuristic false negatives fixed by HHEM: `370`
- Heuristic false positives fixed by HHEM: `21`
- Exact two-sided McNemar p-value: `2.27e-12`

Under this exact EvalOps protocol, HHEM materially improves recall and F1
while introducing substantially more false positives. Statistical significance
describes a paired difference; it does not establish universal superiority or
a production-ready threshold.

## Artifact and provenance note

The source artifacts are intentionally ignored under `reports/*.json`. They
were generated before the repository's first commit and therefore preserve
`git_commit: null`. The finalization commit is the repository baseline for
future runs; new runs should capture that commit SHA automatically.
