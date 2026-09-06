# Phase 6.1 Workspace Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Establish the local-only Workspace runtime, security boundary, file-backed workspace registry, authenticated React shell, and a dedicated Workspace CI gate without adding retrieval execution yet.

**Architecture:** `evalops workspace` remains a thin CLI adapter. It lazily loads an optional FastAPI/Uvicorn runtime, binds only to `127.0.0.1`, generates a one-time bootstrap nonce, serves a Vite-built React SPA and `/api/v1`, and persists only workspace metadata under an explicit local root. Browser requests are untrusted; session, Host, Origin, workspace identity, and filesystem boundaries are enforced server-side.

**Tech Stack:** Python 3.11+, Pydantic 2, FastAPI, Uvicorn, HTTPX/TestClient, React 19, Vite 7, TypeScript, Zod 4, Vitest, Testing Library, Playwright, ESLint, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-06-phase-6-interactive-evaluation-workspace-design.md`

## Global Constraints

- Work in a **new isolated Git worktree** created from the current `origin/main`; do not mutate the known divergent ordinary checkout.
- Before source changes, read `AGENTS.md`, the Phase 6 spec, this plan, and the current `pyproject.toml`, `src/evalops/cli.py`, `.github/workflows/ci.yml`, `.github/workflows/web-ci.yml`, and `apps/web/src/app/globals.css`.
- Do not change retrieval metrics, regression formulas, public evidence semantics, or production Evidence Console behavior in Phase 6.1.
- Do not add cloud services, provider calls, telemetry, a database, LAN binding, arbitrary filesystem APIs, authentication accounts, or a generic plugin system.
- Keep FastAPI/Uvicorn imports out of the core import path. Existing core commands must work after `pip install -e .` without `[workspace]`.
- Do not expose `--host`; the only product bind address is `127.0.0.1`.
- Use test-owned temporary directories only. Never read/write the real `~/.evalops` in tests.
- Generated frontend assets are not UI source of truth. `apps/workspace/src` is authoritative. Wheel packaging of the generated bundle belongs to Phase 6.4.
- Existing required checks (`quality`, `web`, CodeQL language analyses, Dependency Review) remain unchanged. A new Workspace CI job may run, but do not change the main ruleset in this slice.
- Every behavior change follows red → green → refactor and commits only after the scoped tests pass.

## Target File Structure

```text
packages/evidence-ui/
├─ package.json                    # CSS-only shared token package in 6.1
└─ tokens.css                      # stable Evidence design tokens only

apps/workspace/
├─ package.json
├─ package-lock.json
├─ eslint.config.mjs
├─ tsconfig.json
├─ vite.config.ts
├─ vitest.config.ts
├─ playwright.config.ts
├─ index.html
├─ src/
│  ├─ main.tsx
│  ├─ app.tsx
│  ├─ app.test.tsx
│  ├─ styles.css
│  └─ api/
│     ├─ schemas.ts
│     └─ client.ts
└─ tests/
   └─ workspace-smoke.spec.ts

src/evalops/workspace/
├─ __init__.py
├─ cli.py                          # lazy Workspace command adapter/startup
├─ models.py                       # WorkspaceRecord / registry contracts
├─ storage.py                      # root/registry/workspace metadata + atomic JSON writes
├─ security.py                     # bootstrap nonce + process-local session policy
└─ api/
   ├─ __init__.py
   ├─ models.py                    # /api/v1 request/response/error models
   └─ app.py                       # FastAPI app + security middleware/routes/static fallback

tests/workspace/
├─ test_cli.py
├─ test_storage.py
├─ test_security.py
└─ test_api.py

scripts/
├─ export_workspace_openapi.py
└─ run_workspace_e2e_server.py

.github/workflows/workspace-ci.yml
```

## Task 1: Add the optional Workspace dependency and CLI boundary

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/evalops/cli.py`
- Create: `src/evalops/workspace/__init__.py`
- Create: `src/evalops/workspace/cli.py`
- Create: `tests/workspace/test_cli.py`

**Interfaces:**

```python
# src/evalops/workspace/cli.py
def run_workspace_command(*, root: Path | None, port: int | None, open_browser: bool) -> int: ...
```

