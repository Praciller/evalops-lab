# Phase 6: Interactive Evaluation Workspace Design

Date: 2026-09-06
Repository: `Praciller/evalops-lab`
Status: Conversational design approved; canonical spec awaiting owner review before implementation planning

## 1. Goal

Phase 6 adds a **local-first interactive evaluation workspace** to EvalOps Lab without weakening the trust boundary of the existing public Evidence Console.

The phase enables a user to:

```text
add local retrieval evidence
        ↓
validate inputs
        ↓
configure a constrained retrieval evaluation
        ↓
execute locally
        ↓
inspect metrics and failures
        ↓
compare against an explicit baseline
        ↓
export sanitized public evidence explicitly
```

The existing Python evaluation core remains authoritative. The Workspace is an orchestration and interaction layer, not a second implementation of metric, failure, or regression semantics.

The public Evidence Console remains static, read-only, sanitized, and independently deployable on GitHub Pages.

## 2. Product principle

Phase 6 extends the repository's established principle:

> Evidence over decoration.

The Local Workspace creates and investigates private evaluation evidence. The Public Evidence Console presents only explicitly sanitized evidence. The existing Python evaluation core remains authoritative for both.

## 3. Approved architecture

The approved approach is **Layered Local Workspace**.

```text
                         PUBLIC
              ┌─────────────────────────┐
              │ Evidence Console        │
              │ apps/web                │
              │ static GitHub Pages     │
              │ sanitized / read-only   │
              └────────────▲────────────┘
                           │
                   explicit promotion
                           │
                   sanitized artifact
                           │
LOCAL                      │
┌──────────────────────────┴─────────────────────────┐
│ apps/workspace — Vite + React                     │
│                                                   │
│ REST /api/v1 + SSE                                │
│              │                                    │
│              ▼                                    │
│ evalops.workspace — FastAPI                       │
│ ├─ security      loopback + session               │
│ ├─ ingestion     JSONL + guided CSV               │
│ ├─ application   orchestration                    │
│ ├─ jobs          persistent single-worker queue   │
│ └─ storage       immutable local evidence         │
│              │                                    │
│       ┌──────┴────────┐                           │
│       ▼               ▼                           │
│ existing runners   existing export policy         │
│ /evaluators        /serialization                 │
└───────────────────────────────────────────────────┘
```

The Workspace application layer orchestrates; it does not evaluate.

## 4. Authoritative scope boundaries

Phase 6 may add or change:

- `apps/workspace` as a Vite + React local SPA
- optional Python workspace dependencies
- `evalops workspace` CLI startup behavior
- a loopback-only FastAPI server
- versioned local REST/SSE contracts
- local workspace registry and file-backed storage
- local input ingestion and validation
- a persistent single-worker evaluation queue
- retrieval run orchestration through existing runners
- pinned-baseline comparison orchestration
- local failure exploration
- explicit public-evidence preview/export workflows
- packaging of the prebuilt Workspace frontend into the Python distribution
- Workspace-specific CI, browser E2E, accessibility, package, and security verification
- narrowly extracted shared frontend primitives when reuse is proven

Phase 6 must not introduce:

- a hosted Workspace or cloud SaaS
- accounts, teams, collaboration, or authentication over the network
- LAN exposure or `0.0.0.0` server mode
- provider API calls, LLM inference, vector databases, or retrieval-generation pipelines
- arbitrary filesystem browsing
- arbitrary Python, SQL, or script execution
- concurrent/distributed workers
- automatic publishing or committing into the public Evidence Console
- a generic evaluator plugin framework
- silent changes to existing metric, regression, failure, or public-evidence semantics
- a requirement for Node.js at end-user runtime
- remote telemetry, analytics, or crash uploads

## 5. Runtime model

The approved runtime model is **local-first**.

Production-local usage is one command and one local Python process:

