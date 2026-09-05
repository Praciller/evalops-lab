# ADR 0001: Static public Evidence Dashboard boundary

- Status: Accepted
- Date: 2026-09-05

## Context

EvalOps Lab needs a trustworthy public presentation of evaluation evidence without turning the repository into a hosted evaluator. The public surface must remain reviewable, deterministic, privacy-conscious, and inexpensive to operate. Existing evaluation results contain internal details that are useful for debugging but are not safe or necessary for publication.

## Decision

The future Evidence Dashboard will be a static, read-only frontend that consumes explicitly approved JSON artifacts produced by the Python core. Phase 1 defines the versioned Public Evidence Contract V1 and its transformation-only exporters. The pipeline is:

```text
Python evaluation core -> allowlisted sanitizer -> versioned JSON artifacts -> static frontend
```

The public contract carries explicit verification status, data kind, and claim scope. Exporters publish bounded metadata, aggregate metrics, stable safe record references, and structured failure summaries. They do not pass through arbitrary `details`, raw text, secrets, local paths, credentials, hidden reasoning, or unapproved files. Index construction accepts an explicit artifact list and never recursively discovers reports.

The public path does not run evaluation, inference, model providers, external downloads, or runtime APIs. A public comparison may summarize the existing deterministic regression report, but it does not redefine benchmark validity or population compatibility.

## Consequences

Positive consequences:

- Static hosting can serve immutable, cacheable evidence without runtime credentials or paid compute.
- The contract is testable independently from any frontend framework.
- Deterministic serialization supports review, checksums, and reproducible publication.
- Explicit status dimensions prevent synthetic fixtures, partial checks, and official benchmark results from being conflated.
- A frontend can be replaced without changing evaluation semantics.

Costs and constraints:

- Publication requires an explicit allowlist and artifact-selection step.
- Raw debugging context remains available only in internal result files.
- Future benchmark publication still requires dataset provenance, protocol, and owner review.
- Live dashboards, interactive evaluation, and provider-backed scoring are intentionally deferred.

## Rejected alternatives

- **Hosted API or FastAPI publication layer**: adds runtime attack surface and infrastructure without being required for a read-only evidence view.
- **Frontend importing Python internals or executing evaluation**: couples presentation to execution and makes public claims harder to audit.
- **Automatic recursive report discovery**: risks publishing ignored, stale, local, or unsafe artifacts.
- **Raw result passthrough**: can expose private responses, corpus text, paths, or secret-like fields.
