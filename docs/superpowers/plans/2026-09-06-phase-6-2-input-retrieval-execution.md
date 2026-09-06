# Phase 6.2 Input & Retrieval Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Turn the authenticated Workspace shell into a useful retrieval-evaluation product: import/reference validated retrieval inputs, configure a constrained run, execute through the existing EvalOps runner on a persistent single-worker queue, observe progress over SSE, and inspect immutable metrics/failures/provenance.

**Architecture:** Input adapters normalize JSONL/CSV into the existing Pydantic retrieval contracts. Run creation snapshots input identities/config, persists a job, and enqueues only a job ID. A single worker rehydrates the run from disk and calls `run_retrieval_evaluation()`; no metric formula is copied into Workspace code. Job JSON is the source of truth; SSE observes persisted revisions and is advisory. Completed results/provenance are immutable and written atomically.

**Tech Stack:** Phase 6.1 Workspace foundation, Python/Pydantic, existing `evalops.datasets.io` and `evalops.runners.retrieval`, FastAPI multipart upload + StreamingResponse SSE, React/Vite/TypeScript/Zod, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-06-phase-6-interactive-evaluation-workspace-design.md`

## Global Constraints

- Start from the accepted Phase 6.1 merge in a fresh isolated worktree based on current `origin/main`.
- Preserve Phase 6.1 loopback/session/origin/filesystem boundaries; do not weaken them to simplify uploads or SSE.
- Retrieval metrics remain authoritative in `src/evalops/evaluators/retrieval/metrics.py`; execution must call `run_retrieval_evaluation()`.
- Do not subprocess the CLI from the Workspace. If reusable behavior is trapped in CLI code, extract it into a reusable Python function used by both adapters.
- Supported evaluation scope is retrieval only. No provider calls, vector DB, LLM generation, hallucination/groundedness UI, generic evaluator registry, or arbitrary scripts.
- Supported ingestion is canonical retrieval JSONL plus guided CSV mapping only.
- Persisted local paths are private Workspace metadata; API responses must return only the local fields the UI actually needs. Public export remains Phase 6.4.
- Completed run config/result/provenance files are immutable. Retry creates a new job; changing config creates a new run ID.
- Evaluation cancellation is cooperative. The existing evaluator is one deterministic synchronous phase; cancellation may be honored before evaluation and immediately after evaluation before analysis/artifact promotion rather than altering metric internals.
- Do not add concurrent workers. Queue behavior must remain deterministic with one worker.
- Existing core/public tests and Phase 6.1 security/browser gates remain mandatory on every implementation PR.

## Target File Structure

```text
src/evalops/workspace/
├─ ingestion/
│  ├─ __init__.py
│  ├─ models.py                    # InputManifest / validation contracts
│  ├─ jsonl.py                     # canonical JSONL validation/normalization adapter
│  ├─ csv_adapter.py               # explicit guided CSV mapping adapter
│  └─ service.py                   # register upload/reference + pair validation
├─ jobs/
│  ├─ __init__.py
│  ├─ models.py                    # JobState / JobRecord / safe error / progress
│  └─ queue.py                     # persistent single worker + recovery/cancel
├─ application/
│  ├─ __init__.py
│  └─ runs.py                      # run snapshot, execution, immutable artifact/provenance
├─ api/
│  ├─ app.py                       # lifespan wiring only after route extraction
│  ├─ models.py
│  ├─ routes_inputs.py
│  ├─ routes_runs.py
│  └─ routes_jobs.py
└─ storage.py                      # add input/run/job/result/provenance methods

tests/workspace/
├─ test_ingestion_jsonl.py
├─ test_ingestion_csv.py
├─ test_run_validation.py
├─ test_jobs.py
├─ test_run_execution.py
└─ test_api_retrieval.py

apps/workspace/src/
├─ app.tsx
├─ routes.tsx
├─ api/
│  ├─ schemas.ts
│  └─ client.ts
├─ components/
│  ├─ local-workspace-banner.tsx
│  ├─ input-source-form.tsx
│  ├─ csv-mapping-form.tsx
│  ├─ validation-summary.tsx
│  ├─ run-config-form.tsx
│  ├─ run-review.tsx
│  ├─ job-progress.tsx
│  └─ run-result.tsx
└─ pages/
   ├─ workspace-overview.tsx
   ├─ inputs-page.tsx
   ├─ runs-page.tsx
   └─ run-detail-page.tsx