```text
evalops workspace
        ↓
127.0.0.1:<port>
        ↓
Python workspace server
   ├─ /api/v1/*
   ├─ /api/v1/jobs/<id>/events
   └─ prebuilt apps/workspace static UI
```

Node.js is a development and build dependency only.

The canonical Phase 6 workflow requires no outbound runtime network requests.

## 6. Frontend architecture

`apps/workspace` is a **Vite + React SPA** separate from `apps/web`.

Reasons:

- no SSR or hosted runtime is required
- the SPA can be packaged as deterministic static assets
- the Workspace can use REST/SSE directly
- the public static app remains isolated from privileged local capabilities
- Vite/Vitest already fit the repository's frontend ecosystem

Shared code follows **extract-on-demand**. Stable visual primitives may move to a shared package, but application behavior must not be generalized merely to maximize reuse.

Share examples:

- tokens
- typography
- spacing primitives
- status badges
- metric presentation
- accessible table primitives

Do not share a public page or Workspace use-case as a generic abstraction unless a real second use case exists.

## 7. Python dependency model

Workspace server dependencies are an optional extra, conceptually:

```toml
[project.optional-dependencies]
workspace = [
    "fastapi...",
    "uvicorn...",
]
```

Core evaluation installations remain lightweight.

If the user runs `evalops workspace` without the optional dependencies, the CLI must return an actionable message rather than an import traceback.

Example intent:

```text
EvalOps Workspace dependencies are not installed.

Install with:
pip install "evalops-lab[workspace]"
```

Core CLI commands must not import FastAPI/Uvicorn eagerly.

## 8. Trust boundaries and invariants

### 8.1 Python core remains authoritative

Workspace code must not reimplement retrieval metric formulas, failure classification, regression semantics, or public-evidence claim policy.

Retrieval execution routes through the existing reusable runner and evaluator implementation.

### 8.2 Public Evidence Console remains static

`apps/web` must remain:

- public
- static-exported
- read-only
- sanitized
- unprivileged

Phase 6 must not add API routes, server actions, local filesystem access, evaluation execution, provider calls, auth, persistence, or local runtime assumptions to `apps/web`.

### 8.3 Browser is not trusted

Authentication, workspace ownership, path controls, origin checks, job state transitions, public-export eligibility, and filesystem writes are enforced on the Python side.

### 8.4 Private-to-public is explicit and one-way

Local artifacts never become public artifacts implicitly.

The flow is:

```text
local artifact
  ↓
existing export policy/adapters
  ↓
sanitized preview
  ↓
validation / eligibility
  ↓
explicit owner confirmation
  ↓
chosen output destination
```

The default destination must not be `apps/web/public/evidence` or another repository publication directory.

## 9. Workspace identity and storage

The approved model is a **multi-workspace manager**.

One server process can manage multiple independent local workspaces.

Default conceptual root:

```text
~/.evalops/
├─ registry.json
└─ workspaces/
   └─ <workspace-id>/
      ├─ workspace.json
      ├─ inputs/
      │  ├─ manifests/
      │  └─ imported/
      ├─ runs/
      │  └─ <run-id>/
      │     ├─ config.json
      │     ├─ job.json
      │     ├─ result.json
      │     └─ provenance.json
      ├─ comparisons/
      │  └─ <comparison-id>/
      │     ├─ config.json
      │     └─ result.json
      ├─ exports/
      │  └─ manifests/
      └─ workspace-state.json
```

The exact filenames may be refined during implementation planning, but these ownership boundaries are normative.

`workspace_id` is the stable identity. A directory or display-name change must not alter historical evidence identity.

Every persisted manifest/state contract includes an explicit `schema_version`.

Unknown future versions are rejected with an actionable error rather than silently reinterpreted.

## 10. Storage model

Phase 6 uses **file-backed storage** rather than a database.

Rationale:

- the worker model is single-threaded for evaluation mutation
- primary data already consists of manifests and immutable artifacts
- file-backed state is transparent and inspectable
- SQLite would add migration and locking complexity without a proven MVP requirement