- [ ] Add failing CLI tests proving `evalops workspace --help` exists, accepts only `--root`, `--port`, `--no-open`, and has no `--host` option.
- [ ] Add a failing test that simulates missing Workspace dependencies and asserts a stable non-zero exit plus the actionable instruction `pip install "evalops-lab[workspace]"`; assert no traceback is printed.
- [ ] Run `pytest tests/workspace/test_cli.py -q` and confirm the new tests fail for the expected missing command/behavior.
- [ ] In `pyproject.toml`, add optional `workspace` dependencies with compatible bounded ranges: `fastapi>=0.116,<1`, `uvicorn>=0.35,<1`, `python-multipart>=0.0.20,<1`; add `httpx>=0.28,<1` to `dev` for HTTP test clients.
- [ ] Add the `workspace` argparse subcommand to `_build_parser()` with `--root Path`, `--port int`, and `--no-open`; do not import FastAPI/Uvicorn at module import time.
- [ ] Implement the CLI dispatch so the Workspace module is imported only when `args.command == "workspace"`; convert `ModuleNotFoundError` for Workspace-only packages into the actionable install error.
- [ ] Keep every existing CLI command path unchanged and run `pytest tests/workspace/test_cli.py -q` until green.
- [ ] Run representative legacy commands/tests that cover retrieval and evidence CLI dispatch.
- [ ] Commit: `feat(workspace): add optional workspace CLI boundary`.

## Task 2: Implement versioned workspace registry and crash-safe file storage

**Files:**
- Create: `src/evalops/workspace/models.py`
- Create: `src/evalops/workspace/storage.py`
- Create: `tests/workspace/test_storage.py`

**Interfaces:**

```python
WORKSPACE_REGISTRY_SCHEMA_VERSION = "workspace-registry-v1"
WORKSPACE_SCHEMA_VERSION = "workspace-v1"

class WorkspaceRecord(BaseModel):
    schema_version: Literal["workspace-v1"]
    workspace_id: str
    display_name: str
    created_at: datetime
    updated_at: datetime

class WorkspaceRegistry(BaseModel):
    schema_version: Literal["workspace-registry-v1"]
    workspace_ids: list[str]

class WorkspaceStore:
    def __init__(self, root: Path) -> None: ...
    def initialize(self) -> None: ...
    def list_workspaces(self) -> list[WorkspaceRecord]: ...
    def create_workspace(self, display_name: str) -> WorkspaceRecord: ...
    def get_workspace(self, workspace_id: str) -> WorkspaceRecord: ...
    def rename_workspace(self, workspace_id: str, display_name: str) -> WorkspaceRecord: ...
```

- [ ] Write failing tests for first-run root creation, empty registry creation, stable `workspace_id`, create/list/get/rename, display-name rename without identity change, duplicate/unknown IDs, unknown schema versions, and registry recovery after process restart.
- [ ] Write a failing test that injects a failed write and proves the previous canonical JSON file remains valid; no half-written `registry.json` or `workspace.json` may replace the prior state.
- [ ] Run `pytest tests/workspace/test_storage.py -q` and confirm failure.
- [ ] Implement safe workspace IDs using a server-generated opaque identifier (for example `ws-` + UUID4 hex); never derive the ID directly from display text.
- [ ] Implement `WorkspaceStore` so the root defaults are resolved by the caller, all paths are under `<root>/workspaces/<workspace_id>/`, and persisted models reject unsupported `schema_version` values.
- [ ] Implement a private `_atomic_write_json(path: Path, payload: Mapping[str, object])` using a same-directory temporary file, flush/close, and `os.replace`; ensure temporary files are cleaned on failure.
- [ ] Ensure registry ordering is deterministic (sort by stable ID or creation time consistently) and JSON serialization is deterministic enough for repeatable tests.
- [ ] Run `pytest tests/workspace/test_storage.py -q` until green.
- [ ] Run `ruff check src/evalops/workspace tests/workspace` and `mypy src/evalops/workspace`.
- [ ] Commit: `feat(workspace): add versioned local workspace storage`.

## Task 3: Implement bootstrap nonce, session, Host, and Origin security

**Files:**
- Create: `src/evalops/workspace/security.py`
- Create: `tests/workspace/test_security.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class WorkspaceOrigin:
    host: str
    port: int
    @property
    def http_origin(self) -> str: ...

class BootstrapSessionManager:
    def __init__(self, *, bootstrap_nonce: str | None = None) -> None: ...
    def consume_bootstrap_nonce(self, value: str) -> str: ...  # returns session id
    def validate_session(self, session_id: str) -> bool: ...
    def invalidate_all(self) -> None: ...

def validate_host_header(host_header: str, expected: WorkspaceOrigin) -> None: ...
def validate_mutating_origin(origin_header: str | None, expected: WorkspaceOrigin) -> None: ...
```

