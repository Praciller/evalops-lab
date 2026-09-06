# Phase 6.3 Comparison & Failure Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Promote the Local Workspace from a retrieval runner into a reproducible EvalOps regression workflow with an explicit immutable baseline pointer, fail-closed compatibility, deterministic metric regression decisions, explicit exploratory-only comparisons, and private local failure-transition analysis.

**Architecture:** A workspace-level baseline pointer references a completed run ID + result hash; it never mutates the run. Comparison creation snapshots baseline/candidate identities and first evaluates compatibility. Canonical comparison is allowed only for compatible operands and delegates metric decisions to the existing `compare_metrics()` implementation using one versioned Workspace retrieval policy. Non-compatible operands may be compared only through an explicit `EXPLORATORY_ONLY` mode that cannot later be reclassified. Failure transitions are derived from persisted per-query categories, not from public sanitized artifacts.

**Tech Stack:** Existing EvalOps `RunConfig`, `EvaluationResult`, `compare_metrics`, public compatibility field conventions, Phase 6.2 local artifacts/jobs, FastAPI REST, React/Vite/TypeScript/Zod, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-06-phase-6-interactive-evaluation-workspace-design.md`

## Global Constraints

- Begin from the accepted Phase 6.2 merge in a fresh isolated worktree on current `origin/main`.
- A metric delta is never equivalent to a valid regression claim. Compatibility is evaluated and displayed first.
- Canonical comparison fails closed. Do not silently ignore dataset/config/provenance differences.
- Align local population compatibility with the fields already protected by `src/evalops/export/compatibility.py`: dataset name/version/revision, evaluation type, benchmark, language, split, top-k, evaluator versions. Add local-only evidence checks for run schema and ground-truth content hash.
- Prediction hashes are expected to differ between baseline/candidate and therefore are **not** a compatibility mismatch by themselves.
- Existing `compare_metrics()` is authoritative for metric regression decisions. Do not reimplement PASS/REGRESSION/MISSING logic in Workspace or TypeScript.
- The Workspace retrieval regression policy is versioned and fixed in code for this MVP; there is no UI threshold editor.
- Exploratory comparison is a distinct immutable mode, not a warning that can be dismissed. `EXPLORATORY_ONLY` comparisons are permanently ineligible for Phase 6.4 public regression export.
- Historical comparison artifacts never change when the pinned workspace baseline changes.
- Local Failure Explorer may read private local result details, but it must not add arbitrary query languages, scripts, or public publishing.
- Keep all Phase 6.1/6.2 security, job, immutability, no-network, and public Evidence Console regression gates.

## Target File Structure

```text
src/evalops/workspace/
├─ comparison/
│  ├─ __init__.py
│  ├─ models.py                    # compatibility/comparison/failure-transition contracts
│  ├─ compatibility.py             # fail-closed operand checks
│  ├─ policy.py                    # workspace-retrieval-regression-v1 rules
│  └─ failures.py                  # per-query transition derivation
├─ application/
│  ├─ runs.py
│  └─ comparisons.py               # baseline + comparison use-cases
├─ api/
│  ├─ models.py
│  └─ routes_comparisons.py
├─ models.py                       # workspace-state/baseline pointer additions
└─ storage.py                      # workspace state/comparison persistence

tests/workspace/
├─ test_baseline.py
├─ test_comparison_compatibility.py
├─ test_comparison_policy.py
├─ test_comparisons.py
├─ test_failure_transitions.py
└─ test_api_comparisons.py

apps/workspace/src/
├─ api/
│  ├─ schemas.ts
│  └─ client.ts
├─ components/
│  ├─ baseline-card.tsx
│  ├─ compatibility-panel.tsx
│  ├─ comparison-metrics-table.tsx
│  ├─ exploratory-warning.tsx
│  ├─ failure-filter-bar.tsx
│  └─ failure-transition-table.tsx
└─ pages/
   ├─ comparisons-page.tsx
   ├─ comparison-detail-page.tsx
   └─ failures-page.tsx

