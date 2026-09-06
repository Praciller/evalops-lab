# Phase 6.4 Evidence Promotion & Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Complete the Local Evaluation Workspace as a distributable, privacy-preserving product by adding explicit sanitized public-evidence preview/export, packaging the Vite bundle inside the Python wheel, proving clean-install one-command operation, and closing all Workspace/public regression/documentation gates without publishing a release prematurely.

**Architecture:** Local run/comparison artifacts cross into public evidence only through existing `evalops.export` adapters/policy/serialization. Preview builds the exact public artifact bytes in memory, reports what is included/removed/transformed, and requires a second explicit confirmation to write to a user-selected directory. Canonical comparisons export as a self-consistent bundle containing sanitized baseline/candidate run artifacts, the comparison artifact, and an explicit public index so existing operand compatibility validation can run. Build/release automation compiles `apps/workspace`, stages static assets into Python package data, builds a wheel, installs it into a clean environment, and runs the real `evalops workspace` process with no Node runtime dependency.

**Tech Stack:** Existing `evalops.export` V1 models/adapters/policy/serialization, Phase 6.3 comparison artifacts, FastAPI, React/Vite, setuptools, `python -m build`, Playwright, axe, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-06-phase-6-interactive-evaluation-workspace-design.md`

## Global Constraints

- Begin from the accepted Phase 6.3 merge in a fresh isolated worktree on current `origin/main`.
- Do not create, move, delete, or repoint Git tag/release `v0.1.0`.
- Do not create `v0.2.0` in this implementation slice. The intended release is owner-gated **after** Phase 6 final merge, fresh acceptance, and explicit release approval.
- `apps/web` remains the primary public/recruiter surface and stays static/read-only. Workspace export is not automatic publication.
- No `Publish to GitHub`, git commit/push, GitHub API, Pages deployment action, or implicit write to `apps/web/public/evidence` is added to Workspace.
- Existing public evidence adapters/policy/serialization are authoritative. Do not build a second sanitizer in Workspace.
- `EXPLORATORY_ONLY` comparison export is always blocked.
- Phase 6 Workspace ad-hoc inputs may export only as `SYNTHETIC_FIXTURE/INTEGRATION_ONLY` or `CURATED_DATASET/PROTOCOL_SPECIFIC`. `OFFICIAL_BENCHMARK/BENCHMARK_RESULT` stays outside this local ad-hoc Workspace promotion path because official benchmark provenance is not established by import/reference alone.
- Public verification status (`UNVERIFIED`, `PARTIAL`, `VERIFIED`) is explicit owner-supplied export metadata and is validated by existing models; local job completion alone must never auto-promote it to VERIFIED.
- Export destinations are explicit user choices. Never overwrite an existing public artifact/bundle silently.
- Node.js may be required in source/release build environments but not to run an installed wheel.
- Full Phase 6.1–6.3 plus Evidence Console regression/security/no-network gates remain required.

## Target File Structure

```text
src/evalops/workspace/
├─ application/
│  └─ exports.py                   # preview/eligibility/confirm use-cases
├─ export/
│  ├─ __init__.py
│  └─ models.py                    # local export request/preview/manifest contracts
├─ api/
│  ├─ models.py
│  └─ routes_exports.py
├─ static/                         # generated staging target; not UI source
└─ cli.py                          # installed static-resource resolution

tests/workspace/
├─ test_export_preview.py
├─ test_export_write.py
├─ test_api_exports.py
├─ test_static_assets.py
└─ test_package_smoke.py

apps/workspace/src/
├─ components/
│  ├─ export-classification-form.tsx
│  ├─ export-preview.tsx
│  └─ export-confirmation.tsx
└─ pages/
   └─ exports-page.tsx

apps/workspace/tests/
├─ export-run.spec.ts
├─ export-comparison.spec.ts
└─ packaged-workspace.spec.ts

scripts/
├─ stage_workspace_assets.py
├─ verify_workspace_wheel.py
└─ verify_workspace_runtime_boundary.py

