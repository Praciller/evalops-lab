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

## RAGTruth full local classification judge

Phase 5B-L was owner-authorized as the existing Phase 5A-L V3
classification-first experiment and completed as
`ragtruth-local-llm-judge-full-v1`. This is a local benchmark result, not a
Gemini run and not a replacement for human labels.

Protocol: the official RAGTruth test population, revision
`c103204b9ce28d6bbad859304bf30de72b8ed8fe`, strict-groundedness policy,
2,675 `good` examples, and 25 exclusions (24 `incorrect_refusal`, 1
`truncated`). Dataset validation had zero issues and the final successful ID
set matched the target exactly.

The frozen local configuration was Ollama `qwen3:8b`, Ollama ID
`500a1f067a9f`, weights digest
`sha256-a3de86cd1c132c822487ededd47a324c50491393e6565cd14bafa40d0b8e686f`,
Ollama `0.33.2`, CPU inference, `think=false`, temperature `0`, native JSON
schema, and transport `ollama-qwen3-classification-v3`. The semantic prompt
hash is
`6ce1879a517fad6655a4a620d50c49ec24b9cee3c2a9d08c606d2f59c64bc9fc`; the
classification schema hash is
`89c75d0f8b9530262d80d1f5260e3f6efc30e0cfebfae98bef1b986b0d6b1d01`; and
the V3 transport hash is
`bdd91928b7ca23882caf7fe5ba5dbb7917ae89de5e8ee48bc0a31f6921a17da9`.

| Metric | Local Qwen3 | HHEM | Heuristic |
| --- | ---: | ---: | ---: |
| Accuracy | 0.7436 | 0.7566 | 0.6920 |
| Precision | 0.8408 | 0.7160 | 0.7767 |
| Recall | 0.3362 | 0.5133 | 0.1771 |
| F1 | 0.4803 | 0.5979 | 0.2884 |
| Balanced accuracy | 0.6508 | 0.7012 | 0.5747 |
| Specificity | 0.9654 | 0.8891 | 0.9723 |
| FPR | 0.0346 | 0.1109 | 0.0277 |
| FNR | 0.6638 | 0.4867 | 0.8229 |

Local confusion matrix: TP `317`, TN `1672`, FP `60`, FN `626`.

Task slices (local F1 / recall / FPR): Data2txt `0.4825 / 0.3212 /
0.0187` (n=900), QA `0.5664 / 0.5063 / 0.0629` (n=875), and Summary
`0.3802 / 0.2451 / 0.0129` (n=900). Source-model F1 / recall were:
`gpt-3.5-turbo-0613` `0.0741 / 0.0435`, `gpt-4-0613` `0.0426 / 0.0238`,
`llama-2-13b-chat` `0.6231 / 0.4831`, `llama-2-70b-chat` `0.4557 /
0.3158`, `llama-2-7b-chat` `0.4969 / 0.3540`, and `mistral-7B-instruct`
`0.4720 / 0.3187`.

Length slices used deterministic rank quartiles sorted by length and example
ID. Response-character F1 / recall by quartile were Q1 `0.3902 / 0.2857`,
Q2 `0.4669 / 0.3209`, Q3 `0.4515 / 0.3069`, and Q4 `0.5421 / 0.3871`.
Source-context-character F1 / recall were Q1 `0.5043 / 0.4069`, Q2
`0.5254 / 0.3826`, Q3 `0.4884 / 0.3345`, and Q4 `0.4144 / 0.2641`.

Paired exact two-sided McNemar tests on the same 2,675 IDs gave:

| Comparison | Comparator correct / local wrong | Local correct / comparator wrong | p-value |
| --- | ---: | ---: | ---: |
| Local vs heuristic | 146 | 284 | `2.6749e-11` |
| Local vs HHEM | 333 | 298 | `0.1758` |

The local judge therefore improves paired correctness over the heuristic, but
does not show a significant paired difference from HHEM at this sample and
protocol. HHEM remains stronger on recall, F1, and balanced accuracy, while
the local judge has fewer false positives and higher precision/specificity.

The three-evaluator analysis used human labels without majority voting. The
reported correctness-category counts were ALL_CORRECT `1537`, ALL_WRONG
`303`, HEURISTIC_ONLY_CORRECT `50`, HHEM_ONLY_CORRECT `237`,
LOCAL_LLM_ONLY_CORRECT `130`, HHEM_AND_HEURISTIC_CORRECT `1633`,
LOCAL_LLM_AND_HEURISTIC_CORRECT `1705`, and LOCAL_LLM_AND_HHEM_CORRECT
`1691`; all evaluators had complete coverage.

Calibration was weak: Brier score `0.3336` and 10-bin ECE `0.3331` for both
the hallucination probability and decision-confidence views. Error analysis
found 686 errors (626 false negatives and 60 false positives); mean
confidence on errors was `0.9233`. Errors by task were Data2txt `399`, QA
`124`, and Summary `163`.

The deterministic IID bootstrap used 10,000 replicates with seed `20260830`.
Local 95% intervals were F1 `[0.4462, 0.5127]`, balanced accuracy
`[0.6350, 0.6664]`, recall `[0.3058, 0.3663]`, and FPR `[0.0265, 0.0436]`.
Local-minus-HHEM intervals were F1 `[-0.1580, -0.0773]`, balanced accuracy
`[-0.0725, -0.0284]`, recall `[-0.2179, -0.1366]`, and FPR
`[-0.0923, -0.0599]`.

The run used 2,675 local requests, zero hosted requests, and zero quota or
rate-limit events. Mean latency was `8,799.3 ms`, p50 `7,254.2 ms`, p95
`20,071.6 ms`, and generation throughput was `8.11 tokens/s`; reported
hosted inference cost was `$0` and electricity cost was not estimated. The
V3 12-example consistency reference remains PASS at 94.44% agreement and
91.67% unanimity, with the primary prediction unchanged. Relative to the
balanced 120-example V3 pilot, the full-population delta is descriptive only:
full-minus-pilot F1 `-0.1174`, balanced accuracy `-0.0576`, recall `-0.0972`,
and accuracy `+0.0352`.

Conclusion: this is a reproducible, zero-cost local benchmark baseline and a
useful comparator against HHEM and the heuristic. It does not authorize a
new Gemini run, hosted inference, a model change, or another experiment.

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

The local state, preflight, and result artifacts are intentionally ignored
under `reports/*.json`. The completed full-run report records source commit
`42e7822d1cb1bb115276351dffc599fc3d75a62a`, the exact model/transport
provenance above, and the final ID set. Historical heuristic and HHEM reports
retain their original provenance; new runs should capture their source commit
automatically.
