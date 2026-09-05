# Public Evidence Contract V1

## Purpose

Public Evidence Contract V1 is the implementation-facing boundary between EvalOps Lab evaluation outputs and a future static Evidence Dashboard. It is a publication contract, not a new evaluator and not a claim that every internal result is publishable.

## Scope

V1 supports three artifact types:

- `run`: one validated `EvaluationResult`, with allowlisted run metadata, aggregate metrics, bounded failures, and optional safe per-record evidence.
- `comparison`: one standard deterministic `RegressionReport`, with baseline/candidate artifact references and metric comparisons.
- `index`: an explicit, sorted catalog of approved run and comparison artifacts.

The exporter accepts one explicit source at a time. It does not discover files, run evaluation, download data, call providers, or invoke a frontend.

## Required claim dimensions

Every artifact declares all three independent dimensions:

| Dimension | V1 values | Meaning |
| --- | --- | --- |
| `verification_status` | `VERIFIED`, `PARTIAL`, `UNVERIFIED`, `NOT_RUN` | How far the artifact has been checked for its intended claim. |
| `data_kind` | `SYNTHETIC_FIXTURE`, `CURATED_DATASET`, `OFFICIAL_BENCHMARK` | What kind of data supports the artifact. |
| `claim_scope` | `INTEGRATION_ONLY`, `PROTOCOL_SPECIFIC`, `BENCHMARK_RESULT` | The narrowest claim the artifact may support. |

These dimensions are not a universal model-quality or model-superiority score. Limitations are required publication text when caveats matter.

## Allowlist and exclusions

Allowed run metadata includes evaluation type, run and dataset identifiers, dataset revision, system/model/retriever labels, benchmark language/split, evaluator versions, seed, timestamp, and git commit. Allowed evidence includes numeric finite metrics, safe document identifiers, scores, failure categories/classes, and stable record references.

The exporter excludes arbitrary `details`, raw responses, prompts, corpus text, human annotation text, hidden reasoning, credentials, secret-like values, authorization headers, environment values, absolute or local paths, and unsupported model/provider payloads. Unknown source fields are ignored rather than copied. External or official data defaults to aggregate-only evidence unless a future reviewed adapter expands the allowlist.

## Determinism

Public JSON uses UTF-8, stable sorted keys, stable list ordering, finite numeric values, and a trailing newline. Exporting the same validated source twice must produce identical bytes. Export output contains no generated UUID, current export timestamp, filesystem path, or unordered collection dependence.

## CLI contract

```text
evalops evidence export --source SOURCE.json --source-type run|comparison --output PUBLIC.json \
  --artifact-id ID --verification-status STATUS --data-kind KIND --claim-scope SCOPE
evalops evidence index --artifact APPROVED-1.json --artifact APPROVED-2.json --output INDEX.json
```

Comparison exports additionally require `--baseline-artifact-id` and `--candidate-artifact-id`. The CLI is transformation-only and prints the same canonical artifact it writes.

## Acceptance criteria

- Pydantic models reject unknown public fields and unsafe publication text.
- Tests prove allowlist behavior, raw-detail exclusion, external-evidence suppression, malformed-source failure, deterministic bytes, explicit index membership, and stable regression mapping.
- The exporter is usable from Python and from the CLI without adding frontend, server, provider, or external dataset dependencies.

## Out of scope

Frontend implementation, deployment, runtime APIs, live monitoring, full external corpus preparation, new evaluators, model inference, Phase 5A/5B custom report normalization, and claims of production or official benchmark validity without the required evidence.