.github/workflows/workspace-ci.yml
README.md
CONTRIBUTING.md
DEPLOY.md
pyproject.toml
.gitignore
```

## Task 1: Define local export requests, eligibility, and exact sanitized preview bytes

**Files:**
- Create: `src/evalops/workspace/export/__init__.py`
- Create: `src/evalops/workspace/export/models.py`
- Create: `src/evalops/workspace/application/exports.py`
- Create: `tests/workspace/test_export_preview.py`

**Interfaces:**

```python
class WorkspaceExportDataKind(StrEnum):
    SYNTHETIC_FIXTURE = "SYNTHETIC_FIXTURE"
    CURATED_DATASET = "CURATED_DATASET"

class ExportClassification(BaseModel):
    verification_status: VerificationStatus
    data_kind: WorkspaceExportDataKind
    limitations: list[str] = Field(default_factory=list)

class ExportPreview(BaseModel):
    schema_version: Literal["workspace-export-preview-v1"]
    preview_id: str
    source_type: Literal["run", "comparison"]
    source_id: str
    eligible: bool
    blocking_reasons: list[str]
    output_files: list[PreviewFile]
    included: list[str]
    removed: list[str]
    transformed: list[str]
    classification: ExportClassification
    expires_at: datetime

class ExportService:
    def preview_run(... ) -> ExportPreview: ...
    def preview_comparison(... ) -> ExportPreview: ...
```

**Derived claim scope:**

```text
SYNTHETIC_FIXTURE → INTEGRATION_ONLY
CURATED_DATASET   → PROTOCOL_SPECIFIC
```

- [ ] Write failing tests proving a run preview calls `adapt_evaluation_result()` and `serialize_public_artifact()` rather than manually selecting public fields.
- [ ] Test synthetic classification automatically derives `INTEGRATION_ONLY`; curated derives `PROTOCOL_SPECIFIC`; the API/model exposes no `OFFICIAL_BENCHMARK` option in this Workspace path.
- [ ] Test `NOT_RUN` is rejected by existing public policy and local completion does not auto-set verification status.
- [ ] Test path-like/secret-like metadata rejected by existing `safe_public_text`/public models causes preview to be ineligible with a safe blocking reason; do not catch-and-ignore sanitizer failure.
- [ ] Assert output bytes are exactly the deterministic bytes from `serialize_public_artifact()` and contain no Workspace root, input source path, job record, session/bootstrap data, private logs, or raw original CSV.
- [ ] Define static preview disclosure lists that truthfully describe the current adapter boundary: included aggregate/public metadata and allowed sanitized evidence; removed local paths/private source files/job/log/session data; transformed internal models into Public Evidence Contract V1. The disclosure text must not claim a field was removed unless the actual adapter excludes it.
- [ ] Store preview material in process-local memory keyed by opaque `preview-<uuid4hex>` with a short expiry (for example 15 minutes); do not persist sanitized preview files before confirmation.
- [ ] Run `pytest tests/workspace/test_export_preview.py -q` until green.
- [ ] Commit: `feat(workspace): add sanitized run export preview`.

## Task 2: Build validated comparison export bundles from both operands

**Files:**
- Modify: `src/evalops/workspace/application/exports.py`
- Modify: `src/evalops/workspace/export/models.py`
- Modify: `tests/workspace/test_export_preview.py`

**Comparison bundle contract:**

```text
<artifact-id>/
├─ baseline.json
├─ candidate.json
├─ comparison.json
└─ index.json
```

- [ ] Add failing tests that `EXPLORATORY_ONLY` comparisons are ineligible before any serialization attempt.
- [ ] For a canonical comparable comparison, adapt baseline and candidate `EvaluationResult`s using the same selected verification/data-kind/derived claim scope, assign deterministic safe IDs based on the requested comparison artifact ID (`<id>-baseline`, `<id>-candidate`, `<id>`), and adapt the `RegressionReport` with `PopulationCompatibility.MATCHED`.
- [ ] Build `PublicEvidenceIndexV1` with `build_public_index([baseline, candidate, comparison])` so existing `validate_comparison_operands()` verifies operand references/metadata/compatibility.
- [ ] Write failing tests for mismatched/tampered run hashes, non-matching comparison operand IDs, incompatible population metadata, secret/path-like public metadata, and comparison verification that would contradict operand/public rules.
- [ ] Serialize all four artifacts deterministically and expose their exact SHA-256 values in the preview.
- [ ] Ensure local private failure-transition records are **not** copied wholesale into public comparison output; only existing public adapters determine allowed comparison fields.
- [ ] Run focused export tests until green.
- [ ] Commit: `feat(workspace): preview validated public comparison bundles`.

## Task 3: Confirm exports to an explicit non-overwriting destination

**Files:**
- Modify: `src/evalops/workspace/application/exports.py`
- Create: `tests/workspace/test_export_write.py`

**Interfaces:**

```python
class ConfirmExportRequest(BaseModel):
    preview_id: str
    destination_directory: str

