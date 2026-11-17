---
name: verify-evalops
description: Reproduce EvalOps Lab reviewer journeys in the local GitHub Pages build and the private Workspace, and retain evidence for navigation, evaluation failures, and the public artifact boundary.
---

# Verify EvalOps Lab

Use the [feature map](references/features/README.md) to select journeys and
report each as passed, failed, or blocked. The Pages console renders the
checked-in synthetic fixtures; the Workspace runs deterministic evaluations on
test inputs in a separate loopback instance. Neither flow publishes anything.

## Launch and doctor

1. From the repo root, record `git status --short --branch`, `git rev-parse HEAD`,
   Python, Node and OS versions. Use a disposable checkout of the target revision
   for browser runs: the existing public suite writes full-page PNGs into tracked
   `docs/screenshots/evidence-console/`. For committed changes, use
   `git worktree add --detach <scratch-checkout> <target-sha>`. For uncommitted
   changes, copy only the intended changes there and record that diff. Run the
   commands below against that checkout. Create a separate evidence directory
   outside the checkout and any public tree before running commands.
2. Use Python 3.12 (required by the Pages doctor) and Node 22 to match CI.
   In the scratch checkout create and activate a venv (`python -m venv .venv`),
   then run
   `python -m pip install -e ".[dev,workspace]"`. In each app under test run
   `npm ci` and `npx --no-install playwright install chromium` (add `--with-deps`
   on Linux when browser system dependencies need provisioning). Keep the venv on
   PATH: the Workspace harness launches `python`.
3. Check the relevant loopback ports are free before starting: Pages uses 4174
   (4173 for the plain web export), Workspace source E2E uses 18234. On Windows,
   use `Get-NetTCPConnection -State Listen -LocalPort 4173,4174,18234`; on Linux,
   inspect `ss -ltn`. A busy port is a blocker; do not reuse or stop a foreign
   process. Clear any inherited `PORT` override before Pages E2E.
4. In `apps/web`, run `npm run build:pages`; in `apps/workspace`, run
   `npm run build`. The Pages build must create app routes under `out/` and pass
   public Storybook validation; the Workspace source driver requires
   `dist/index.html`. From the repo root run
   `python .agents/skills/verify-evalops/scripts/check_pages_output.py` after
   the Pages build in that same checkout. Keep `out/`, `.next/static/` and
   `storybook-public-static/` from the same build. The doctor checks the
   assembled file inventory, compares copied files by byte and records public
   JSON SHA-256 values. The Python generator and web schema tests establish
   the provenance and validity of the evidence JSON.

## Drive and record

- **Public:** from `apps/web`, use `npm run test:e2e:pages` for the existing
  Pages suite, including the `/evalops-lab/` prefix and curated Storybook.
  Its wrapper does not forward runner flags. For a targeted run, set
  `PAGES_MODE=true` (`export PAGES_MODE=true` in Bash or
  `$env:PAGES_MODE = 'true'` in PowerShell), then use
  `npm run test:e2e -- --grep "<test name>"`.
  Playwright owns the server and waits for HTTP readiness at
  `http://127.0.0.1:4174/evalops-lab/`. For manual checks, set the same mode
  and run `npm run start:pages` in a dedicated terminal instead. Wait for
  its listening message and HTTP 200 at that URL; stop it before using
  the Playwright driver. A plain export (`npm run build` then
  `npm run test:e2e` with `PAGES_MODE` unset) overwrites `out/` and omits the
  Pages prefix and public Storybook; rebuild Pages before using its doctor.
- **Private:** from `apps/workspace`, use `npm run test:e2e` after building.
  Playwright starts the test supervisor, waits for HTTP at
  `http://127.0.0.1:18234/`, and drives canned JSONL/CSV inputs. The fixed test
  nonce, injected worker gate, and restart controls belong to that harness.
  Run the [clean wheel path](../../../docs/local-workspace.md#build-and-test-a-clean-install-wheel)
  to check the actual packaged CLI, loopback binding, sanitized export and
  restart persistence. Use synthetic input and a fresh private temporary root.
- **Quality gates:** from the root run `python -m pytest -ra`,
  `python -m ruff check .`, `python -m ruff format --check .`, and
  `python -m mypy src`. In each app run `npm run lint`, `npm run typecheck`,
  and `npm test`. For Storybook interactions use `npm run storybook:test` in
  `apps/web`. For Workspace schema drift use
  `python scripts/export_workspace_openapi.py --check`. Use the repo
  [workflows](../../../.github/workflows/) for full artifact/release checks.
  For changes to the doctor itself run
  `python -m pytest -ra .agents/skills/verify-evalops/tests` and run the doctor
  against a fresh `npm run build:pages` export.
- Set `CI=1` for the browser runs to require a newly started Playwright
  server. To retain an HTML report, run Playwright directly with
  `--reporter=list,html --retries=0` after `npm run test:e2e --`; keep the
  relevant mode variable set and point `PLAYWRIGHT_HTML_OUTPUT_DIR` at a
  dedicated directory outside the checkout. Save each command's output and
  exit code there. If a drive fails, check whether the runner started and
  reached its own server before diagnosing product behavior. Distinguish
  failed assertions, tests skipped by the platform, and commands not run.
  For visual checks use Chromium on Linux, the CI comparison environment.
  Record Windows visual failures separately and keep the diff images. Keep
  the checked-in screenshot expectations during verification. See the
  [observed platform results](references/features/README.md#observed-platform-results).

## Clean up

Copy the synthetic screenshots or failure diffs you need and retain logs,
reports, hashes, and route results in the evidence directory. Keep private
exports, session URLs/cookies and private data out of shared evidence.
Confirm Playwright's owned ports stop listening after each run; the Workspace
harness and wheel verifier own their temporary roots. Abrupt termination can
leave a synthetic temp root: before removing one, verify it belongs to this
run. Inspect scratch `git status` first and remove only the disposable
checkout you created. After saving evidence, return only the spec's
regenerated scratch PNGs to their original bytes, then use
`git worktree remove <scratch-checkout>` without forcing it.
Verify retained logs still exist after cleanup. Leave the working checkout and
public artifacts unchanged.