apps/workspace/tests/
├─ retrieval-happy-path.spec.ts
├─ csv-import.spec.ts
└─ retrieval-failure-paths.spec.ts
```

## Task 1: Define canonical local input manifests and JSONL registration

**Files:**
- Create: `src/evalops/workspace/ingestion/__init__.py`
- Create: `src/evalops/workspace/ingestion/models.py`
- Create: `src/evalops/workspace/ingestion/jsonl.py`
- Create: `src/evalops/workspace/ingestion/service.py`
- Modify: `src/evalops/workspace/storage.py`
- Create: `tests/workspace/test_ingestion_jsonl.py`

**Interfaces:**

```python
class InputKind(StrEnum):
    RETRIEVAL_GROUND_TRUTH = "retrieval_ground_truth"
    RETRIEVAL_PREDICTIONS = "retrieval_predictions"


class InputSourceMode(StrEnum):
    IMPORTED = "imported"
    REFERENCED = "referenced"


class InputManifest(BaseModel):
    schema_version: Literal["workspace-input-v1"]
    input_id: str
    kind: InputKind
    source_mode: InputSourceMode
    canonical_format: Literal["retrieval-jsonl-v1"]
    content_sha256: str  # canonical bytes consumed by the runner
    source_sha256: str  # original source bytes; same as content for canonical JSONL
    record_count: int
    validation_status: Literal["VALID"]
    source_path: str | None  # referenced input only; private metadata
    stored_relative_path: str | None  # imported canonical file only
    source_filename: str | None
    created_at: datetime


class InputRegistrationResult(BaseModel):
    manifest: InputManifest
    summary: InputValidationSummary
```

- [ ] Write failing tests for canonical ground-truth JSONL import, predictions JSONL import, duplicate `query_id`, malformed JSON, Pydantic schema error, empty file, stable SHA-256, imported file location, referenced real-path resolution, symlink resolution, unreadable/non-file path, and unsupported extension/format.
- [ ] Assert duplicate IDs use the existing loader behavior and surface a safe structured issue; do not create a second duplicate-detection implementation with different semantics.
- [ ] Run `pytest tests/workspace/test_ingestion_jsonl.py -q` and confirm failure.
- [ ] Implement canonical JSONL validation by calling `load_retrieval_ground_truth()` or `load_retrieval_predictions()` based on `InputKind`.
- [ ] For browser-imported JSONL, copy canonical UTF-8 bytes into `<workspace>/inputs/imported/<input_id>.jsonl` only after validation succeeds; write manifest to `inputs/manifests/<input_id>.json` atomically.
- [ ] For referenced JSONL, call `Path.resolve(strict=True)`, require a regular readable file, compute the file hash, validate through the existing loader, and persist the resolved path privately in the manifest. Do not copy by default.
- [ ] Use opaque `input-<uuid4hex>` identifiers. Never derive an input ID from a user path or filename.
- [ ] Add `WorkspaceStore.list_inputs/get_input/save_input_manifest` methods that validate workspace ownership before any filesystem access.
- [ ] Keep invalid temporary uploads out of canonical imported storage and clean temp files on failure.
- [ ] Run tests, Ruff, and mypy until green.
- [ ] Commit: `feat(workspace): register validated retrieval JSONL inputs`.

## Task 2: Add guided CSV normalization into canonical retrieval JSONL

**Files:**
- Create: `src/evalops/workspace/ingestion/csv_adapter.py`
- Create: `tests/workspace/test_ingestion_csv.py`
- Modify: `src/evalops/workspace/ingestion/models.py`
- Modify: `src/evalops/workspace/ingestion/service.py`

**Interfaces:**

```python
class CsvMapping(BaseModel):
    query_id_column: str
    document_ids_column: str
    document_ids_delimiter: str = Field(min_length=1, max_length=1)