Critical state writes use crash-safe behavior conceptually equivalent to:

```text
validate
→ write temporary file
→ flush/close
→ atomic replace
```

No completed canonical artifact may be considered valid if only a partial file exists.

## 11. Input model

The approved ingestion model is **hybrid local import**:

1. browser upload/file-picker; and
2. explicit local path reference.

Both paths normalize to a canonical `InputManifest`.

Conceptual manifest fields include:

```text
input_id
kind = retrieval_ground_truth | retrieval_predictions
source_mode = imported | referenced
canonical_format = retrieval-jsonl-v1
content_sha256
record_count
validation_status
created_at
schema_version
```

### 11.1 Browser uploads

Uploaded files are written to a temporary local file, validated, normalized, hashed, and only then promoted into workspace-owned imported storage.

### 11.2 Local references

A path reference is explicit user input, not a filesystem browser.

The server must:

- canonicalize and resolve the path
- confirm it is a readable regular file
- resolve symlinks to the real location before provenance is persisted
- validate content
- compute a content hash
- register an `input_id`

Subsequent run requests use `input_id`, not arbitrary paths.

If a referenced file changes after validation, the changed content is a different input revision and must not silently inherit prior provenance.

## 12. Supported input formats

MVP supports:

- canonical retrieval JSONL; and
- a guided CSV importer.

CSV is an ingestion adapter only.

```text
CSV
 ↓
explicit column mapping
 ↓
canonical retrieval records
 ↓
Pydantic validation
 ↓
existing retrieval runner
```

The importer may support mapping fields such as:

```text
query_id
relevant_document_ids
retrieved_document_ids
```

It must not support arbitrary nested transforms, user expressions, custom Python, or generic data-wrangling pipelines.

## 13. Validation summary

Before a run can be created, the Workspace must present actionable input validation evidence rather than a single `valid` flag.

Examples include:

- format/schema
- record count
- unique query count
- duplicate IDs
- missing identifiers
- content SHA-256
- prediction/ground-truth overlap
- missing prediction queries
- extra prediction queries
- blocking errors vs non-blocking warnings

Blocking schema/identity errors stop evaluation before enqueueing a job.

## 14. Retrieval-first MVP

Phase 6 evaluates retrieval only.

Canonical flow:

```text
ground truth
+ predictions
+ constrained RunConfig
        ↓
existing retrieval runner
        ↓
existing retrieval evaluator
        ↓
EvaluationResult
        ↓
local immutable artifact
```

MVP configuration is deliberately constrained.

User-adjustable fields include only values with clear experiment semantics such as:

- run name
- ground-truth input
- prediction input
- `top_k`
- system label
- dataset/version metadata
- optional explicit comparison reference

Metric formulas, evaluator semantics, claim policy, and regression meaning are not arbitrary UI knobs.

## 15. Run immutability and provenance

Once execution begins, a run snapshots its inputs and configuration.

A completed run includes enough provenance to identify at least:

- input identities and hashes
- `RunConfig`
- evaluator/version metadata
- dataset identity/version
- execution timestamp
- EvalOps version
- resulting artifact hash

After a run is `COMPLETE`, its config/result/provenance is immutable.

Changing config and executing again creates a new run identity.

## 16. Job execution model

The approved model is a **persistent single-worker queue**.

State machine:

```text
QUEUED
  ↓
VALIDATING
  ↓
EVALUATING
  ↓
ANALYZING
  ↓
WRITING_ARTIFACT
  ↓
COMPLETE
```

Terminal states:

```text
COMPLETE
FAILED
CANCELLED
INTERRUPTED
```

Parallel evaluation workers are out of scope.

## 17. Cancellation and restart recovery

Cancellation is cooperative.

- queued jobs cancel immediately
- running work stops at deterministic safe checkpoints
- artifact writes must not leave half-written canonical results

On server restart:

- `QUEUED` jobs may be re-enqueued
- completed/failed/cancelled jobs remain history
- jobs persisted in transient execution states become `INTERRUPTED`

Phase 6 does not resume computation mid-step.

Retry creates a **new job identity** using the persisted source config/provenance. Existing history is not rewritten.

## 18. Session bootstrap and localhost security

The server binds only to loopback.

`evalops workspace` must not expose an option equivalent to `--host 0.0.0.0` in Phase 6.

Startup concept:

```text
evalops workspace
        ↓
generate cryptographically random one-time nonce
        ↓
open http://127.0.0.1:<port>/#bootstrap=<nonce>
        ↓
SPA exchanges nonce
        ↓
server invalidates nonce
        ↓
process-local session cookie
```

The bootstrap nonce is carried in the URL fragment rather than the query string to reduce accidental access-log leakage.

After successful exchange, the SPA removes the fragment from browser history.

Session cookie intent:

- `HttpOnly`
- `SameSite=Strict`
- `Path=/`
- session-only

Restarting the server invalidates the previous process-local session.

## 19. Request security controls

The local server enforces:

- bind to `127.0.0.1`
- expected loopback Host validation
- no wildcard CORS
- exact-origin validation for mutating requests
- valid process-local session for privileged endpoints
- anti-framing response policy
- restrictive CSP
- no remote analytics/scripts/fonts required for production operation

The production-local app is same-origin: the Python process serves both `/api/v1/*` and the prebuilt Workspace SPA.

Localhost is not treated as equivalent to unauthenticated.

## 20. API contract

The local API is versioned under:

```text
/api/v1/
```

Resource groups are expected to include equivalents of:

```text
session/
workspaces/
workspaces/{workspace_id}/inputs/
workspaces/{workspace_id}/runs/
workspaces/{workspace_id}/comparisons/
workspaces/{workspace_id}/exports/
jobs/
jobs/{job_id}/events
```

Pydantic/FastAPI request and response models are the server authority.

The frontend may use generated or checked OpenAPI schema plus TypeScript types and Zod runtime validation, but the browser is never the enforcement authority.

A breaking contract should use an explicit versioning decision rather than silently changing `/api/v1` meaning.

## 21. SSE progress model

REST handles state and actions. SSE handles server-to-browser job progress.

Conceptual event:

```json
{
  "job_id": "job-...",
  "sequence": 14,
  "state": "EVALUATING",
  "progress": {
    "completed": 420,
    "total": 1000
  },
  "message": "Evaluating retrieval queries"
}
```

SSE is advisory for UX freshness, not the canonical source of truth.

If the browser disconnects, the job continues. Reconnection reads persisted job state and resumes live updates.

SSE must not stream private raw evaluation payloads merely for convenience.

## 22. API error contract

API errors are structured, sanitized, and actionable.

Example intent:

```json
{
  "error": {
    "code": "INPUT_DUPLICATE_QUERY_ID",
    "message": "Prediction input contains duplicate query IDs.",
    "field": "predictions",
    "retryable": false
  }
}
```

API/UI responses must not expose:

- Python traceback
- environment-variable dumps
- session/bootstrap secrets
- arbitrary filesystem contents
- raw corpus content
- private prompts/responses
- hidden reasoning

## 23. Filesystem write boundary

By default the server may write only to:

- the canonical EvalOps local root
- registered workspace directories
- server-owned temporary paths

The only user-directed exception is an explicit export destination in the public-evidence export flow.

The server must not expose a general filesystem listing/read API.

## 24. Pinned baseline model

The approved comparison model uses an **explicit pinned baseline**.

A completed eligible run may be set as the workspace baseline.

The workspace baseline stores a stable run/artifact reference, conceptually:

```text
run_id
artifact_sha256
```

Changing the workspace baseline never changes the meaning of historical comparisons.

Each comparison snapshots both baseline and candidate identities/hashes.

## 25. Compatibility and exploratory comparisons

Canonical comparison is **fail closed by default**.

