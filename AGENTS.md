# AGENTS.md

## Purpose

EvalOps Lab is a testing-first Python framework for reproducible AI reliability evaluation. The initial supported use case is Thai/English RAG retrieval and chatbot evaluation. The repository is an evaluation product, not a chatbot application.

## Architecture

- `src/evalops/models/` contains Pydantic contracts for datasets, runs, failures, and retrieval inputs.
- `src/evalops/datasets/` loads JSONL and validates human-authored cases.
- `src/evalops/evaluators/retrieval/` contains dependency-light deterministic metrics.
- `src/evalops/evaluators/generation/` and `src/evalops/evaluators/judge/` contain future adapter interfaces only.
- `src/evalops/runners/` orchestrates evaluators into traceable result envelopes.
- `src/evalops/retrieval/` contains the generic retriever interface and deterministic BM25 baseline.
- `src/evalops/benchmarks/` connects normalized MIRACL data to retrievers and the existing metric layer.
- `src/evalops/regression/` compares current metrics against baselines.
- `datasets/` contains manifests and clearly labeled small fixtures; full external datasets are excluded.
- `tests/` is the executable contract for public behavior.

## Allowed commands

From the repository root:

```text
python -m pip install -e ".[dev]"
pytest
ruff check .
ruff format --check .
mypy src
python -m evalops dataset validate datasets/fixtures/thai-rag-sample.jsonl --document-catalog datasets/fixtures/document-catalog.txt
python -m evalops retrieval evaluate --ground-truth datasets/fixtures/retrieval-ground-truth.jsonl --predictions datasets/fixtures/retrieval-predictions.jsonl --k 5
python -m evalops dataset prepare miracl --language th --split dev --mini
python -m evalops benchmark miracl --language th --split dev --retriever bm25 --k 5 --mini
python -m evalops regression compare --baseline <baseline.json> --candidate <candidate.json> --policy datasets/fixtures/miracl-mini-baseline-policy.json
```

Use `apply_patch` for source edits. Keep changes small and reviewable.

## Code and testing rules

- Use Python `src/` layout, type annotations, Pydantic models, and deterministic standard-library formulas where practical.
- Every metric implementation requires manually verifiable tests.
- Every bug fix requires a regression test when practical.
- Tests should exercise public behavior, not private implementation details.
- Do not claim an evaluator works unless its behavior is tested with appropriate evidence.
- Preserve separation between human labels, system outputs, and model-generated judge outputs.
- Do not replace deterministic metrics with LLM judgment when deterministic evaluation is available.

## Dataset and security boundaries

- Never commit API keys, tokens, credentials, or `.env` files.
- Never commit full external datasets unless licensing, provenance, and size have been explicitly reviewed.
- Do not invent or guess upstream license information; use `REQUIRES_UPSTREAM_LICENSE_VERIFICATION` until verified.
- External snapshots must be prepared explicitly, checksum-checked where practical, and kept under ignored `datasets/external/`.
- MIRACL full-dev preparation and execution are opt-in; never download the full corpus in ordinary tests or CI.
- Never report the synthetic `miracl-th-mini` fixture as an official MIRACL score.
- Never silently alter ground truth to improve scores.
- Synthetic fixtures must be clearly labeled and must not be presented as benchmark results.
- Do not add paid infrastructure, external API calls, vector databases, or provider credentials to local tests.

## Frontend Evidence Console rules

- The `apps/web` app is a static export and may read only the explicit checked-in `public/evidence/index.json` and artifact files named by that index.
- Keep the public Zod mirror strict and fail closed; never expose raw details, responses, prompts, corpus text, hidden reasoning, paths, or secrets.
- Preserve `SYNTHETIC_FIXTURE` and `INTEGRATION_ONLY` labels in the UI; synthetic MIRACL-shaped data is never an official benchmark result.
- Do not add API routes, server actions, model/provider inference, external fetches, authentication, persistence, analytics, or deployment configuration in Phase 2.
- Frontend changes require npm lint, typecheck, unit tests, static build, Playwright/axe checks, and reviewed screenshots in `docs/screenshots/evidence-console/`.

## Required validation before completion

Run the full applicable suite: `pytest`, `ruff check .`, `ruff format --check .`, and `mypy src`. Manually exercise the CLI with included fixtures. Inspect `git status` and `git diff --check`. Report limitations honestly; use `UNVERIFIED` or `PLANNED` when evidence is unavailable.