- [ ] Write failing tests for cryptographically random default nonce generation, one-time nonce consumption, nonce replay rejection, unknown session rejection, session invalidation, exact loopback Host acceptance, alternate Host rejection, exact Origin acceptance for mutating requests, missing/wrong Origin rejection, and rejection of `localhost` when the server origin was issued as `127.0.0.1` (no origin aliasing).
- [ ] Add a test proving session/nonce values never appear in exception messages or `repr()` output intended for logs.
- [ ] Run `pytest tests/workspace/test_security.py -q` and confirm failure.
- [ ] Implement using `secrets.token_urlsafe()` for bootstrap/session material; keep it process-local and never persist it to disk.
- [ ] Keep the expected origin exact: `http://127.0.0.1:<port>`.
- [ ] Implement errors as typed internal exceptions with safe public codes; do not include supplied secret material in messages.
- [ ] Run the security tests until green, then run Ruff/mypy for the module.
- [ ] Commit: `feat(workspace): enforce localhost session security`.

## Task 4: Build the authenticated FastAPI application and Workspace API shell

**Files:**
- Create: `src/evalops/workspace/api/__init__.py`
- Create: `src/evalops/workspace/api/models.py`
- Create: `src/evalops/workspace/api/app.py`
- Create/modify: `tests/workspace/test_api.py`
- Modify: `src/evalops/workspace/cli.py`

**API contract for 6.1:**

```text
POST  /api/v1/session/bootstrap
GET   /api/v1/session
GET   /api/v1/workspaces
POST  /api/v1/workspaces
GET   /api/v1/workspaces/{workspace_id}
PATCH /api/v1/workspaces/{workspace_id}
GET   /api/v1/health
```

- [ ] Write failing TestClient tests for bootstrap success, `HttpOnly; SameSite=Strict; Path=/` session cookie, replay rejection, unauthenticated API rejection, wrong Host/Origin rejection, safe JSON errors, create/list/get/rename workspace isolation, unknown workspace 404, and restrictive response headers.
- [ ] Assert `GET /api/v1/health` reveals no filesystem root, nonce, session ID, environment data, or server traceback.
- [ ] Assert mutating routes require exact Origin while read routes still require a valid session.
- [ ] Run `pytest tests/workspace/test_api.py -q` and confirm failure.
- [ ] Implement Pydantic request/response models with `extra="forbid"` and versioned response envelopes where persisted contracts are involved.
- [ ] Implement `create_workspace_app(store, session_manager, origin, static_dir)`; do not use global singleton state in tests.
- [ ] Add middleware/dependencies that validate Host for all requests, session for privileged `/api/v1` routes, and Origin for mutating routes.
- [ ] Add headers equivalent to `Content-Security-Policy: default-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'`, plus anti-framing and MIME-sniff protections. Adjust only if the actual Vite build requires a documented self-only directive.
- [ ] Map internal exceptions to safe structured responses `{ "error": { "code", "message", "field", "retryable" } }`; never serialize tracebacks.
- [ ] Serve an explicit `static_dir` when present and use SPA fallback for non-API GET routes; `/api/*` must never fall through to `index.html`.
- [ ] Implement `run_workspace_command()` to resolve the default root (`Path.home() / ".evalops"` only in product runtime), allocate/validate a loopback port, create nonce/session manager, start Uvicorn with host `127.0.0.1`, and open `/#bootstrap=<nonce>` unless `--no-open`.
- [ ] Ensure startup logging never prints the bootstrap fragment/token. It may print the safe base URL and a message that a browser was opened.
- [ ] Run API, CLI, storage, security tests until green.
- [ ] Commit: `feat(workspace): add authenticated localhost API shell`.

## Task 5: Extract shared Evidence tokens and create the Vite/React Workspace shell

**Files:**
- Create: `packages/evidence-ui/package.json`
- Create: `packages/evidence-ui/tokens.css`
- Modify: `apps/web/package.json`
- Modify: `apps/web/package-lock.json`
- Modify: `apps/web/src/app/globals.css`
- Create: `apps/workspace/package.json`
- Create: `apps/workspace/package-lock.json`
- Create: `apps/workspace/eslint.config.mjs`
- Create: `apps/workspace/tsconfig.json`
- Create: `apps/workspace/vite.config.ts`
- Create: `apps/workspace/vitest.config.ts`
- Create: `apps/workspace/index.html`
- Create: `apps/workspace/src/main.tsx`
- Create: `apps/workspace/src/app.tsx`
- Create: `apps/workspace/src/styles.css`
- Create: `apps/workspace/src/app.test.tsx`