apps/workspace/tests/
├─ comparison-happy-path.spec.ts
└─ comparison-incompatible.spec.ts
```

## Task 1: Persist an explicit immutable baseline pointer

**Files:**
- Modify: `src/evalops/workspace/models.py`
- Modify: `src/evalops/workspace/storage.py`
- Create: `src/evalops/workspace/application/comparisons.py`
- Create: `tests/workspace/test_baseline.py`

**Interfaces:**

```python
class BaselinePointer(BaseModel):
    run_id: str
    result_sha256: str
    pinned_at: datetime


class WorkspaceState(BaseModel):
    schema_version: Literal["workspace-state-v1"]
    baseline: BaselinePointer | None = None


class ComparisonService:
    def set_baseline(self, workspace_id: str, run_id: str) -> WorkspaceState: ...
    def get_baseline(self, workspace_id: str) -> BaselinePointer | None: ...
```

- [ ] Write failing tests for no baseline, set baseline from a COMPLETE run, reject non-COMPLETE/FAILED/CANCELLED/INTERRUPTED jobs, reject missing result/provenance, reject cross-workspace run, preserve `run_id + result_sha256`, and replace the pointer without changing any historical run/comparison file.
- [ ] Write a test that tampers with `result.json` after completion and proves baseline pinning rejects the run when the current result hash does not match recorded provenance.
- [ ] Run `pytest tests/workspace/test_baseline.py -q` and confirm failure.
- [ ] Implement `workspace-state.json` with schema version and atomic replacement. Do not store baseline fields in mutable run artifacts.
- [ ] Resolve a baseline only from the run's recorded `provenance.result_sha256`; verify current file hash before pinning.
- [ ] Keep prior state readable when there is no baseline.
- [ ] Run tests/Ruff/mypy until green.
- [ ] Commit: `feat(workspace): add explicit pinned retrieval baseline`.

## Task 2: Implement fail-closed comparison compatibility with explicit reasons

**Files:**
- Create: `src/evalops/workspace/comparison/__init__.py`
- Create: `src/evalops/workspace/comparison/models.py`
- Create: `src/evalops/workspace/comparison/compatibility.py`
- Create: `tests/workspace/test_comparison_compatibility.py`

**Interfaces:**

```python
class ComparisonCompatibilityStatus(StrEnum):
    COMPARABLE = "COMPARABLE"
    NON_COMPARABLE = "NON_COMPARABLE"


class CompatibilityReason(BaseModel):
    field: str
    baseline: str
    candidate: str


class ComparisonCompatibility(BaseModel):
    status: ComparisonCompatibilityStatus
    reasons: list[CompatibilityReason]


def assess_local_retrieval_compatibility(
    baseline_snapshot: RunSnapshot,
    baseline_result: EvaluationResult,
    candidate_snapshot: RunSnapshot,
    candidate_result: EvaluationResult,
) -> ComparisonCompatibility: ...
```

- [ ] Write failing table-driven tests for each incompatible dimension: evaluation type, dataset name, dataset version, dataset revision, benchmark, language, split, top-k, evaluator versions, run schema version, and ground-truth content hash.
- [ ] Write passing tests proving different predictions input IDs/hashes, system names, run IDs, timestamps, and result hashes do not by themselves make two runs non-comparable.
- [ ] Assert reasons are stable, sorted by field, and sanitized for API display (no local source paths).
- [ ] Run `pytest tests/workspace/test_comparison_compatibility.py -q` and confirm failure.
- [ ] Implement the population-field check with the same conceptual field set as `evalops.export.compatibility.POPULATION_FIELDS`; do not import public artifacts as the local source of truth.
- [ ] Add the local ground-truth hash requirement so two runs labeled with the same dataset version but evaluated against different local ground truth fail closed.
- [ ] Keep prediction changes intentionally allowed because the candidate system is the object under test.
- [ ] Run tests/Ruff/mypy until green.
- [ ] Commit: `feat(workspace): fail closed on incompatible retrieval runs`.

## Task 3: Define the versioned canonical Workspace retrieval regression policy

**Files:**
- Create: `src/evalops/workspace/comparison/policy.py`
- Create: `tests/workspace/test_comparison_policy.py`

**Interfaces:**

```python
WORKSPACE_RETRIEVAL_POLICY_VERSION = "workspace-retrieval-regression-v1"