def normalize_retrieval_csv(
    source: Path,
    *,
    kind: InputKind,
    mapping: CsvMapping,
) -> tuple[bytes, InputValidationSummary]: ...
```

- [ ] Write failing tests for ground-truth mapping (`query_id` + relevant IDs), prediction mapping (`query_id` + retrieved IDs), custom header names, one-character delimiter, whitespace normalization, empty document list, duplicate query IDs, missing mapped column, duplicate CSV headers, malformed quoting, non-UTF-8 input, and forbidden multi-character delimiter.
- [ ] Assert CSV output is deterministic canonical JSONL with one normalized JSON object per query and a terminal newline; the same logical CSV must produce the same canonical hash.
- [ ] Run `pytest tests/workspace/test_ingestion_csv.py -q` and confirm failure.
- [ ] Implement using Python `csv` only; no pandas dependency and no arbitrary transforms/expressions.
- [ ] Normalize a ground-truth row to the existing `RetrievalGroundTruth` model shape and predictions to `RetrievalPrediction`; validate every normalized record with Pydantic before registration.
- [ ] After normalization, run the same canonical JSONL loader used by Task 1 as a second boundary check.
- [ ] Persist only the normalized canonical JSONL in imported storage; keep `source_filename` plus `source_sha256` for provenance. `content_sha256` is the normalized JSONL hash used by evaluation.
- [ ] Add deterministic validation issues that identify CSV row/column without echoing entire raw rows.
- [ ] Run CSV + JSONL ingestion tests until green.
- [ ] Commit: `feat(workspace): add guided retrieval CSV importer`.

## Task 3: Add pair validation and constrained retrieval run snapshots

**Files:**
- Create: `src/evalops/workspace/application/__init__.py`
- Create: `src/evalops/workspace/application/runs.py`
- Modify: `src/evalops/workspace/ingestion/models.py`
- Modify: `src/evalops/workspace/ingestion/service.py`
- Modify: `src/evalops/workspace/storage.py`
- Create: `tests/workspace/test_run_validation.py`

**Interfaces:**

```python
class RetrievalPairValidation(BaseModel):
    ground_truth_records: int
    prediction_records: int
    matching_query_count: int
    missing_prediction_query_ids: list[str]
    extra_prediction_query_ids: list[str]
    blocking_issues: list[ValidationIssue]
    warnings: list[ValidationIssue]


class CreateRetrievalRun(BaseModel):
    run_name: str
    ground_truth_input_id: str
    predictions_input_id: str
    top_k: int = Field(ge=1)
    system_name: str
    dataset_name: str
    dataset_version: str


class RunSnapshot(BaseModel):
    schema_version: Literal["workspace-run-v1"]
    run_id: str
    workspace_id: str
    run_name: str
    ground_truth_input_id: str
    ground_truth_content_sha256: str
    predictions_input_id: str
    predictions_content_sha256: str
    config: RunConfig
    created_at: datetime
```

- [ ] Write failing tests for correct overlap summary, missing prediction queries as non-blocking warning (existing evaluator treats missing predictions as empty rankings), extra prediction queries as warning, wrong input kinds as blocking, cross-workspace input IDs as blocking, invalid `top_k`, empty labels, and deterministic `RunConfig` evaluator version `{"retrieval": "deterministic-v1"}`.
- [ ] Write a failing test proving a run snapshot captures hashes at creation and cannot be updated in place through `WorkspaceStore` after execution starts.
- [ ] Run `pytest tests/workspace/test_run_validation.py -q` and confirm failure.
- [ ] Implement pair validation by loading canonical input data and comparing query-ID sets; do not reinterpret metric behavior.
- [ ] Create opaque `run-<uuid4hex>` IDs and construct the existing `RunConfig` with dataset/system/top-k metadata plus current EvalOps/git metadata when available.
- [ ] Persist `<workspace>/runs/<run_id>/config.json` atomically before job enqueue. The file is a snapshot, not a mutable draft after enqueue.
- [ ] Do not expose evaluator version editing in API models.
- [ ] Run tests/Ruff/mypy until green.
- [ ] Commit: `feat(workspace): snapshot constrained retrieval runs`.

## Task 4: Implement the persistent single-worker job state machine

**Files:**
- Create: `src/evalops/workspace/jobs/__init__.py`
- Create: `src/evalops/workspace/jobs/models.py`
- Create: `src/evalops/workspace/jobs/queue.py`
- Modify: `src/evalops/workspace/storage.py`
- Create: `tests/workspace/test_jobs.py`

**Interfaces:**

```python
class JobState(StrEnum):
    QUEUED = "QUEUED"
    VALIDATING = "VALIDATING"
    EVALUATING = "EVALUATING"
    ANALYZING = "ANALYZING"
    WRITING_ARTIFACT = "WRITING_ARTIFACT"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    INTERRUPTED = "INTERRUPTED"


