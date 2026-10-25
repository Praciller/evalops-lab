# Contributing to EvalOps Lab

EvalOps Lab is a testing-first framework for reproducible AI reliability evaluation. Contributions should preserve the distinction between evaluation truth, sanitized public evidence, and recruiter-facing presentation.

## Development setup

Use Python 3.11 or newer and Node.js 22 for the Evidence Console.

```text
python -m pip install -e ".[dev]"
pytest
ruff check .
ruff format --check .
mypy src

cd apps/web
npm ci
npm run lint
npm run typecheck
npm test
npm run build
```

The reproducibility contract and deeper evaluation commands are documented in [docs/reproducibility.md](docs/reproducibility.md). Repository architecture and operating boundaries are documented in [AGENTS.md](AGENTS.md).

## Contribution flow

1. Start from the current `main` branch in a scoped feature branch.
2. Make the smallest deterministic, testable change that addresses one issue.
3. Run the applicable Python, CLI, web, accessibility, Storybook, and static-build checks.
4. Open a pull request using the repository template and link the issue.
5. Resolve CI failures and review conversations on the same branch.
6. Merge through the repository's approved pull-request flow using a squash merge.

Normal contributors do not create release tags. Milestone releases are created only through an explicitly accepted release task.

## Evaluation and metric changes

Evaluation behavior is a public contract. Metric or evaluator semantic changes must be explicit, documented, and covered by manually verifiable tests and regression tests where practical. Do not silently change formulas, thresholds, ground truth, failure classifications, or benchmark interpretation to improve a result.

Deterministic evaluation is preferred when it is sufficient. Keep human labels, system outputs, and model-generated judge outputs separate. Synthetic fixtures must remain clearly labeled and must not be presented as official benchmark evidence.

## Public evidence boundary

The public Evidence Console is a static, read-only surface. Public export must remain strict and fail closed. Do not expose raw prompts, responses, corpus text, hidden reasoning, private artifacts, local paths, credentials, or other private evaluation material. Preserve `SYNTHETIC_FIXTURE`, `INTEGRATION_ONLY`, `VERIFIED`, `PARTIAL`, `UNVERIFIED`, and `NOT_RUN` semantics. `INTEGRATION_ONLY` and synthetic evidence do not establish real-world model superiority or official benchmark results.

## Frontend changes

UI changes require the relevant evidence, not only a successful local render:

```text
npm run lint
npm run typecheck
npm test
npm run storybook:build
npm run storybook:build:public
node scripts/verify-public-storybook.mjs
npm run build
npm run test:e2e
npm run build:pages
npm run test:e2e:pages
```

Include accessibility/axe coverage, representative mobile overflow checks, and reviewed screenshots when the visual surface changes. Keep the public Storybook allowlist and static-export boundaries intact.

## Local Workspace changes

The interactive Workspace is a **private localhost application**, separate from
the public Evidence Console and its Storybook. For its source code, install the
optional dependencies and run its own gates:

```bash
python -m pip install -e ".[dev,workspace]"
ruff check .
ruff format --check .
mypy src
pytest
cd apps/workspace
npm ci
npm run lint
npm run typecheck
npm test
npm run build
npm run test:e2e
cd ../..
python scripts/export_workspace_openapi.py --check
python scripts/stage_workspace_assets.py
python -m build --wheel
python scripts/verify_workspace_runtime_boundary.py --wheel dist/evalops_lab-0.1.0-py3-none-any.whl
python scripts/verify_workspace_wheel.py dist/evalops_lab-0.1.0-py3-none-any.whl --browser
```

The wheel filename above refers to the **current candidate version**, not an
approved `v0.2.0` release. The installed runtime must work outside the checkout
on `127.0.0.1`, without Node.js, external provider calls or public writes.
The separate Playwright verification process may use Node.

**Generated assets rule:** edit `apps/workspace`, never hand-edit
`src/evalops/workspace/static`. Rebuild Vite, stage the checked output, and
verify both package and browser flows. Keep OpenAPI schemas synchronized with
Workspace API changes; do not loosen data/claim-scope policy to make tests pass.

Exports must remain two-step, owner-classified, non-overwriting, and sanitized
through the existing Public Evidence Contract. `EXPLORATORY_ONLY` comparisons
cannot become public regression claims. Never add implicit Pages/GitHub
publication, private local path or raw input leakage, LAN binding, telemetry
or hosted model inference. See [Local Workspace](docs/local-workspace.md).

## Data and security rules

- Never commit API keys, tokens, credentials, `.env` files, or secret-bearing logs.
- Do not commit raw external datasets, model weights, private prompts/responses, or private evidence artifacts.
- Do not invent upstream licenses; verify provenance and licensing before adding external assets.
- Do not add external inference calls, paid infrastructure, hosted scanners, auth, persistence, analytics, or provider credentials to local tests.
- Do not add unsupported benchmark, production-performance, or model-superiority claims.

For undisclosed security vulnerabilities, follow [SECURITY.md](SECURITY.md) instead of opening a public issue.
