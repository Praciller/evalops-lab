# Phase 4: Comparison + Failure Explorer Design

Date: 2026-09-05
Repository: `Praciller/evalops-lab`
Status: Approved design, pending implementation planning

## 1. Goal

Extend the static Evidence Console from single-run inspection to a traceable regression story:

`metric changed -> regression policy fired -> record evidence explains why`.

The public demo remains static, read-only, synthetic, deterministic, zero-cost, and provider-free. Phase 4 must not introduce runtime inference, APIs, external datasets, authentication, analytics, or benchmark/model-superiority claims.

## 2. Current constraints

- Existing public evidence contract: `public-evidence-v1`.
- Existing public run artifacts are explicit allowlisted JSON files.
- Existing comparison export model already exists in Python as `PublicComparisonArtifactV1`.
- Existing regression engine already supports `PASS`, `REGRESSION`, and `MISSING` with metric direction and degradation tolerance.
- Existing frontend validates run artifacts and index summaries fail-closed.
- GitHub Pages remains the production target under `/evalops-lab`.

## 3. Architecture decision

Use one deterministic, same-population synthetic baseline/candidate pair on the checked-in retrieval fixture. Do not compare the retrieval fixture to the MIRACL-shaped fixture because their populations and protocols differ.

### 3.1 Public artifact set

The Phase 4 public bundle contains:

- `demo-miracl-th-mini-v1` — existing synthetic MIRACL-shaped run.
- `demo-retrieval-fixture-v1` — existing retrieval candidate run; do not rewrite its semantics.
- `demo-retrieval-reference-v1` — new deterministic reference run.
- `demo-retrieval-regression-v1` — new comparison artifact produced through the existing regression engine and public comparison adapter.

`apps/web/public/evidence/index.json` remains an explicit allowlist. No filesystem discovery is permitted.

### 3.2 Reference fixture

Add `datasets/fixtures/retrieval-reference-predictions.jsonl` with the same five query IDs as the existing retrieval ground truth:

```text
THQA-001 -> [doc-th-001, doc-th-999]
THQA-002 -> []
THQA-003 -> [doc-th-003, doc-th-002]
THQA-004 -> [doc-th-004]
THQA-005 -> [doc-th-005, doc-th-006]
```

The candidate remains `datasets/fixtures/retrieval-predictions.jsonl` unchanged.

## 4. Regression policy

Evaluate reference and candidate with the same deterministic retrieval evaluator, metadata population, and `top_k=5`. Compare these aggregate metrics:

- `hit_rate_at_5`
- `mrr`
- `ndcg_at_5`
- `precision_at_5`
- `recall_at_5`

For all five metrics:

```text
direction = HIGHER_IS_BETTER
max_degradation = 0.10
```

Expected synthetic demonstration behavior is four `REGRESSION` outcomes and one `PASS` outcome, with overall `passed=false`. Tests may assert this expected behavior, but artifact values, deltas, reasons, and statuses must be produced by the deterministic evaluator plus `compare_metrics()`; they must not be hard-coded into public JSON or frontend logic.

## 5. Public comparison contract

The frontend gains a strict schema/parser for the full comparison artifact, mirroring the Python public export model:

- baseline/candidate artifact IDs and run IDs
- `passed`
- comparison metric records
- direction, values, delta, status, and reason
- claim dimensions and limitations
- population compatibility

### 5.1 Population compatibility

Harden public-export population compatibility to an enum:

```text
MATCHED
UNVERIFIED
INCOMPATIBLE
```

The Evidence Console may render a regression verdict and record-level transitions only when compatibility is `MATCHED`.

`MATCHED` must be recomputed from the loaded baseline and candidate rather than trusted as caller text. These fields must match:

- dataset name, version, and revision
- evaluation type
- benchmark
- language
- split
- top_k
- evaluator versions

These fields may differ because they can be the subject of comparison: system name, model/provider, retriever/version, timestamp, and git commit.

If required population/protocol fields differ, the public comparison cannot be treated as `MATCHED` and record-transition inference is unavailable.

## 6. Frontend repository boundary

Add `getComparisonArtifact(id)` and `getComparisonBundle(id)` following the current fail-closed run repository pattern.

`getComparisonBundle()` must validate all of the following before returning data:

- comparison exists in the explicit index and has type `comparison`
- baseline and candidate references exist and target run artifacts in the same index
- full comparison payload references match the index summary
- baseline/candidate run IDs match the loaded runs
- claim dimensions remain compatible with public policy
- comparison artifact uses the approved synthetic/integration-only claim dimensions for this demo
- population compatibility equals `MATCHED`
- compatibility recomputed from both loaded runs is also `MATCHED`
- referenced files use safe artifact IDs and cannot escape the evidence directory

Any mismatch returns the generic existing contract error: `Evidence unavailable`. Partial comparison rendering is forbidden.

## 7. Routes and navigation

Keep the explorer comparison-scoped:

```text
/
/runs/[artifactId]/
/comparisons/[artifactId]/
/comparisons/[artifactId]/failures/
```

Do not add a global `/failures/` route in Phase 4.

Recruiter-facing flow:

`Overview -> regression comparison -> metric policy result -> record changes -> reference/candidate run evidence`.

## 8. Comparison detail UX

The comparison page contains six bounded sections:

1. Verdict: regression detected or passed, sourced from the comparison artifact.
2. Reference vs candidate metadata with links to both run pages.
3. Population compatibility status.
4. Metric comparison table: reference, candidate, delta, direction, status, and policy reason.
5. Record-change summary and link to Failure Explorer.
6. Limitations/contract notes that retain `VERIFIED`, `SYNTHETIC_FIXTURE`, and `INTEGRATION_ONLY` wording.

The overview adds one restrained Regression Evidence section. It must state that this is a synthetic same-population regression demonstration, not an official benchmark or model-superiority result.

No composite quality score, gauge, leaderboard, animation, decorative chart wall, or inferred statistical significance is added.

## 9. Failure Explorer derivation

Do not add failure transitions to the public contract. Derive them at build/render time from the two approved public run artifacts by joining exact `record_ref` sets.

The record sets must be equal. A missing or extra record on either side makes record-level comparison unavailable; no partial join is permitted.

Transition states are:

```text
PASS -> PASS                    STABLE_PASS
PASS -> non-PASS                INTRODUCED_FAILURE
non-PASS -> PASS                RESOLVED_FAILURE
same non-PASS -> same non-PASS  PERSISTENT_CATEGORY
non-PASS A -> non-PASS B        CHANGED_FAILURE_CATEGORY
```

`SHOULD_ABSTAIN` is an evaluation condition when no relevant document exists, so persistent `SHOULD_ABSTAIN` must be labeled `Persistent category`, not `Persistent system failure`.

Record metric deltas are shown independently from category transitions. A `PASS -> PASS` record may have changed metrics, but the UI must not label the record itself a regression unless a record-level regression policy exists. Phase 4 defines no such policy.

The explorer may expose only already-public fields:

- record ID
- retrieved document IDs
- relevant document IDs
- per-record metrics
- failure category
- failure class when present

It must not expose query text, corpus text, raw answers, prompts, authorization data, model/provider secrets, hidden reasoning, or unapproved report content.

## 10. Failure Explorer UX

Provide simple client-side controls only:

- transition filter
- candidate category filter
- changed-records-only toggle
- record ID search

Each table row may use semantic `<details>` for expanded evidence. Avoid adding a dialog framework or global application state for this slice.

## 11. Generator and deterministic bundle

Extend `scripts/generate_public_demo_evidence.py` explicitly; do not introduce directory scanning.

Generation order:

1. evaluate the new reference retrieval fixture
2. evaluate the unchanged candidate retrieval fixture
3. evaluate the existing MIRACL-shaped fixture
4. call `compare_metrics(candidate_metrics, reference_metrics, rules)`
5. adapt the resulting regression report to `demo-retrieval-regression-v1`
6. build the explicit public index from the four approved artifacts
7. write exactly four artifact JSON files plus `index.json`

The tracked-bundle test must assert the exact five-file inventory and byte-compare fresh deterministic generation with `apps/web/public/evidence/`.

No external model inference, provider credentials, data downloads, or hidden source reports are permitted during generation.

## 12. Testing requirements

### Python

Required coverage includes deterministic reference evaluation, comparison generation through the real regression engine, expected 4-regression/1-pass policy result, comparison `passed=false`, population compatibility checks, self-comparison rejection, exact file inventory, and byte-identical bundle drift protection.

Run full Python gates: `pytest`, `ruff check`, `ruff format --check`, and `mypy`.

### TypeScript contract and repository

Required negative coverage includes:

- malformed or unknown comparison status/direction
- invalid public claim combinations or `NOT_RUN`
- missing, dangling, self, or comparison-to-comparison references
- baseline/candidate run ID mismatches
- index/payload reference mismatches
- dataset name/version/revision mismatches
- evaluation type, benchmark, language, split, top_k, or evaluator-version mismatches
- population compatibility other than `MATCHED`
- unexpected fields and unsafe artifact IDs/path traversal

Positive coverage must include one valid same-population comparison bundle.

### Transition logic

Unit-test every transition state, changed metrics with stable category, unequal record sets failing closed, and deterministic behavior independent of record ordering.

### Browser and accessibility

Playwright must cover Overview -> Comparison -> Failure Explorer -> Run navigation in local and GitHub Pages modes, including desktop and 390px mobile layouts, keyboard traversal, dark theme, root horizontal overflow, internal table scrolling, axe serious/critical violations, static assets, and unexpected external network requests.

Visual regression coverage must include at least:

- comparison desktop
- comparison mobile
- failure explorer desktop
- failure explorer mobile

The mobile regression test must explicitly assert that the root viewport does not horizontally overflow while wide evidence tables remain internally scrollable.

## 13. CI path coverage

Web and Pages workflows must run when Phase 4 evidence semantics can change. Relevant paths include:

```text
apps/web/**
scripts/generate_public_demo_evidence.py
datasets/fixtures/retrieval-ground-truth.jsonl
datasets/fixtures/retrieval-predictions.jsonl
datasets/fixtures/retrieval-reference-predictions.jsonl
src/evalops/export/**
src/evalops/regression/**
src/evalops/evaluators/retrieval/**
src/evalops/models/runs.py
```

Do not weaken existing Python or Web CI gates.

## 14. Production acceptance

Phase 4 is complete only after merge to `main`, successful Python CI, successful Web CI, successful GitHub Pages deployment, and fresh production browser verification.

Production routes to verify:

```text
/evalops-lab/
/evalops-lab/comparisons/demo-retrieval-regression-v1/
/evalops-lab/comparisons/demo-retrieval-regression-v1/failures/
/evalops-lab/runs/demo-retrieval-reference-v1/
/evalops-lab/runs/demo-retrieval-fixture-v1/
```

Verification must cover HTTP 200, navigation, assets, theme, 390px overflow, accessibility, external-network boundary, synthetic/integration-only labels, comparison values/statuses, and record transitions.

README may receive a minimal recruiter-facing update after the production deployment is verified. `DEPLOY.md` needs no architectural rewrite unless deployment mechanics change.

## 15. Scope

### In scope

- deterministic reference fixture and reference run
- public comparison artifact and strict frontend parser/repository support
- population-compatibility hardening
- Overview regression evidence section
- comparison detail route
- comparison-scoped Failure Explorer
- simple client-side filters/search
- deterministic failure-transition derivation
- full contract, unit, E2E, accessibility, visual, and CI coverage
- GitHub Pages production verification

### Out of scope

- official MIRACL or RAGTruth comparison publication
- provider/model inference or external API calls
- runtime evaluator execution in the browser
- backend/API/database/authentication/analytics
- model-vs-model leaderboard
- global `/failures/` experience
- user-uploaded runs
- Storybook or design-system redesign
- dashboards, gauges, or decorative chart walls
- statistical-significance claims
- automatic regression history
- custom domain or paid hosting

## 16. Non-negotiable evidence semantics

- Synthetic fixtures remain `SYNTHETIC_FIXTURE` + `INTEGRATION_ONLY`.
- No official benchmark-result claim is introduced.
- `SHOULD_ABSTAIN` is not automatically described as a system failure.
- Aggregate metric policy determines aggregate regression status; record metric changes do not create an inferred record-level regression policy.
- No partial population join or partial comparison rendering is allowed.
- Public comparison values and statuses come from the evaluation/regression pipeline, not frontend arithmetic that changes the source of truth.
- The public artifact bundle remains explicit, deterministic, sanitized, and byte-drift guarded.

## 17. Success signal

A reviewer should be able to start from the live Overview and answer, using only approved evidence:

1. Did the candidate regress under a declared deterministic policy?
2. Which metrics crossed the tolerance?
3. Which records changed category or metrics?
4. Can the reviewer trace those records back to both approved run artifacts?
5. Are the limits of the claim visible without reading repository internals?

If all five answers are yes without exposing raw corpus/model content or relying on runtime services, Phase 4 has achieved its purpose.
