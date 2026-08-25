# Reproducibility guide

EvalOps Lab is designed to run locally without paid APIs or external services.
Normal tests and CI are offline and do not download external datasets or HHEM.

## Supported setup

- Python 3.11 or newer; CI runs Python 3.12.
- Install the core and development tools:

```bash
python -m venv .venv
python -m pip install -e ".[dev]"
```

The optional HHEM group is separate:

```bash
python -m pip install -e ".[hhem]"
```

It provides the pinned Transformers/Torch/safetensors/sentencepiece boundary.
Model weights remain in the external Hugging Face cache and are never stored
in this repository.

## Offline validation

```bash
pytest
ruff check .
ruff format --check .
mypy src
```

The included fixtures can also be exercised manually:

```bash
python -m evalops dataset validate \
  datasets/fixtures/thai-rag-sample.jsonl \
  --document-catalog datasets/fixtures/document-catalog.txt

python -m evalops retrieval evaluate \
  --ground-truth datasets/fixtures/retrieval-ground-truth.jsonl \
  --predictions datasets/fixtures/retrieval-predictions.jsonl \
  --k 5

python -m evalops dataset prepare miracl --language th --split dev --mini
python -m evalops benchmark miracl --language th --split dev --retriever bm25 --k 5 --mini
python -m evalops dataset prepare ragtruth --mini
```

Mini MIRACL and RAGTruth runs use synthetic fixtures and are not official
benchmark scores.

## External benchmark preparation

Preparation is explicit and writes only to ignored local storage. MIRACL
topics/qrels can be prepared without the large corpus:

```bash
python -m evalops dataset prepare miracl \
  --language th --split dev --topics-qrels-only
```

The full MIRACL corpus and official RAGTruth files use the pinned revisions in
their manifests and are not part of normal tests or CI. See
[`miracl-benchmark.md`](miracl-benchmark.md) and
[`ragtruth-benchmark.md`](ragtruth-benchmark.md).

## RAGTruth evaluation

With the official RAGTruth snapshot already prepared locally:

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

HHEM is opt-in and requires the reviewed manifest and exact model revision.
Use `--local-files-only` when the required snapshots are already cached:

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

The loader checks the exact model/tokenizer revisions, reviewed custom-code
hashes, configuration hash, and weight-file identity before importing remote
code. See [`hhem-evaluator.md`](hhem-evaluator.md) for the protocol and
security boundary.

## Artifacts and comparisons

Run artifacts contain dataset/evaluator configuration, metrics, slices,
failures, per-example evidence, and Git commit provenance when a valid HEAD
exists. Compare same-population hallucination artifacts with:

```bash
python -m evalops hallucination compare \
  --baseline reports/ragtruth-test-heuristic-v1.json \
  --candidate reports/ragtruth-test-hhem-v1.json \
  --output reports/ragtruth-test-heuristic-vs-hhem.json
```

The regression interface remains available for retrieval artifacts:

```bash
python -m evalops regression compare \
  --baseline <baseline.json> \
  --candidate <candidate.json> \
  --policy datasets/fixtures/miracl-mini-baseline-policy.json
```

The Phase 3/4 artifacts were generated before the initial repository commit
and truthfully retain `git_commit: null`. Future runs should automatically
capture the finalization commit or a later commit in their run envelope.