Compatibility checks include important dimensions such as:

- dataset identity/version
- evaluator/metric version
- `top_k`
- population/provenance where applicable
- schema/contract version

Statuses include equivalents of:

```text
COMPARABLE
NON_COMPARABLE
EXPLORATORY_ONLY
```

If inputs are incompatible, canonical regression comparison is blocked.

The user may explicitly create an exploratory comparison. Such a result is permanently labeled `EXPLORATORY_ONLY` and is not eligible for public regression/benchmark claims.

Metric difference must never be presented as equivalent to a valid regression comparison.

## 26. Workspace UX

Primary navigation is expected to include equivalents of:

```text
Overview
Inputs
Runs
Comparisons
Failures
Exports
```

The main path is:

```text
Workspace Home
→ Create/Open Workspace
→ Add Inputs
→ Validation Summary
→ Configure Retrieval Run
→ Review & Run
→ Live Progress
→ Run Result
→ Set Baseline
→ Compare
→ Failure Explorer
→ Export Public Evidence
→ Sanitized Preview
→ Explicit Confirm
```

The UI must retain a persistent distinction such as:

```text
LOCAL WORKSPACE
Data stays on this machine
```

Local evidence must not be visually confused with public evidence.

## 27. Run result UX

A completed run presents at least four information layers:

1. summary metrics;
2. failure analysis;
3. provenance; and
4. evidence/publication status.

Metrics must include their evaluation context such as `@K` where relevant.

Provenance must be directly inspectable rather than hidden behind marketing summaries.

## 28. Comparison and Failure Explorer UX

Comparison shows compatibility before metric deltas.

When comparable, the UI may show baseline, candidate, and delta side by side.

When non-comparable, the canonical comparison is blocked and reasons are shown.

The local Failure Explorer may show private run details unavailable in the public console, while keeping application-level boundaries and avoiding arbitrary query/script execution.

Useful filters may include:

- failure category
- query ID
- baseline pass → candidate fail
- candidate pass → baseline fail
- missing prediction
- rank movement

## 29. Explicit public-evidence export

Eligible run/comparison results expose an explicit **Export Public Evidence** action.

The preview must distinguish:

- fields included
- fields removed
- fields transformed
- verification status
- data kind
- claim scope
- limitations
- export destination

The existing public export policy/adapters/serialization remain authoritative.

The preview must make it clear that raw local paths, private inputs, raw corpus content, prompts, responses, logs, secrets, and other disallowed local data are not part of the public artifact.

Exploratory-only comparison results are not eligible for public regression claims.

Creating a sanitized export is not the same as publishing it to GitHub Pages.

## 30. Packaging model

The Vite Workspace build is packaged into the Python distribution as static package data.

Conceptual release pipeline:

```text
apps/workspace
      ↓
npm ci
lint / typecheck / unit / build
      ↓
prebuilt dist
      ↓
Python package data
      ↓
wheel
      ↓
clean environment install
      ↓
evalops workspace
```

`src/evalops/workspace/static/` is generated/package output, not the UI source of truth.

A user must not need a repository checkout or Node.js to run the packaged Workspace.

## 31. One-command startup contract

With the optional dependencies installed, `evalops workspace` must:

1. resolve/create the local EvalOps root;
2. recover persisted job states;
3. generate the bootstrap nonce;
4. select an available loopback port unless explicitly configured;
5. bind only to `127.0.0.1`;
6. start the single worker;
7. serve the packaged SPA;
8. open the default browser unless `--no-open` is used; and
9. print only safe local startup information.

Operational options may include:

```text
--no-open
--port <port>
--root <explicit-local-root>
```

No LAN-host option is part of Phase 6.

## 32. Testing strategy

Phase 6 requires coverage at four layers:

```text
Python / React unit
        ↓
API / application / storage integration
        ↓
real localhost browser E2E
        ↓
clean packaged-wheel E2E/smoke
```

