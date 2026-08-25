# HHEM-2.1-Open evaluator

Phase 4 adds an optional adapter for Vectara's HHEM-2.1-Open model. The
default test and heuristic benchmark paths remain model-free and offline.
Upstream provenance is the [HHEM model card](https://huggingface.co/vectara/hallucination_evaluation_model).

## Provenance and security boundary

The repository manifest is
[`models/manifests/hhem-2.1-open.json`](../models/manifests/hhem-2.1-open.json).
The adapter accepts only:

- `vectara/hallucination_evaluation_model` at revision
  `8e4a2e6e96c708cc76c2344f7e4757df2515292c`;
- `google/flan-t5-base` at tokenizer revision
  `7bcac572ce56db69c1ea7c8af255c5d7c9672fc2`;
- the reviewed `configuration_hhem_v2.py`, `modeling_hhem_v2.py`, and
  `config.json` hashes recorded in the manifest.

The upstream model uses Transformers custom code. The local loader validates
the manifest and hashes before importing Transformers, passes the exact
revision with `trust_remote_code=True`, prefers `model.safetensors`, and
does not install packages or execute arbitrary shell commands. The reviewed
custom code uses Transformers/PyTorch and loads the pinned base tokenizer;
user text is not sent to the model hub. The optional dependency boundary is
`pip install -e ".[hhem]"`.

The upstream model card describes the score as a support score in `[0, 1]`:
higher means the hypothesis is better supported by the premise. EvalOps
maps `support_score < threshold` to `HALLUCINATED` and records
`hallucination_score = 1 - support_score`.

## RAGTruth context contract

The context builder is `ragtruth-source-context-v1`:

- QA uses the source passages only; the question/prompt is not passed as
  premise context.
- Summary uses the source information string.
- Data2txt uses stable, Unicode-preserving JSON for structured source info.

The response is the hypothesis. Prompts, labels, and human annotations are
not passed into the model. Input lengths are recorded. No truncation is
silently applied; long-input warnings remain visible in the run environment.

## Threshold and evaluation policy

The default threshold is `0.5`, recorded as
`fixed-probability-boundary-v1`. It is not tuned on the official test split.
The threshold utility can select a value from a validation split using a
deterministic candidate grid and seed, and explicitly rejects `split=test`.
For source-correlated data, validation work should split by `source_id`, not
random response rows.

Use the mini path for a local smoke test:

```bash
python -m evalops hallucination evaluate \
  --dataset ragtruth-mini \
  --split test \
  --evaluator hhem-2.1-open \
  --device cpu \
  --batch-size 2 \
  --local-files-only \
  --run-id ragtruth-mini-hhem-v1 \
  --output reports/ragtruth-mini-hhem-v1.json
```

The full official run is explicit and opt-in:

```bash
python -m evalops hallucination evaluate \
  --dataset ragtruth \
  --data-dir datasets/external/ragtruth \
  --split test \
  --evaluator hhem-2.1-open \
  --device cpu \
  --batch-size 16 \
  --local-files-only \
  --run-id ragtruth-test-hhem-v1 \
  --output reports/ragtruth-test-hhem-v1.json
```

Compare two artifacts only when they contain the same example IDs and human
labels:

```bash
python -m evalops hallucination compare \
  --baseline reports/ragtruth-test-heuristic-v1.json \
  --candidate reports/ragtruth-test-hhem-v1.json \
  --output reports/ragtruth-test-heuristic-vs-hhem.json
```

The comparison reports per-example transitions, false-positive/false-negative
IDs, metric deltas, and an exact two-sided McNemar test on the paired binary
correctness outcomes. The model-agnostic report also includes balanced
accuracy `(recall + specificity) / 2`.

## Official RAGTruth test run

The completed CPU run is preserved in
`reports/ragtruth-test-hhem-v1.json`; the paired comparison is
`reports/ragtruth-test-heuristic-vs-hhem.json`. Both evaluators used the same
2,675 included test responses and 25 excluded responses.

At the fixed threshold of `0.5`, HHEM produced accuracy `0.7566`, balanced
accuracy `0.7012`, F1 `0.5979`, precision `0.7160`, recall `0.5133`,
specificity `0.8891`, FPR `0.1109`, and FNR `0.4867`. Its confusion matrix was
TP `484`, TN `1540`, FP `192`, FN `459`.

Against the heuristic baseline, the primary metric deltas were accuracy
`+0.0647`, balanced accuracy `+0.1265`, F1 `+0.3095`, recall `+0.3362`, and
precision `-0.0608`. HHEM corrected 370 heuristic false negatives and 21
heuristic false positives; it introduced 192 false positives and 459 false
negatives of its own. The paired categories were both correct `1633`,
heuristic-only correct `218`, HHEM-only correct `391`, and both wrong `433`.
The exact two-sided McNemar p-value was `2.27e-12` (continuity-corrected
statistic `48.578`), indicating a statistically detectable paired difference,
not that HHEM is universally preferable.

Task-level HHEM F1 was Data2txt `0.6391`, QA `0.6000`, and Summary `0.4483`.
Model-level F1 ranged from `0.2025` for gpt-3.5-turbo-0613 to `0.6587` for
llama-2-13b-chat. The run recorded input lengths up to 2,723 tokens and zero
adapter-applied truncations; the upstream long-sequence warning is therefore
a material limitation for interpretation.

## Interpretation

RAGTruth results here are response-level comparisons against its preserved
human annotations. They are not upstream leaderboard scores. The mini
fixture is synthetic and only verifies plumbing. Model-backed results are
resource-dependent, should retain the exact artifact and manifest, and need
separate calibration/validation work before any production threshold claim.
