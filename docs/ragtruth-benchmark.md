# RAGTruth hallucination benchmark

Phase 3 integrates the official RAGTruth response/source JSONL files into the
generic `HallucinationExample` model. The official repository is pinned to
[`c103204b9ce28d6bbad859304bf30de72b8ed8fe`](https://github.com/ParticleMedia/RAGTruth/tree/c103204b9ce28d6bbad859304bf30de72b8ed8fe)
and is published under MIT licensing. The pinned release reports 17,790
responses, 7,664 responses with hallucination annotations, 14,289 spans, and
2,965 source instances.

## Preparation

Real files are downloaded only when explicitly requested and are stored below
the ignored `datasets/external/ragtruth/` directory:

```bash
python -m evalops dataset prepare ragtruth \
  --output-dir datasets/external/ragtruth
```

Preparation uses the pinned raw files, writes SHA-256 values and counts to
`preparation-manifest.json`, validates response/source references, and refuses
to overwrite an existing destination with different content. Normal CI does
not download the official dataset.

The offline fixture is deliberately synthetic:

```bash
python -m evalops dataset prepare ragtruth --mini
```

It is labeled **SYNTHETIC TEST FIXTURE — NOT OFFICIAL RAGTRUTH RESULTS** and
contains QA, Summary, Data2txt, multiple spans, `implicit_true`, `due_to_null`,
non-good quality values, and an intentional offset anomaly.

## Human labels and evaluator predictions

The adapter preserves the response, source/source-info, prompt, model,
temperature, quality, split, raw records, and each human span. It validates
`response[start:end] == label.text` and reports mismatches without rewriting
the upstream text or offsets.

Human labels are computed separately from evaluator predictions. The positive
response class is `HALLUCINATED`; an empty annotation list is `GROUNDED`.

Two explicit policies are supported:

- `strict-groundedness` counts every annotated span, including
  `implicit_true`. This matches the strict RAG definition: a fact may be true
  but still unsupported by the supplied evidence.
- `factual-correctness` excludes only `implicit_true` spans from the positive
  response label. `due_to_null` remains visible and is counted as a failure of
  the supplied evidence because a null value is not a known fact.

The default quality filter is `quality == good`. `incorrect_refusal` and
`truncated` records are excluded and reported with counts and IDs. They are
not silently treated as grounded or hallucinated.

## Evaluator and metrics

The implemented evaluator is the local deterministic `heuristic-baseline`:
it compares normalized response tokens with evidence tokens using a fixed
0.4 support threshold. The threshold is recorded as
`fixed-v1-not-tuned-on-test`. It is a smoke-test baseline, not a factuality
judge, and it does not use an LLM or paid API.

```bash
python -m evalops hallucination evaluate \
  --dataset ragtruth \
  --data-dir datasets/external/ragtruth \
  --split test \
  --evaluator heuristic-baseline \
  --annotation-policy strict-groundedness \
  --run-id ragtruth-test-heuristic-v1 \
  --output reports/ragtruth-test-heuristic-v1.json
```

Artifacts include the run revision, annotation policy, quality filter,
evaluator name/version/config, total/included/excluded counts, confusion
matrix, precision/recall/F1/accuracy/specificity/FPR/FNR, task/model slices,
false-positive and false-negative IDs, validation-issue counts, and compact
per-example evidence. Confusion-matrix zero denominators resolve to `0.0` and
are not hidden.

Response-level metrics are the primary gate. Span primitives separately
provide exact character match, character overlap, and character IoU; an
evaluator must emit spans before span scores are reported. Exact and overlap
matching must not be conflated.

## Leakage and limitations

The baseline does not tune on the official test split. No train-derived model
or threshold-selection stage is claimed. Sibling responses share source
instances, so future training/validation work must split by `source_id` rather
than randomly splitting responses. Human labels are not an automatic judge,
and the baseline's false positives/negatives are evaluator errors, not
changes to ground truth.

Phase 4 adds the validated optional HHEM-2.1-Open detector and same-population
paired comparison against this baseline. See
[`docs/hhem-evaluator.md`](hhem-evaluator.md) for the exact model provenance,
security review, context construction, official test result, and limitations.
LLM-as-a-Judge validation remains separate from RAGTruth ground truth and is
not implemented here.