Metric correctness remains covered by the existing evaluator tests. Workspace tests verify orchestration, provenance, state, policy, and security rather than duplicating metric formulas.

## 33. Mandatory Python behavior tests

Coverage must include at least:

- workspace create/rename/lookup
- imported/reference input manifests
- hashing/provenance
- duplicate-ID rejection
- changed referenced file detection
- CSV normalization
- immutable completed runs
- baseline semantics
- compatibility classification
- exploratory override
- export eligibility
- atomic writes
- restart → `INTERRUPTED`
- retry identity
- cancellation transitions
- path canonicalization/symlink behavior

Tests use temporary directories rather than user-local state.

## 34. Mandatory API/security tests

Tests must cover at least:

- bootstrap nonce one-time use
- session enforcement
- session invalidation after server restart
- exact-origin checks
- Host validation
- upload/reference registration
- workspace isolation
- run creation
- cancellation
- SSE reconnection behavior
- export preview/confirmation
- safe error serialization

Negative cases include:

```text
missing session        → reject
wrong Origin           → reject
nonce reuse            → reject
unknown workspace      → reject
path traversal         → reject
invalid state change   → reject
exploratory export     → reject
```

## 35. Browser E2E

Canonical Playwright E2E uses a real Python localhost server.

Minimum happy path:

```text
start server
→ authenticate browser
→ create workspace
→ upload ground truth
→ upload predictions
→ validate
→ configure top_k
→ run retrieval evaluation
→ observe progress
→ COMPLETE
→ inspect metrics/failures/provenance
→ set baseline
→ run second candidate
→ compare
→ inspect failures
→ preview sanitized export
→ create sanitized export
```

A separate E2E path covers guided CSV import.

Required failure scenarios include changed referenced input, incompatible comparison/exploratory override, restart recovery, and cross-origin request rejection.

## 36. Accessibility and responsive requirements

Workspace follows the accessibility discipline of the Evidence Console.

Requirements include:

- keyboard navigation
- visible focus
- semantic labels
- accessible validation/error messages
- status communication that does not rely on color alone
- accessible tables
- controlled live-region progress announcements
- correct dialog focus management
- no root horizontal overflow

Canonical browser verification covers at least approximately:

```text
390px
768px
1280px+
```

Dense tables may use scoped horizontal scrolling or alternate presentation on narrow viewports, but the root page must not overflow.

Curated flows target zero axe violations, with no serious/critical violations accepted.

## 37. CI and compatibility gates

Phase 6 adds Workspace gates without weakening existing gates.

Conceptual CI categories:

```text
EvalOps Core
- pytest
- Ruff
- mypy
- existing CLI behavior

Public Evidence Console
- existing lint/type/unit/static gates
- Storybook
- Pages/browser E2E

Local Workspace
- frontend lint/type/unit/build
- Python workspace tests
- API/security integration
- Playwright E2E
- axe
- wheel/package smoke
```

The public build must prove that the local Workspace runtime is not accidentally bundled into GitHub Pages.

Existing behavior that must remain compatible includes:

- `evalops retrieval evaluate`
- regression commands
- evidence export/index
- public artifact serialization
- `apps/web` static export
- Evidence Console production routes
- `SYNTHETIC_FIXTURE` / `INTEGRATION_ONLY` policy semantics

## 38. Test data policy

CI uses only small deterministic synthetic fixtures.

Do not require:

- private datasets
- user filesystem data
- provider APIs
- paid services
- live vector databases
- large benchmark downloads

The full canonical Workspace path must be able to run reproducibly without external network access.

## 39. Delivery decomposition

Phase 6 is delivered in four implementation slices.

### 39.1 Phase 6.1 — Workspace Foundation

Includes:

- optional workspace dependency boundary
- `evalops workspace` shell
- FastAPI loopback server
- session/bootstrap security
- workspace registry/storage primitives
- Vite Workspace shell

Acceptance proves startup, authentication, workspace creation/reopen, restart persistence, and security boundaries. Retrieval execution is not required yet.

