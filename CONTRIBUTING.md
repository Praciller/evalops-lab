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

## Data and security rules

- Never commit API keys, tokens, credentials, `.env` files, or secret-bearing logs.
- Do not commit raw external datasets, model weights, private prompts/responses, or private evidence artifacts.
- Do not invent upstream licenses; verify provenance and licensing before adding external assets.
- Do not add external inference calls, paid infrastructure, hosted scanners, auth, persistence, analytics, or provider credentials to local tests.
- Do not add unsupported benchmark, production-performance, or model-superiority claims.

For undisclosed security vulnerabilities, follow [SECURITY.md](SECURITY.md) instead of opening a public issue.
