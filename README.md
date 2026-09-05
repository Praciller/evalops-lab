# EvalOps Lab

AI reliability testing and evaluation framework for RAG systems, LLM outputs, and AI-generated code with reproducible benchmarks, failure analysis, and regression testing.

EvalOps Lab treats AI evaluation as a software and data quality problem rather than relying on a single model-generated score.

## Recruiter snapshot

**Signal:** Reproducible AI evaluation for retrieval, groundedness, failure taxonomy, and regression decisions.

[Repository](https://github.com/Praciller/evalops-lab)

**What this demonstrates:** dataset and provenance validation · deterministic retrieval metrics · evaluator and failure-analysis separation.

**Boundary:** this is a local evaluation framework with no hosted demo or model-superiority claim.

## Problem

An answer can look fluent while being wrong, unsupported by retrieved context, stale, incomplete, or unsafe to change. A score without ground truth, provenance, and failure evidence does not provide a reliable engineering signal.

## Goals

The bootstrap establishes a local, testing-first core for Thai/English RAG evaluation:

1. validate dataset quality before evaluating a system;
2. prefer deterministic retrieval metrics;
3. classify failures instead of hiding them behind averages;
4. record dataset, evaluator, run, and system provenance;
5. compare current results with a baseline using explicit thresholds.

## Architecture

```text
Dataset → validation → evaluation runner → metric evaluators
                                      ↓
                         failure taxonomy + structured result
                                      ↓
                             baseline/regression comparison
```

The first runnable path is retrieval evaluation. Generation remains a typed
interface for future adapters. The bounded Phase 5A LLM-as-a-Judge path is
opt-in and does not replace human ground truth or existing deterministic/HHEM
results. The owner-authorized Phase 5B-L local full benchmark is recorded as a
separate protocol-specific baseline; it does not authorize a new Gemini run or
another model experiment.

### Public Evidence Dashboard boundary

The future public dashboard is a static, read-only presentation of explicitly
approved, sanitized JSON artifacts. The Python evaluation core remains the
source of truth; the public path does not run evaluation, call model providers,
download external data, or expose raw result details. Phase 1 defines the
versioned Public Evidence Contract and exporters; frontend implementation and
deployment remain future work.

## Implemented

- Pydantic schemas for curated RAG cases, retrieval inputs, run metadata, and results.
- Dataset validation for required fields, duplicate IDs, near-duplicate questions, constrained labels, empty ground truth, and optional document catalogs.
- Deterministic Precision@K, Recall@K, Hit Rate@K, MRR, and binary-relevance nDCG with unit tests.
- Explicit RAG failure taxonomy and per-query retrieval classifications.
- Higher-is-better/lower-is-better baseline comparison with minimum/maximum thresholds and allowable degradation.
- JSONL loading, traceable result serialization, and a small reusable CLI.
- Synthetic Thai fixtures, a pinned MIRACL Thai adapter/mini benchmark, checksum-aware non-destructive preparation, and GitHub Actions CI.
- RAGTruth human-label normalization, strict/factual annotation policies, quality filtering, deterministic heuristic hallucination evaluation, and failure analysis.
- Optional pinned HHEM-2.1-Open model evaluation with reviewed custom-code hashes, deterministic context construction, threshold leakage protection, and paired McNemar comparison.
- Phase 5A LLM judge pilot framework with frozen strict-groundedness contracts,
  provider-independent readiness, preserved Gemini/Groq/OpenRouter/OKMD
  adapters, deterministic balanced sampling, resumable bounded execution, and
  aggregate comparison tooling. See
  [`docs/llm-judge-pilot.md`](docs/llm-judge-pilot.md).

## Evaluation layers

EvalOps Lab keeps the evidence chain separate:

1. Dataset manifests and validation establish what data is being evaluated.
2. Human labels remain distinct from system predictions and model-generated judge outputs.
3. Deterministic metrics and model-backed evaluators produce traceable results.
4. Failure analysis and regression comparison turn scores into engineering evidence.

Human labels remain distinct from model-generated judge outputs. Phase 5A is a
bounded evaluator-validation framework, and the completed Phase 5B-L result
reports full-population RAGTruth performance only for its frozen local
protocol.

## Initial datasets

- **MIRACL Thai:** Phase 2 retrieval benchmark integration. The repository contains verified source metadata and a synthetic offline fixture; the full corpus is prepared locally under ignored storage and is not committed.
- **RAGTruth:** Phase 3 human-annotation comparison for groundedness/hallucination evaluation. The adapter, pinned preparation, deterministic heuristic baseline, response-level metrics, slices, FP/FN evidence, and synthetic offline fixture are implemented. The official snapshot is prepared locally under ignored storage and is not committed.
- **HHEM-2.1-Open:** Phase 4 optional model-backed evaluator with an exact model/tokenizer revision, reviewed custom-code hashes, deterministic RAGTruth context construction, threshold reporting, and paired comparison utilities. It is opt-in and is not imported by the default offline test path.
- **thai-rag-eval-200:** manual curation specification with five labeled seed fixtures. The five records validate the schema and pipeline; they are not a 200-case benchmark.

Dataset metadata and rules are in [`datasets/README.md`](datasets/README.md) and [`datasets/manifests/`](datasets/manifests/). MIRACL and RAGTruth metadata are pinned to verified upstream revisions recorded in their manifests.

Verified results are consolidated in [`docs/benchmark-results.md`](docs/benchmark-results.md).
The reproducible command flow is in [`docs/reproducibility.md`](docs/reproducibility.md),
and HHEM provenance/security details are in [`docs/hhem-evaluator.md`](docs/hhem-evaluator.md).
The isolated local Ollama/Qwen3 Phase 5A-L and completed Phase 5B-L
experiments are documented in [`docs/llm-judge-pilot.md`](docs/llm-judge-pilot.md);
they remain separate from the partial Gemini pilot and do not authorize a new
Gemini/model experiment.

## RAGTruth hallucination benchmark

The official RAGTruth files are prepared and evaluated explicitly; normal CI
remains offline. Use the synthetic fixture for tests and the real command only
after choosing to download the pinned snapshot. See the detailed
[RAGTruth benchmark guide](docs/ragtruth-benchmark.md) for the annotation
policies, quality filtering, leakage boundary, and baseline limitations.
The optional model-backed path is documented in the
[HHEM evaluator guide](docs/hhem-evaluator.md).

## MIRACL Thai Benchmark

MIRACL Thai provides native-language passage retrieval queries, TREC-style
qrels, and a large Thai Wikipedia passage corpus. The official sources report
542,166 Thai passages from 128,179 articles, with 733 dev queries and 7,573
dev judgments. See the detailed [MIRACL benchmark guide](docs/miracl-benchmark.md)
and the verified [MIRACL project repository](https://github.com/project-miracl/miracl).

Preparation is explicit and pinned to recorded upstream revisions:

```bash
evalops dataset prepare miracl --language th --split dev --mini
evalops dataset prepare miracl --language th --split dev --topics-qrels-only
```

The first command is offline and uses a **synthetic test fixture, not MIRACL
benchmark data**. The second prepares real topics/qrels without downloading the
large corpus. Full preparation and the opt-in BM25 dev run are documented in
[`docs/miracl-benchmark.md`](docs/miracl-benchmark.md). Normal CI never
downloads the full dataset.

The baseline is a deterministic local BM25 retriever with Thai character
bigrams/trigrams plus Latin/number runs. It uses the existing EvalOps metric
layer and persists per-query rankings, scores, qrels, failure counts, source
revisions, tokenization strategy, and run metadata. Results are not described
as official MIRACL leaderboard scores.

The official Thai corpus listing shows two shards totaling about 110 MB
compressed. Because the transparent BM25 baseline expands the corpus into an
in-memory index, the full run is intentionally not part of normal validation;
available memory must be assessed before an owner-run experiment.

## Metrics and failure taxonomy

Retrieval metrics are implemented locally so their formulas are visible and independently tested. Sequence callers use binary relevance; MIRACL qrel mappings preserve positive graded labels for nDCG. Duplicate retrieved IDs cannot create extra hits. Precision retains `k` as its denominator when fewer than `k` results are returned. Empty relevance sets score zero and are not silently treated as successful retrieval.

Initial constrained failure categories include `PASS`, `RETRIEVAL_MISS`, `WRONG_ANSWER`, `HALLUCINATION`, `UNSUPPORTED_CLAIM`, `WRONG_CITATION`, `INCOMPLETE_ANSWER`, `CONTEXT_CONFLICT`, `SHOULD_ABSTAIN`, `DATASET_AMBIGUOUS`, and `GROUND_TRUTH_ERROR`.

## Reproducibility

Every result envelope records run ID, dataset name/version, system name, top-k, evaluator versions, optional model/provider/prompt/retriever details, random seed, timestamp, and Git commit when available. Local evaluation requires no paid service or API key.

See the [reproducibility guide](docs/reproducibility.md) for installation,
offline fixtures, opt-in external preparation, HHEM setup, and artifact comparison.

## Security and provenance

External datasets and model weights stay outside Git. HHEM execution is
opt-in, pinned to one reviewed revision, and guarded by a manifest that checks
the tokenizer revision, configuration/custom-code hashes, and safe weight-file
identity before importing remote code. Default CI installs only `.[dev]` and
does not download datasets or execute HHEM custom code.

The repository includes source, tests, metadata, and small synthetic fixtures;
it does not redistribute the external MIRACL/RAGTruth corpora or HHEM weights.
Upstream terms recorded in the manifests must be re-checked before any
redistribution, and this repository does not assert a project license for
those upstream assets.

## Local setup

Python 3.11+ is supported; CI runs Python 3.12.

```bash
python -m venv .venv
python -m pip install -e ".[dev]"
```

## Fast reviewer path

From the repository root, run the deterministic offline path:

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python -m evalops dataset validate datasets/fixtures/thai-rag-sample.jsonl --document-catalog datasets/fixtures/document-catalog.txt
python -m evalops retrieval evaluate --ground-truth datasets/fixtures/retrieval-ground-truth.jsonl --predictions datasets/fixtures/retrieval-predictions.jsonl --k 5
python -m evalops benchmark miracl --language th --split dev --retriever bm25 --k 5 --mini
```

The MIRACL command uses the clearly labeled synthetic `miracl-th-mini`
fixture; its perfect fixture score is not an official MIRACL result.

## CLI examples

Validate the labeled fixture and its document references:

```bash
python -m evalops dataset validate \
  datasets/fixtures/thai-rag-sample.jsonl \
  --document-catalog datasets/fixtures/document-catalog.txt
```

Run retrieval evaluation and print the JSON result:

```bash
python -m evalops retrieval evaluate \
  --ground-truth datasets/fixtures/retrieval-ground-truth.jsonl \
  --predictions datasets/fixtures/retrieval-predictions.jsonl \
  --k 5 \
  --run-id fixture-run-v1
```

The installed entry point is also available as `evalops ...` after installation.

## Tests and CI

```bash
pytest
ruff check .
ruff format --check .
mypy src
```

GitHub Actions runs the same lint, format, type, and test gates on pushes and pull requests without external API keys.

## Roadmap

- Phase 5B-L: completed owner-authorized full-population local LLM-as-a-Judge
  benchmark; HHEM remains the default detector and Qwen3 local is
  complementary.
- Future: publish the frozen benchmark baseline and evidence.
- Future: expand the curated Thai evaluation benchmark.
- Future: add code-generation and code-migration evaluator adapters.

## Limitations

The full MIRACL Thai dev BM25 run is not executed because the current
in-memory index resource requirements were not safely established. HHEM CPU
inference is slow, observed inputs reached approximately 2,723 tokens without
adapter truncation, and HHEM-only threshold calibration/bootstrap intervals
remain future work. The completed local RAGTruth result is protocol-specific
and is not a leaderboard or universal generalization claim. The MIRACL and
RAGTruth mini fixtures are synthetic and must not be presented as official
benchmark performance. The five `thai-rag-eval-200` records are a seed
fixture, not a 200-case benchmark.