### 39.2 Phase 6.2 — Input & Retrieval Execution

Includes:

- JSONL upload/reference
- guided CSV importer
- validation summary
- constrained RunConfig
- single-worker queue
- SSE progress
- retrieval result/provenance

This is the first meaningful interactive evaluation milestone.

### 39.3 Phase 6.3 — Comparison & Failure Analysis

Includes:

- pinned baseline
- compatibility checks
- canonical regression comparison
- `EXPLORATORY_ONLY` override
- local Failure Explorer

This turns the Workspace from an interactive runner into an EvalOps regression workflow.

### 39.4 Phase 6.4 — Evidence Promotion & Packaging

Includes:

- sanitized export preview
- public-export eligibility
- packaged Vite assets in the wheel
- clean-install acceptance
- full browser/accessibility verification
- documentation and final release evidence

The phase is not complete if the Workspace works only from a monorepo checkout.

## 40. Migration and retention policy

There is no legacy Workspace storage to migrate in Phase 6.

Persisted contracts include schema versions from the beginning.

Completed run artifacts and historical comparisons are not automatically garbage-collected.

Changing the baseline does not delete or rewrite old comparisons.

Workspace/run deletion and bulk destructive management are not core MVP requirements.

## 41. Logging and privacy

Local structured logging may include:

- server startup/shutdown
- workspace/job IDs
- job state transitions
- safe error categories
- timings

It must not include by default:

- session/bootstrap tokens
- environment-variable dumps
- prompts
- raw corpus content
- raw private input records
- remote telemetry or analytics

## 42. Documentation positioning

After Phase 6 implementation, repository-facing documentation should distinguish three surfaces:

```text
1. Live Evidence Console
   public verification / recruiter path

2. Local Evaluation Workspace
   private interactive execution

3. CLI
   automation / reproducible engineering workflow
```

The Live Evidence Console remains the primary recruiter/public CTA.

The Workspace is documented as localhost/private and must not be represented as hosted or automatically publishing evidence.

## 43. Release semantics

Existing `v0.1.0` remains a historical frozen baseline and must not be repointed or reused.

If Phase 6 passes all implementation, packaging, regression, security, and owner-acceptance gates, the intended future milestone is:

```text
v0.2.0 — Local Evaluation Workspace
```

Do not create the release before final Phase 6 acceptance.

## 44. Definition of Done

Phase 6 is complete only after fresh verification proves, at minimum:

```text
Python full suite              PASS
Ruff                           PASS
mypy                           PASS

Workspace lint                 PASS
Workspace typecheck            PASS
Workspace unit                 PASS
Workspace build                PASS

API/security integration       PASS
Workspace Playwright E2E       PASS
axe canonical flows            PASS

wheel build                    PASS
clean-wheel install            PASS
evalops workspace smoke        PASS

Evidence Console regression    PASS
public Pages build/E2E         PASS

no external runtime requests   PASS
loopback-only proof            PASS
secret/path leakage checks     PASS
```

Actual test counts are reported from fresh evidence and are not fixed in advance.

Completion classifications remain evidence-based:

- **COMPLETE** — all required product/security/package/regression gates pass and owner acceptance is complete.
- **COMPLETE_WITH_LIMITATIONS** — implementation is sound but a clearly documented non-material platform/owner boundary remains.
- **BLOCKED** — a material security, evidence-integrity, packaging, or production regression gate fails.
- **NOT_COMPLETE** — implementation exists but required acceptance evidence is incomplete.

## 45. Planning gate

This document is the canonical Phase 6 design only after owner review and explicit approval.

No implementation plan, implementation issue breakdown, worktree, source mutation, or Codex implementation prompt may proceed from this spec until the owner explicitly approves the written spec.

After written-spec approval, the next step is to produce a detailed implementation plan under `docs/superpowers/plans/` and submit that plan for owner approval before implementation begins.