- [ ] Before extraction, add/retain a Web Evidence Console regression check proving computed core CSS variables/classes used by current pages do not disappear after token relocation.
- [ ] Create `@evalops/evidence-ui` as a private **CSS-only** package in this slice. Move only stable root/dark color, spacing, radius, focus, and control variables from `apps/web/src/app/globals.css` into `packages/evidence-ui/tokens.css`; leave Tailwind theme bindings and app-specific utility classes in `apps/web`.
- [ ] Add `"@evalops/evidence-ui": "file:../../packages/evidence-ui"` to both app package manifests and regenerate both lockfiles. Do not introduce a root npm workspace in Phase 6.1.
- [ ] Run the existing `apps/web` lint/type/unit/build tests immediately after extraction; fix only regressions caused by token movement.
- [ ] Scaffold `apps/workspace` with React 19 / ReactDOM 19 / Zod 4 and Vite/TypeScript/Vitest/Testing Library/ESLint versions compatible with the already-installed Evidence Console ecosystem; commit the resolved lockfile.
- [ ] Write failing component tests for: persistent `LOCAL WORKSPACE` label, `Data stays on this machine`, unauthenticated bootstrap state, authenticated empty workspace list, create-workspace form, safe API error state, and no public/hosted wording.
- [ ] Implement the shell with semantic landmarks and accessible form labels. Use shared tokens but no copied public Evidence pages.
- [ ] Build to `apps/workspace/dist`; do not edit generated files manually and do not treat `dist` as source.
- [ ] Run `npm run lint && npm run typecheck && npm test && npm run build` from `apps/workspace`.
- [ ] Run full existing `apps/web` checks again.
- [ ] Commit: `feat(workspace): add local React workspace shell`.

## Task 6: Add the checked OpenAPI contract and authenticated frontend client

**Files:**
- Create: `scripts/export_workspace_openapi.py`
- Create: `apps/workspace/openapi.json`
- Create: `apps/workspace/src/api/schemas.ts`
- Create: `apps/workspace/src/api/client.ts`
- Modify: `apps/workspace/src/app.tsx`
- Modify: `apps/workspace/src/app.test.tsx`
- Modify: `tests/workspace/test_api.py`

- [ ] Add a failing Python test that exports `create_workspace_app(...).openapi()` and compares canonical JSON with `apps/workspace/openapi.json`; drift must fail CI.
- [ ] Implement `scripts/export_workspace_openapi.py` with `--check` and write modes; canonicalize key ordering/newline so generated diffs are deterministic.
- [ ] Generate and commit `apps/workspace/openapi.json` from the actual FastAPI app; do not hand-author it.
- [ ] Define Zod runtime schemas only for responses consumed by the 6.1 UI (`SessionInfo`, `WorkspaceSummary`, error envelope) and derive TypeScript types with `z.infer`.
- [ ] Implement `bootstrapSession(nonce)`, `listWorkspaces()`, `createWorkspace(displayName)`, and `renameWorkspace(...)` with `credentials: "same-origin"`; centralize error parsing.
- [ ] In the SPA startup, read `location.hash`, exchange `bootstrap=<nonce>`, immediately call `history.replaceState()` to remove the fragment, and never render/store/log the nonce after exchange.
- [ ] Add frontend tests proving the fragment is removed after success and API errors do not expose raw response bodies.
- [ ] Run Python API tests plus Workspace frontend unit/type tests.
- [ ] Commit: `feat(workspace): establish versioned local API contract`.

## Task 7: Prove the real same-origin browser security and restart-persistence path

**Files:**
- Create: `scripts/run_workspace_e2e_server.py`
- Create: `apps/workspace/playwright.config.ts`
- Create: `apps/workspace/tests/workspace-smoke.spec.ts`
- Modify: `apps/workspace/package.json`