class ExportManifest(BaseModel):
    schema_version: Literal["workspace-export-manifest-v1"]
    export_id: str
    source_type: Literal["run", "comparison"]
    source_id: str
    destination: str
    files: list[ExportedFile]
    classification: ExportClassification
    created_at: datetime

class ExportService:
    def confirm(self, request: ConfirmExportRequest) -> ExportManifest: ...
```

- [ ] Write failing tests for expired/unknown preview ID, changed source artifact after preview, destination explicit path resolution, regular-directory requirement, non-overwrite behavior, existing target file/bundle rejection, write failure cleanup, and successful manifest history.
- [ ] Re-hash/revalidate the source run/comparison artifacts at confirmation; a preview is not permission to export changed evidence.
- [ ] Resolve the destination explicitly. Do not provide/list arbitrary filesystem directories through an API. The user supplies the path string.
- [ ] Run export writes as temp files/directories under the destination parent and atomically rename when the complete artifact/bundle is ready. On failure, remove only the temporary server-owned path.
- [ ] Run export: write `<artifact-id>.json` into the selected directory and fail if that exact file exists.
- [ ] Comparison export: create `<artifact-id>/` bundle directory and fail if it already exists or is non-empty; never merge into an existing bundle.
- [ ] Persist a private export manifest under the Workspace `exports/manifests/` directory only after destination write success. This manifest may store the resolved destination locally but is never public evidence.
- [ ] Do not run Git commands or write directly to a repository path unless the owner explicitly entered that path as the destination; even then, perform only the file export and no commit/push/publish action.
- [ ] Run `pytest tests/workspace/test_export_write.py -q` until green.
- [ ] Commit: `feat(workspace): confirm explicit public evidence exports`.

## Task 4: Expose two-step export API and user-visible sanitization preview

**Files:**
- Create: `src/evalops/workspace/api/routes_exports.py`
- Modify: `src/evalops/workspace/api/models.py`
- Modify: `src/evalops/workspace/api/app.py`
- Create: `tests/workspace/test_api_exports.py`
- Regenerate: `apps/workspace/openapi.json`
- Modify: `apps/workspace/src/api/schemas.ts`
- Modify: `apps/workspace/src/api/client.ts`
- Create: `apps/workspace/src/components/export-classification-form.tsx`
- Create: `apps/workspace/src/components/export-preview.tsx`
- Create: `apps/workspace/src/components/export-confirmation.tsx`
- Create: `apps/workspace/src/pages/exports-page.tsx`
- Modify: `apps/workspace/src/routes.tsx`
- Add focused frontend tests beside the new files

**API additions:**

```text
POST /api/v1/workspaces/{workspace_id}/exports/preview
POST /api/v1/workspaces/{workspace_id}/exports/confirm
GET  /api/v1/workspaces/{workspace_id}/exports
```

- [ ] Write failing API tests for run preview, canonical comparison preview, exploratory block, invalid classification, missing/expired preview, changed source between preview/confirm, explicit destination, non-overwrite error, cross-workspace source, session/origin enforcement, and safe error bodies.
- [ ] API request accepts artifact ID, source ID/type, verification status, allowed local data kind, limitations. Claim scope is server-derived and official benchmark classification is not accepted by this Workspace route.
- [ ] Regenerate/check OpenAPI and update Zod schemas/client methods.
- [ ] Write failing UI tests that preview shows separate `Included`, `Removed`, `Transformed`, `Classification`, and output-file sections before destination/confirm controls become active.
- [ ] Make the UI state clearly say `Creating sanitized export does not publish to GitHub Pages`.
- [ ] Require explicit destination text entry and a second confirm action. There is no default repository/public-evidence path, no filesystem explorer, and no `Publish` action.
- [ ] After success, show output file names/hashes and local export manifest identity; do not claim deployment/public availability.
- [ ] Run Python API tests plus Workspace lint/type/unit/build/OpenAPI checks.
- [ ] Commit: `feat(workspace): add explicit evidence export flow`.

## Task 5: Prove sanitization/export behavior in browser E2E

**Files:**
- Create: `apps/workspace/tests/export-run.spec.ts`
- Create: `apps/workspace/tests/export-comparison.spec.ts`
- Modify: `scripts/run_workspace_e2e_server.py`

- [ ] Run export E2E: complete a synthetic run → choose `SYNTHETIC_FIXTURE` + explicit verification → preview → assert `INTEGRATION_ONLY`, disclosure lists, sanitized file hash → confirm into an E2E temp destination → parse exported JSON and validate Public Evidence V1 shape.
- [ ] Assert exported run bytes contain no Workspace root, input path, original CSV filename if disallowed by adapter, bootstrap/session tokens, raw local logs, or external URL.
- [ ] Comparison export E2E: create canonical comparison → preview four-file bundle → confirm → parse all artifacts/index → assert `build_public_index`-equivalent operand references are valid.
- [ ] Attempt export from `EXPLORATORY_ONLY` and assert hard block before destination write.
- [ ] Attempt confirm after mutating/tampering a source artifact in test harness and assert failure with no destination artifact.
- [ ] Assert no external runtime requests and run axe on export screens; target zero violations, no serious/critical accepted.
- [ ] Commit: `test(workspace): prove explicit sanitized export flow`.

## Task 6: Stage the Vite bundle into Python package data deterministically

**Files:**
- Modify: `pyproject.toml`
- Modify: `.gitignore`
- Create: `scripts/stage_workspace_assets.py`
- Modify: `src/evalops/workspace/cli.py`
- Create: `tests/workspace/test_static_assets.py`

**Package configuration intent:**

```toml
[tool.setuptools.package-data]
"evalops.workspace" = ["static/*", "static/assets/*"]
```

- [ ] Add `build>=1.2,<2` to `dev` dependencies.
- [ ] Write failing tests for installed-resource lookup, source-checkout fallback, missing index error, and refusal to serve a partially staged bundle.
- [ ] Implement `scripts/stage_workspace_assets.py`: require a successful `apps/workspace/dist/index.html`, remove only previous server-owned staging contents under `src/evalops/workspace/static`, copy `index.html` + asset tree, reject sourcemaps if not intentionally shipped, and emit a deterministic asset manifest with SHA-256 per staged file.
- [ ] Ignore generated `src/evalops/workspace/static/*` in Git while retaining the directory marker/build instructions as needed. Do not commit minified generated assets as UI source.
- [ ] Update runtime static resolution to prefer `importlib.resources.files("evalops.workspace") / "static"` when installed. A source-checkout fallback to `apps/workspace/dist` is allowed for development, but installed runtime must not depend on repository paths.
- [ ] Validate that the staged bundle contains no absolute developer-machine paths, source maps with private source content, external script/font references, or build-time secrets.
- [ ] Run frontend build → stage script → Python static tests.
- [ ] Commit: `build(workspace): stage frontend assets for Python packaging`.

## Task 7: Build and verify the real wheel in a clean environment

**Files:**
- Create: `scripts/verify_workspace_wheel.py`
- Create: `tests/workspace/test_package_smoke.py`
- Modify: `apps/workspace/tests/packaged-workspace.spec.ts`
- Modify: `apps/workspace/package.json`

- [ ] Write a package-smoke test that opens the built wheel as a ZIP and asserts `evalops/workspace/static/index.html` and referenced asset files exist and match the staging manifest.
- [ ] Implement `scripts/verify_workspace_wheel.py` to create a fresh temporary virtual environment, install the produced wheel with its `[workspace]` extra, run representative core CLI `--help`, start installed `evalops workspace --no-open --root <temp> --port <free-port>`, parse the explicitly emitted one-time bootstrap URL for `--no-open`, and wait for healthy loopback service.
- [ ] Assert the installed process imports/serves static resources from the wheel/venv, not the source checkout. Run verification from a working directory outside the repository.
- [ ] Point `packaged-workspace.spec.ts` at that installed server and execute a compact canonical flow: bootstrap → create workspace → import deterministic JSONL fixtures made available in temp data → run → COMPLETE → inspect result → sanitized run export.
- [ ] Assert browser network origins remain only `http://127.0.0.1:<port>` and that Node is not invoked by the installed Python process.
- [ ] After server shutdown, assert a second launch with the same test root can reopen local metadata and creates a new invalidating bootstrap/session context.
- [ ] Run `python -m build`; run wheel ZIP test; run `python scripts/verify_workspace_wheel.py dist/<wheel>`; run packaged Playwright.
- [ ] Commit: `test(workspace): verify clean wheel runtime`.

## Task 8: Expand Workspace CI to full build/package acceptance

**Files:**
- Modify: `.github/workflows/workspace-ci.yml`
- Create: `scripts/verify_workspace_runtime_boundary.py`

- [ ] Extend `workspace` CI to: install Python deps; Python lint/type/full Workspace tests; Node install/lint/type/unit; Vite build; OpenAPI check; Playwright source-checkout E2E; stage static assets; `python -m build`; wheel content check; clean-wheel verification; packaged Playwright.
- [ ] Add a runtime-boundary script that scans built `apps/workspace/dist`, staged static files, and wheel contents for: external HTTP(S) runtime references (allow only intentionally inert documentation text), `0.0.0.0`, developer absolute paths, known secret-key field patterns, source maps, and accidental `apps/web/public/evidence` write defaults.
- [ ] Preserve least-privilege GitHub Actions permissions and immutable action SHAs.
- [ ] Do not make the `workspace` status required in the main ruleset inside the same unproven workflow edit. After this workflow passes on a real PR, governance may be updated only as an explicit owner-approved follow-up/readback.
- [ ] Ensure CodeQL JS/TS includes `apps/workspace` source and Python analysis includes `src/evalops/workspace`; do not suppress findings to make CI green.
- [ ] Commit: `ci(workspace): enforce package and runtime acceptance`.

## Task 9: Update product/documentation boundaries without weakening recruiter flow

**Files:**
- Modify: `README.md`
- Modify: `CONTRIBUTING.md`
- Modify: `DEPLOY.md`
- Add/modify only other existing docs that need canonical Workspace instructions

- [ ] Add Local Evaluation Workspace as the second product surface after the **Live Evidence Console** primary CTA. Preserve the recruiter 90-second public evidence flow.
- [ ] Document clear distinction:
  - Evidence Console = hosted/static/sanitized/public/read-only.
  - Local Workspace = localhost/private/interactive/explicit local input access/no automatic publish.
  - CLI = automation/reproducible engineering workflow.
- [ ] Document install/start commands: `pip install "evalops-lab[workspace]"`, `evalops workspace`, plus `--no-open`, `--port`, `--root`; state explicitly that no LAN host option exists.
- [ ] Document JSONL + guided CSV scope, single-worker/restart semantics, explicit sanitized export, and the fact that `EXPLORATORY_ONLY` cannot become a public regression claim.
- [ ] In `CONTRIBUTING.md`, add Workspace validation commands and generated-static rule: edit `apps/workspace`, never hand-edit `src/evalops/workspace/static`.
- [ ] In `DEPLOY.md`, keep GitHub Pages instructions scoped to `apps/web`; add local package acceptance/release evidence instructions without calling Workspace a deployment.
- [ ] Do not change the package version/tag/release to `0.2.0` yet. Add an owner-gated release checklist if useful, clearly marked future/post-acceptance.
- [ ] Check README links/rendering and run docs/public web gates.
- [ ] Commit: `docs(workspace): document local evaluation workspace`.

## Task 10: Final Phase 6 pre-merge acceptance

**Files:**
- Review the complete Phase 6 diff and all four plans/spec.

- [ ] Fresh Python: `ruff check .`; `ruff format --check .`; `mypy src`; full `pytest`.
- [ ] Fresh core CLI proof: existing retrieval evaluate, regression compare, evidence export/index behavior remains passing.
- [ ] Fresh Workspace source proof: lint, typecheck, unit, Vite build, OpenAPI check, real FastAPI Playwright flows, axe at canonical routes/viewports.
- [ ] Fresh package proof: stage assets, build sdist/wheel, inspect wheel, install wheel with `[workspace]` in a clean venv outside repo, start installed server, packaged browser flow, restart persistence.
- [ ] Fresh public Evidence Console proof: existing `apps/web` lint/type/unit/Storybook/public-Storybook/static/Playwright gates and public evidence generation/validation unchanged.
- [ ] No-network proof: canonical source and packaged browser flows produce zero external runtime requests; Python retrieval evaluation makes no provider/network calls.
- [ ] Loopback proof: Uvicorn binds only `127.0.0.1`; no product config exposes `0.0.0.0`/LAN mode.
- [ ] Leakage proof: scan API/SSE responses, exported artifacts, build outputs, wheel, logs, and checked source for session/bootstrap values, secret-like fields, raw private input rows, local paths, source maps, and unintended repo publication paths.
- [ ] Placeholder scan: no TODO/FIXME/stub/fake metrics/fake export or ignored failing test remains in Phase 6 source.
- [ ] Run code review and resolve every material finding with fresh affected/full verification.
- [ ] Record exact test counts, hashes, CI run IDs, wheel hash, limitations, and the current main/PR SHAs in the implementation report; do not claim `COMPLETE` before post-merge verification.

## Task 11: Post-merge owner acceptance and release gate

**Files:**
- No source mutation unless verification finds a defect or the owner separately approves release work.

- [ ] After implementation PR(s) merge, read canonical `main` SHA and verify required GitHub contexts on that final state.
- [ ] Re-run/verify the public GitHub Pages production route set so Phase 6 did not regress the Evidence Console.
- [ ] Re-run a clean-wheel/local packaged Workspace acceptance from the final source SHA or release-candidate artifact.
- [ ] Classify Phase 6 truthfully as `COMPLETE`, `COMPLETE_WITH_LIMITATIONS`, `BLOCKED`, or `NOT_COMPLETE` using the approved spec.
- [ ] Only after explicit owner acceptance may a separate release action/PR bump package metadata and create **`v0.2.0 — Local Evaluation Workspace`**. Never reuse or move `v0.1.0`.

## Phase 6.4 Acceptance Contract

Phase 6.4 is accepted when local private run/comparison evidence can be previewed through the existing public sanitizer, canonical comparisons export with validated operand bundles, exploratory comparisons remain blocked, explicit confirmation writes deterministic non-overwriting artifacts without auto-publishing, the Vite Workspace is packaged inside a Python wheel, a clean environment can install and run `evalops workspace` without Node or a repository checkout, and all Workspace/core/public/security/accessibility/no-network gates remain green. Release `v0.2.0` remains a separate post-acceptance owner action.