class JobRecord(BaseModel):
    schema_version: Literal["workspace-job-v1"]
    job_id: str
    workspace_id: str
    run_id: str
    state: JobState
    revision: int
    cancel_requested: bool
    safe_error: SafeJobError | None
    created_at: datetime
    updated_at: datetime


class SingleWorkerQueue:
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def enqueue(self, job: JobRecord) -> None: ...
    def request_cancel(self, job_id: str) -> JobRecord: ...
    def recover(self) -> None: ...
```

- [ ] Write failing tests for exact allowed transitions, rejection of invalid transitions, deterministic revision increments, one-at-a-time execution, queued cancel, running cancel request, terminal-state idempotence, safe error persistence, restart recovery (`QUEUED` re-enqueued; transient states → `INTERRUPTED`; terminal states unchanged), and worker shutdown.
- [ ] Write a failing test proving a cancelled job left in the in-memory queue is skipped when dequeued rather than executed.
- [ ] Use synchronization primitives/events in tests; no sleeps as the primary correctness assertion.
- [ ] Run `pytest tests/workspace/test_jobs.py -q` and confirm failure.
- [ ] Implement queue storage around persisted `job.json` records; the in-memory queue stores only `(workspace_id, job_id)` references.
- [ ] Ensure every state mutation reads/validates the current persisted record and atomically replaces it.
- [ ] Implement recovery by scanning registered workspaces/runs, validating job schema versions, and applying the approved restart rules before the worker starts consuming.
- [ ] Do not implement mid-step computation resume.
- [ ] Run tests under repeated execution to catch ordering/race errors.
- [ ] Commit: `feat(workspace): add persistent single-worker jobs`.

## Task 5: Execute jobs through the existing retrieval runner and persist immutable provenance

**Files:**
- Modify: `src/evalops/workspace/application/runs.py`
- Modify: `src/evalops/workspace/jobs/queue.py`
- Modify: `src/evalops/workspace/storage.py`
- Create: `tests/workspace/test_run_execution.py`

**Interfaces:**

```python
class RunProvenance(BaseModel):
    schema_version: Literal["workspace-provenance-v1"]
    run_id: str
    ground_truth_input_id: str
    ground_truth_content_sha256: str
    predictions_input_id: str
    predictions_content_sha256: str
    evaluator_versions: dict[str, str]
    evalops_version: str
    git_commit: str | None
    completed_at: datetime
    result_sha256: str


class RetrievalRunService:
    def create_and_enqueue(self, workspace_id: str, request: CreateRetrievalRun) -> JobRecord: ...
    def execute_job(self, workspace_id: str, job_id: str) -> None: ...
    def retry_job(self, workspace_id: str, job_id: str) -> JobRecord: ...