- [ ] Create a test-only Python server harness that receives an E2E temp root and deterministic test bootstrap nonce through test-only CLI arguments/environment. Product `evalops workspace` must not expose a fixed-nonce option.
- [ ] Configure Playwright to test the **built Vite bundle served by the real FastAPI process**, not the Vite dev server.
- [ ] Write the browser scenario: open `/#bootstrap=<test nonce>` → nonce exchange → URL fragment disappears → create workspace → reload → workspace remains → rename → restart server with the same temp root → workspace remains.
- [ ] Add browser assertions that the page carries the local-only identity, no root horizontal overflow at 390px, and no external runtime requests. Fail the test on any request whose origin is not the test server origin.
- [ ] Add a cross-origin security probe from a separately created browser page/origin and assert privileged mutation is rejected.
- [ ] Add `@axe-core/playwright` and assert zero serious/critical violations on the Workspace Home/create flow; record any lower-severity issue rather than silently ignoring it.
- [ ] Run `npm run build && npm run test:e2e` from `apps/workspace` until green.
- [ ] Commit: `test(workspace): prove local shell security in browser`.

## Task 8: Add Workspace CI without changing branch governance yet

**Files:**
- Create: `.github/workflows/workspace-ci.yml`
- Modify if needed: `.github/dependabot.yml`

- [ ] Add a `Local Workspace CI` workflow with a stable job name `workspace` and least-privilege `contents: read`.
- [ ] Trigger on pull requests and on pushes affecting `apps/workspace/**`, `packages/evidence-ui/**`, `src/evalops/workspace/**`, `src/evalops/cli.py`, `pyproject.toml`, Workspace tests/scripts, or the workflow itself.
- [ ] Use the same immutable SHA-pinning policy as existing workflows.
- [ ] CI steps: Python setup; install `.[dev,workspace]`; Ruff Workspace/Python changes; mypy `src`; Workspace Python tests; Node 22; `npm ci`; lint; typecheck; unit; build; OpenAPI `--check`; install Chromium; Playwright E2E.
- [ ] Do **not** update ruleset `22385261` in this slice. The new context must first prove itself in a real PR.
- [ ] If Dependabot currently has no npm entry for `apps/workspace`, add a weekly npm entry while preserving grouped/noise-control policy.
- [ ] Run local YAML/static review and ensure no secrets/write permissions are introduced.
- [ ] Commit: `ci(workspace): add local workspace validation`.

## Task 9: Full regression and Phase 6.1 acceptance

**Files:**
- Review all Phase 6.1 changed files.
- Do not add implementation beyond this plan to make acceptance green.

- [ ] Run `python -m pip install -e ".[dev,workspace]"` in the isolated worktree environment.
- [ ] Run `ruff check .`.
- [ ] Run `ruff format --check .`.
- [ ] Run `mypy src`.
- [ ] Run full `pytest`.
- [ ] Run the existing CLI smoke paths, including retrieval evaluate and evidence export/index fixtures.
- [ ] Run the full `apps/web` gate: `npm ci`, lint, typecheck, unit tests, Storybook build/tests as currently required, static build, and Playwright E2E.
- [ ] Run the full `apps/workspace` gate: lint, typecheck, unit, build, OpenAPI check, Playwright E2E, axe.
- [ ] Verify `pip install -e .` (without `[workspace]`) still imports/runs non-Workspace CLI commands; `evalops workspace` must fail with the actionable extra-install message.
- [ ] Verify `evalops workspace --no-open --root <temp> --port <free-loopback-port>` binds only `127.0.0.1` and that a connection attempt via a non-loopback interface is unavailable.
- [ ] Search changed source/docs/log fixtures for secrets, bootstrap/session values, machine-local absolute paths, raw private data, TODO/FIXME/placeholders, and accidental `0.0.0.0` support.
- [ ] Confirm `apps/web` remains static/read-only and has no import/dependency on `src/evalops/workspace` or Workspace runtime assets.
- [ ] Request code review only after fresh gates pass. Address findings with the normal review workflow and rerun affected/full gates.
- [ ] Final commit if verification documentation itself changed: `docs(workspace): record Phase 6.1 verification`.

## Phase 6.1 Acceptance Contract

Phase 6.1 is accepted only when a clean source checkout can build `apps/workspace`, `evalops workspace` starts an authenticated loopback-only shell, workspace create/rename/reopen survives restart, the browser cannot bypass nonce/session/origin controls, no outbound runtime request is made, existing CLI/public Evidence Console behavior remains green, and the new Workspace CI has succeeded on its implementation PR. Retrieval inputs, jobs, metrics, comparisons, and exports remain intentionally out of scope until later slices.