def build_workspace_retrieval_rules(k: int) -> list[MetricRule]: ...
```

**Policy V1:** all five current retrieval metrics are higher-is-better and allow no unacknowledged degradation:

```text
precision_at_<k>   HIGHER_IS_BETTER   max_degradation=0.0
recall_at_<k>      HIGHER_IS_BETTER   max_degradation=0.0
hit_rate_at_<k>    HIGHER_IS_BETTER   max_degradation=0.0
mrr                HIGHER_IS_BETTER   max_degradation=0.0
ndcg_at_<k>        HIGHER_IS_BETTER   max_degradation=0.0
```

- [ ] Write failing tests asserting the exact metric names/order/directions/max-degradation and policy version.
- [ ] Add tests proving missing metrics fail closed via existing `compare_metrics()` and any numerical degradation produces `REGRESSION` under V1 while equal/improved values pass.
- [ ] Run `pytest tests/workspace/test_comparison_policy.py -q` and confirm failure.
- [ ] Implement only a rule builder. Do not copy `_compare_one()` or regression-status logic.
- [ ] Keep this policy read-only in Phase 6 UI. A future threshold/policy editor requires a new design/version.
- [ ] Run focused tests until green.
- [ ] Commit: `feat(workspace): define retrieval regression policy v1`.

## Task 4: Persist canonical and exploratory comparison artifacts

**Files:**
- Modify: `src/evalops/workspace/comparison/models.py`
- Modify: `src/evalops/workspace/application/comparisons.py`
- Modify: `src/evalops/workspace/storage.py`
- Create: `tests/workspace/test_comparisons.py`

**Interfaces:**

```python
class ComparisonMode(StrEnum):
    CANONICAL = "CANONICAL"
    EXPLORATORY_ONLY = "EXPLORATORY_ONLY"


class ComparisonRecord(BaseModel):
    schema_version: Literal["workspace-comparison-v1"]
    comparison_id: str
    workspace_id: str
    mode: ComparisonMode
    compatibility: ComparisonCompatibility
    baseline_run_id: str
    baseline_result_sha256: str
    candidate_run_id: str
    candidate_result_sha256: str
    policy_version: str
    regression_report: RegressionReport
    created_at: datetime


class ComparisonService:
    def create_comparison(
        self,
        workspace_id: str,
        candidate_run_id: str,
        *,
        mode: ComparisonMode,
    ) -> ComparisonRecord: ...
```

- [ ] Write failing tests for canonical comparable comparison, no pinned baseline, baseline=candidate rejection, stale/tampered operand hash, cross-workspace candidate, NON_COMPARABLE canonical block, explicit exploratory success for incompatible operands, immutable mode, stable operand snapshots, and old comparisons remaining unchanged after baseline pointer changes.
- [ ] Assert canonical comparison calls `compare_metrics(candidate.metrics, baseline.metrics, build_workspace_retrieval_rules(k))` exactly once.
- [ ] Assert exploratory comparisons may still calculate/report deltas using the same rules for inspection but are permanently labeled `EXPLORATORY_ONLY`; compatibility reasons remain attached.
- [ ] Run `pytest tests/workspace/test_comparisons.py -q` and confirm failure.
- [ ] Persist under `<workspace>/comparisons/<comparison_id>/config.json` and `result.json` using atomic writes. Generate opaque `comparison-<uuid4hex>` IDs.
- [ ] Snapshot current baseline/candidate result hashes and policy version into the record.
- [ ] Never mutate an existing comparison to change mode or operands.
- [ ] Run focused tests and full Workspace Python suite until green.
- [ ] Commit: `feat(workspace): add immutable retrieval comparisons`.

## Task 5: Derive private per-query failure transitions without changing evaluator semantics

**Files:**
- Create: `src/evalops/workspace/comparison/failures.py`
- Modify: `src/evalops/workspace/comparison/models.py`
- Modify: `src/evalops/workspace/application/comparisons.py`
- Create: `tests/workspace/test_failure_transitions.py`

**Interfaces:**

```python
class FailureTransition(StrEnum):
    UNCHANGED_PASS = "UNCHANGED_PASS"
    REGRESSED = "REGRESSED"
    IMPROVED = "IMPROVED"
    PERSISTENT_FAILURE = "PERSISTENT_FAILURE"
    CHANGED_FAILURE = "CHANGED_FAILURE"