```

- [ ] Write failing tests for the complete state sequence, exact call to `run_retrieval_evaluation()`, expected macro metrics from a deterministic fixture, persisted per-query failures, referenced-input hash mutation before evaluation, cancellation before evaluator call, cancellation after evaluator call but before artifact promotion, atomic result/provenance writes, result hash, immutable COMPLETE artifacts, evaluator exception → safe FAILED, and retry → new job identity.
- [ ] Add a regression assertion that the Workspace result equals direct `run_retrieval_evaluation()` for the same canonical inputs/config.
- [ ] Run `pytest tests/workspace/test_run_execution.py -q` and confirm failure.
- [ ] At `VALIDATING`, re-hash referenced inputs and compare to the run snapshot. If changed, fail with safe code `INPUT_HASH_CHANGED` before calling the evaluator.
- [ ] Transition to `EVALUATING`, call the existing loaders and `run_retrieval_evaluation()` once, then check `cancel_requested` at the next deterministic safe boundary.
- [ ] Use `ANALYZING` only for Workspace-level safe summaries/provenance preparation; do not recompute metric formulas.
- [ ] During `WRITING_ARTIFACT`, serialize `EvaluationResult.model_dump(mode="json")` to a temp file, hash canonical serialized bytes, atomically replace `result.json`, then atomically write `provenance.json`; only then set job `COMPLETE`.
- [ ] Prevent any subsequent API/store method from overwriting completed config/result/provenance paths.
- [ ] Implement retry from persisted snapshot/provenance references with a new `job-<uuid4hex>`; do not rewrite prior job history.
- [ ] Run full Workspace Python suite until green.
- [ ] Commit: `feat(workspace): execute immutable retrieval evaluation jobs`.

## Task 6: Expose input/run/job APIs and SSE from persisted state

**Files:**
- Create: `src/evalops/workspace/api/routes_inputs.py`
- Create: `src/evalops/workspace/api/routes_runs.py`
- Create: `src/evalops/workspace/api/routes_jobs.py`
- Modify: `src/evalops/workspace/api/models.py`
- Modify: `src/evalops/workspace/api/app.py`
- Create: `tests/workspace/test_api_retrieval.py`
- Modify: `scripts/export_workspace_openapi.py`
- Regenerate: `apps/workspace/openapi.json`

**API additions:**

```text
GET   /api/v1/workspaces/{workspace_id}/inputs
POST  /api/v1/workspaces/{workspace_id}/inputs/upload
POST  /api/v1/workspaces/{workspace_id}/inputs/reference
POST  /api/v1/workspaces/{workspace_id}/inputs/csv
GET   /api/v1/workspaces/{workspace_id}/inputs/{input_id}
POST  /api/v1/workspaces/{workspace_id}/runs/validate
GET   /api/v1/workspaces/{workspace_id}/runs
POST  /api/v1/workspaces/{workspace_id}/runs
GET   /api/v1/workspaces/{workspace_id}/runs/{run_id}
GET   /api/v1/jobs/{job_id}
POST  /api/v1/jobs/{job_id}/cancel
POST  /api/v1/jobs/{job_id}/retry
GET   /api/v1/jobs/{job_id}/events
```

- [ ] Write failing API tests for multipart upload, explicit path reference, CSV mapping, validation summaries, run enqueue, list/get, cancel/retry, cross-workspace ID rejection, input mutation error, session/origin enforcement, and safe error bodies.
- [ ] Write SSE tests that assert event `id` equals persisted `revision`, state comes from current job JSON, reconnect with `Last-Event-ID` returns the latest newer state, and terminal events close the stream cleanly.
- [ ] Assert SSE never contains raw input records, local paths, bootstrap/session values, or full `EvaluationResult.details` payloads.
- [ ] Refactor `api/app.py` only enough to register focused route modules and application services; keep security middleware centralized.
- [ ] Implement SSE by observing persisted job revisions at a bounded interval/event notification. SSE is not an event store and missed intermediate events must not affect correctness.
- [ ] Regenerate `apps/workspace/openapi.json` and run `python scripts/export_workspace_openapi.py --check`.
- [ ] Run API/security tests until green.
- [ ] Commit: `feat(workspace): expose retrieval jobs over REST and SSE`.

## Task 7: Build the retrieval-first Workspace UX

**Files:**
- Modify: `apps/workspace/package.json`
- Modify: `apps/workspace/package-lock.json`
- Create: `apps/workspace/src/routes.tsx`
- Modify: `apps/workspace/src/app.tsx`
- Modify: `apps/workspace/src/api/schemas.ts`
- Modify: `apps/workspace/src/api/client.ts`
- Create all components/pages listed in Target File Structure
- Add focused `*.test.tsx` files beside components/pages

- [ ] Add `react-router-dom>=7,<8` and commit the resolved lockfile; configure SPA routes so reloads are handled by the FastAPI static fallback.
- [ ] Write failing component tests before each screen: input source choice; CSV mapping; validation summary; constrained run config; review screen; progress states; failed/interrupted/cancelled messaging; run result summary/failure/provenance/local-evidence status.
- [ ] Build navigation for `Overview`, `Inputs`, `Runs`, `Comparisons`, `Failures`, `Exports`, but keep future sections visibly unavailable/empty rather than fake-functional. Phase 6.2 implements Overview/Inputs/Runs only.
- [ ] Input UI supports upload and explicit local path entry. It must not implement filesystem listing/browsing.
- [ ] CSV UI requests only query-ID column, document-ID column, and one-character delimiter based on selected input kind.
- [ ] Validation UI shows record/unique counts, duplicates/missing issues, hashes, and pair overlap/missing/extra prediction counts. Blocking errors visually and semantically differ from warnings.
- [ ] Run configuration exposes only run name, selected GT/prediction inputs, top-k, system label, dataset name/version. Render evaluator version/metric contract read-only.
- [ ] Review screen shows input hashes and validation evidence before `Run Evaluation`.
- [ ] Job page uses SSE for freshness but always fetches current persisted state on initial load/reconnect. Reloading must reconstruct the correct page from REST.
- [ ] Run result renders macro metrics using actual keys (`precision_at_<k>`, `recall_at_<k>`, `hit_rate_at_<k>`, `mrr`, `ndcg_at_<k>`), failure categories from persisted per-query result, provenance hashes, and persistent `LOCAL EVIDENCE — Not published` status.
- [ ] Do not label a local run as `VERIFIED`, benchmark result, or public evidence merely because the job completed.
- [ ] Run Workspace lint/type/unit/build after each page group.
- [ ] Commit: `feat(workspace): add guided retrieval evaluation flow`.

## Task 8: Prove happy path, CSV path, mutation failure, cancellation, and restart recovery in browser

**Files:**
- Create: `apps/workspace/tests/retrieval-happy-path.spec.ts`
- Create: `apps/workspace/tests/csv-import.spec.ts`
- Create: `apps/workspace/tests/retrieval-failure-paths.spec.ts`
- Modify: `scripts/run_workspace_e2e_server.py`
- Modify: `apps/workspace/playwright.config.ts`

- [ ] Extend the E2E server harness with deterministic synthetic retrieval fixture paths and a test-owned root only; never rely on user-local files.
- [ ] Happy path: authenticate → create workspace → upload GT JSONL → upload predictions JSONL → validate → configure k → review hashes → run → observe state progression → COMPLETE → inspect actual metrics/failures/provenance → reload and confirm same result.
- [ ] CSV path: import ground truth/predictions through explicit mappings → validate normalized hashes → run → assert result equals equivalent JSONL flow.
- [ ] Mutation path: register referenced predictions → validate → mutate source file in test temp dir → run → assert `INPUT_HASH_CHANGED`, no canonical result artifact, and safe UI remediation.
- [ ] Cancellation path: enqueue a job with a deterministic test gate around execution → request cancel → assert approved terminal state and no partial canonical artifact.
- [ ] Restart path: persist a job in a transient state via test harness → restart server → assert `INTERRUPTED` → Retry → new job ID → successful completion.
- [ ] At 390px, 768px, and 1280px viewports assert no root horizontal overflow in Input, Run Review, Job, and Run Result canonical screens.
- [ ] Run axe on canonical screens and fail on serious/critical violations; target zero total violations.
- [ ] Assert all browser requests remain same-origin loopback; no external network requests.
- [ ] Commit: `test(workspace): cover retrieval execution lifecycle`.

## Task 9: Expand Workspace CI and run Phase 6.2 acceptance

**Files:**
- Modify: `.github/workflows/workspace-ci.yml`
- Review all Phase 6.2 changes.

- [ ] Ensure Workspace CI installs `.[dev,workspace]`, runs the full Workspace Python/API test set, verifies OpenAPI freshness, builds the Vite app, and runs Playwright retrieval E2E.
- [ ] Keep the new `workspace` context non-required until a real PR proves stability; do not alter governance in this implementation slice.
- [ ] Run `ruff check .`, `ruff format --check .`, `mypy src`, and full `pytest`.
- [ ] Run existing CLI retrieval evaluation against repository fixtures and compare its result with the Workspace runner path where inputs/config are equivalent.
- [ ] Run full `apps/web` lint/type/unit/Storybook/static/Playwright gates unchanged.
- [ ] Run full `apps/workspace` lint/type/unit/build/OpenAPI/Playwright/axe gates.
- [ ] Verify clean process restart behavior with a test-owned Workspace root.
- [ ] Search for secrets, raw private records in API/SSE fixtures, absolute developer-machine paths, `0.0.0.0`, external fetches, TODO/FIXME/placeholders, duplicated metric formulas, and any Workspace subprocess invocation of `evalops retrieval`.
- [ ] Request code review after fresh green evidence; resolve findings and rerun affected/full gates.

## Phase 6.2 Acceptance Contract

Phase 6.2 is accepted when a user can locally create/open a workspace, import or reference canonical JSONL (or guided CSV), inspect validation evidence, configure only approved retrieval fields, execute through the existing deterministic retrieval runner on a recoverable single-worker queue, cancel/retry safely, observe job state via REST/SSE, and inspect immutable local metrics/failures/provenance after reload/restart. No comparison, baseline, public-evidence promotion, provider execution, or cloud behavior is part of this slice.
