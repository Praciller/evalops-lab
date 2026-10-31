# Thai Support RAG → EvalOps (synthetic baseline)

This opt-in local integration connects the separately maintained public
[Customer Support RAG Triage Agent](https://github.com/Praciller/customer-support-rag-triage-agent)
with EvalOps Lab's existing `retrieval evaluate` CLI. It **does not** duplicate the
evaluation engine or automatically import customer records.

The importer accepts only `synthetic-thai-enterprise-policy-v1` results in
`offline_character_bigram_lexical_baseline` mode, verifies unique case/document
IDs and permission-safe flags, and exports **only IDs**, not question text,
policy bodies, user data, prompt contents, or credentials.

## Windows / PowerShell (local only)

First check out a version of Customer Support RAG containing
`src/evaluation/evaluate_thai_policy.py` and its synthetic dataset.

```powershell
cd C:\dev\customer-support-rag-triage-agent
uv run --no-project --python 3.13 python -m src.evaluation.evaluate_thai_policy > "$env:TEMP\support-thai-eval.json"

cd C:\dev\evalops-lab
$env:THAI_EXPORT = "$env:TEMP\evalops-thai-support"
uv run --no-project --python 3.13 python scripts/import_synthetic_thai_support.py --report "$env:TEMP\support-thai-eval.json" --output-dir $env:THAI_EXPORT

$env:PYTHONPATH = "$PWD\src"
uv run --no-project --python 3.13 --with "pydantic>=2.7,<3" python -c 'from evalops.cli import main; raise SystemExit(main())' retrieval evaluate --ground-truth "$env:THAI_EXPORT\ground_truth.jsonl" --predictions "$env:THAI_EXPORT\predictions.jsonl" --k 5 --dataset-name synthetic-thai-enterprise-policy-v1 --dataset-version fixture-v1 --system-name support-thai-lexical-baseline --run-id support-thai-local --output "$env:THAI_EXPORT\evalops-run.json"
```

The resulting `metadata.json` records the synthetic and integration-only
boundaries. Inspect it before interpreting or sharing any evaluation run.
By design, the converter **fails closed** on a different dataset, model mode,
missing permission checks, duplicated case IDs, or mismatched counts.

## What the metrics do and do not say

EvalOps's retrieval evaluator measures rankings against this small fixture's
relevance IDs. Query-level negative/abstention cases and permission checks
remain separately recorded in the source and metadata; retrieval ranking
metrics alone are **not** sufficient proof of access control, safe abstention,
or LLM prompt-injection resistance.

The current 8-case fixture has 5 retrieval-positive cases and 3 deliberate
abstentions. The existing EvalOps retrieval evaluator counts all 8 input
queries in its aggregate denominator; it therefore reports Recall@5 = 5/8
(0.625), **not** the positive-only retrieval success rate (5/5). Assess the
3/3 synthetic abstentions separately and never interpret the mixed-population
aggregate as an estimate of real-world relevance accuracy. Compare only
identically defined populations across runs.

The baseline uses character-bigram lexical overlap; it is **not** semantic
Thai retrieval quality, OCR quality, live customer-support accuracy, or
production permission enforcement. For a stronger comparison, add reviewed,
non-sensitive Thai queries and judgments plus a Thai-capable embedding
baseline, then compare paired runs on the same labeled population.

## Verification

```powershell
uv run --no-project --python 3.13 --with pytest python -m pytest tests/test_support_thai_import.py -q
uvx --python 3.13 ruff check scripts/import_synthetic_thai_support.py tests/test_support_thai_import.py
```

No public artifact is created automatically. This integration never
modifies a hosted EvalOps evidence catalog or consumes a model/API quota.