class QueryFailureTransition(BaseModel):
    query_id: str
    transition: FailureTransition
    baseline_category: str
    candidate_category: str
    baseline_metrics: dict[str, float]
    candidate_metrics: dict[str, float]


def build_failure_transitions(
    baseline: EvaluationResult,
    candidate: EvaluationResult,
) -> list[QueryFailureTransition]: ...
```

- [ ] Write failing tests for pass→pass, pass→failure, failure→pass, same failure→same failure, one failure category→different failure category, stable query ordering, and missing per-query evidence.
- [ ] Define behavior for a query absent from a per-query result: treat absent data as an explicit internal validation error because compatible retrieval runs should share ground-truth query population; do not synthesize a PASS/failure category.
- [ ] Run `pytest tests/workspace/test_failure_transitions.py -q` and confirm failure.
- [ ] Derive transitions only from `EvaluationResult.details["per_query"]` categories/metrics already produced by the evaluator. Do not calculate retrieval metrics again.
- [ ] Persist transitions as part of comparison-local `result.json` or a deterministic `failures.json` referenced from it; choose one representation and test its schema/version explicitly. Prefer a separate `failures.json` if it keeps `ComparisonRecord` focused.
- [ ] Do not add raw prompts/corpus content/local paths to transition records.
- [ ] Run tests/Ruff/mypy until green.
- [ ] Commit: `feat(workspace): add local retrieval failure transitions`.

## Task 6: Expose baseline/comparison/failure APIs with fail-closed status codes

**Files:**
- Create: `src/evalops/workspace/api/routes_comparisons.py`
- Modify: `src/evalops/workspace/api/models.py`
- Modify: `src/evalops/workspace/api/app.py`
- Create: `tests/workspace/test_api_comparisons.py`
- Regenerate: `apps/workspace/openapi.json`

**API additions:**

```text
GET  /api/v1/workspaces/{workspace_id}/baseline
PUT  /api/v1/workspaces/{workspace_id}/baseline
GET  /api/v1/workspaces/{workspace_id}/comparisons
POST /api/v1/workspaces/{workspace_id}/comparisons
GET  /api/v1/workspaces/{workspace_id}/comparisons/{comparison_id}
GET  /api/v1/workspaces/{workspace_id}/comparisons/{comparison_id}/failures
```

- [ ] Write failing API tests for pin baseline, replace baseline confirmation payload, canonical comparable creation, canonical incompatible 409 with structured compatibility reasons, explicit exploratory creation, missing baseline, invalid/unfinished candidate, cross-workspace IDs, and session/origin enforcement.
- [ ] Ensure API does not accept arbitrary `MetricRule`, threshold, policy version, baseline hash, or compatibility status from the browser. Those are server-derived.
- [ ] `POST comparisons` accepts only candidate run ID plus explicit mode. `CANONICAL` on incompatible inputs returns a safe blocking response; it must not create a comparison directory.
- [ ] Failure API supports server-side filters only from an allowlisted typed set: transition, failure category, query ID substring/exact match as designed. No arbitrary expression/query language.
- [ ] Regenerate/check OpenAPI and update Zod schemas only from the returned contract.
- [ ] Run API/security/full Workspace Python tests.
- [ ] Commit: `feat(workspace): expose regression comparison API`.

## Task 7: Build baseline, comparison, and local Failure Explorer UX

**Files:**
- Modify: `apps/workspace/src/api/schemas.ts`
- Modify: `apps/workspace/src/api/client.ts`
- Modify: `apps/workspace/src/routes.tsx`
- Create components/pages listed in Target File Structure
- Add focused component/page tests beside each file

- [ ] Write failing tests for baseline card, set-baseline confirmation, compatibility-first comparison screen, canonical block, exploratory warning, metric table, permanent `EXPLORATORY_ONLY` label, failure filters, and local-evidence identity.
- [ ] On Run Detail, expose `Set as Workspace Baseline` only for a valid COMPLETE run. Confirmation must show current/new baseline and state that existing comparisons do not change.
- [ ] On Comparison creation, default mode is canonical. If API reports incompatibility, show reasons before any metric delta and present a separate explicit `Create Exploratory Comparison` action.
- [ ] Comparison Detail renders baseline/candidate IDs and hashes (short display with accessible full value), compatibility status, policy version, then metric baseline/candidate/delta/status. Never render a delta without operand context.
- [ ] Exploratory comparison has a persistent warning: `EXPLORATORY_ONLY — Not eligible for public regression claim`.
- [ ] Failure Explorer supports approved filters: transition, category, query ID. Render baseline/candidate categories and metric differences from persisted transition records.
- [ ] Reuse the shared `@evalops/evidence-ui` tokens from Phase 6.1. Do not copy whole Evidence Console pages; keep local/private labels and interactions distinct.
- [ ] Keep `Exports` as future/empty state until Phase 6.4; do not add fake export buttons here.
- [ ] Run Workspace lint/type/unit/build until green.
- [ ] Commit: `feat(workspace): add baseline comparison and failure explorer UI`.

## Task 8: Prove comparable and incompatible flows in real browser E2E

**Files:**
- Create: `apps/workspace/tests/comparison-happy-path.spec.ts`
- Create: `apps/workspace/tests/comparison-incompatible.spec.ts`
- Modify: `scripts/run_workspace_e2e_server.py` only for deterministic test fixtures/gates

- [ ] Happy path: create workspace → run baseline k=10 → set baseline → run candidate k=10 on same GT/dataset → create canonical comparison → assert `COMPARABLE` appears before deltas → inspect regression statuses → open Failure Explorer and filter regressed/improved transitions.
- [ ] Change the workspace baseline after the first comparison and assert the existing comparison detail still references its original baseline run/hash.
- [ ] Incompatible path: baseline k=10 → candidate k=20 → canonical creation blocked with exact `top_k` reason → no comparison persisted → explicitly create exploratory → assert permanent `EXPLORATORY_ONLY` label and compatibility reasons.
- [ ] Add a second incompatibility proof using same dataset labels but modified ground-truth content hash; canonical comparison must fail closed.
- [ ] At 390/768/1280 widths assert comparison tables use scoped overflow/alternate layout without root overflow.
- [ ] Run axe on comparison/failure views and assert no serious/critical violations, target zero total.
- [ ] Assert zero external runtime requests.
- [ ] Commit: `test(workspace): prove comparison compatibility flows`.

## Task 9: Phase 6.3 full acceptance and regression verification

**Files:**
- Review all Phase 6.3 changed files.
- Modify `.github/workflows/workspace-ci.yml` only to include new tests/routes when necessary.

- [ ] Run `ruff check .`, `ruff format --check .`, `mypy src`, full `pytest`.
- [ ] Run direct `compare_metrics()` equivalence tests against the Workspace canonical comparison for deterministic fixtures.
- [ ] Run the existing CLI regression command tests and public export compatibility tests unchanged.
- [ ] Run full `apps/web` lint/type/unit/Storybook/static/Playwright gates.
- [ ] Run full `apps/workspace` lint/type/unit/build/OpenAPI/Playwright/axe gates.
- [ ] Verify public `evalops.export.compatibility` behavior and claim rules have not been weakened or bypassed.
- [ ] Search for duplicate regression algorithms, client-supplied thresholds/policy, silent compatibility bypasses, mutable comparison records, raw local paths in API responses, external fetches, secrets, TODO/FIXME/placeholders.
- [ ] Request code review after fresh green evidence; resolve findings and rerun affected/full gates.

## Phase 6.3 Acceptance Contract

Phase 6.3 is accepted when a completed local retrieval run can be pinned as an immutable workspace baseline, a compatible candidate produces a deterministic canonical regression report through existing `compare_metrics()`, incompatible operands are blocked with explicit reasons, an owner can intentionally create a permanently `EXPLORATORY_ONLY` comparison, historical comparisons survive baseline changes unchanged, and the private Failure Explorer exposes deterministic per-query transitions without reimplementing metrics or crossing the public evidence boundary.
