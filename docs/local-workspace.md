# Local Evaluation Workspace

The Local Evaluation Workspace is the second product surface of EvalOps Lab. It is an **interactive, localhost-only Python application** for experimenting with private evaluation inputs. The [Live Evidence Console](https://praciller.github.io/evalops-lab/) remains the primary public/recruiter entry point; its checked-in evidence is static, sanitized and read-only.

| Surface | Execution | Evidence and audience |
| --- | --- | --- |
| [Live Evidence Console](https://praciller.github.io/evalops-lab/) | Hosted GitHub Pages static site; no evaluator or API runtime | Explicitly allowlisted, sanitized public evidence; recruiter/reviewer read-only |
| Local Evaluation Workspace | Local Python/FastAPI server bound to `127.0.0.1` | Interactive private inputs, deterministic evaluations, comparison/failure analysis, explicitly confirmed sanitized exports |
| CLI | Local Python command-line tools | Reproducible validation/evaluation/benchmark/regression workflows; no hosted inference implied |

**There is no synchronization or automatic publication between these surfaces.** Installing or running Workspace does not publish anything to GitHub, Pages, or the public evidence directory.

## Current packaging status

Phase 6.4 builds and verifies an installable **candidate wheel** from source. The historical `v0.1.0` tag/release is unchanged and must not be treated as the Phase 6 Workspace release.

After Phase 6 acceptance and separate owner approval, the intended public install command will be:

```bash
pip install "evalops-lab[workspace]"
evalops workspace
```

**Until that release is approved and published, use the source checkout or a freshly built candidate wheel** instead of assuming the published package includes the Workspace UI.

## Start from a source checkout

Requires Python 3.11 or newer and Node.js 22 for the **build**, not for running an installed wheel.

```bash
python -m pip install -e ".[dev,workspace]"
cd apps/workspace
npm ci
npm run build
cd ../..
python scripts/stage_workspace_assets.py
evalops workspace
```

The browser opens a private one-time bootstrap URL. For explicit control over the local root and port:

```bash
evalops workspace --no-open --root ./local-workspace-data --port 18234
```

`--no-open` prints the bootstrap URL instead of opening a browser. Treat that URL as a short-lived local secret: do not paste it in issues, logs or screenshots. The server binds to **`127.0.0.1` only**; no `0.0.0.0`/LAN option, provider credentials, external model calls, analytics or telemetry are part of this local runtime. The default private root is `~/.evalops`.

## Build and test a clean-install wheel

Run these from the repository root after building and staging Vite assets:

```bash
python -m build --wheel
python -m pytest tests/workspace/test_package_smoke.py -q
python scripts/verify_workspace_runtime_boundary.py --wheel dist/evalops_lab-0.1.0-py3-none-any.whl
python scripts/verify_workspace_wheel.py dist/evalops_lab-0.1.0-py3-none-any.whl --browser
```

These are candidate build commands, not release/publishing commands. The verification installs `[workspace]` in a clean virtual environment outside the checkout, launches the installed Python server, checks packaged UI content and loopback-only browser behavior, exercises a synthetic evaluation/export, and verifies restart persistence. **An installed wheel needs Python but does not need Node.js at runtime.** Node is used only by the separate optional Playwright verification process.

The installed static assets are generated from `apps/workspace` and staged under `src/evalops/workspace/static`. Edit the frontend source, never generated staged assets directly.

## Local workflow and evidence boundaries

1. Create a local Workspace. Register validated retrieval ground truth and predictions as JSONL, or use the guided CSV import supported by the UI. Import and reference paths remain local; external data files and raw rows are not public evidence.
2. Configure and run the deterministic retrieval evaluation. The local job worker processes work in the selected root. Finished artifacts persist; an interrupted/in-flight job is **not** silently represented as complete after restart.
3. Choose a completed run or a canonical, same-population comparison; inspect aggregate metrics and, where available, private per-query failure transitions. An `EXPLORATORY_ONLY` comparison is useful for local inspection but is **not** eligible for public regression export.
4. To export, enter an explicit verification status, permitted data kind and limitations. Workspace derives `SYNTHETIC_FIXTURE → INTEGRATION_ONLY` or `CURATED_DATASET → PROTOCOL_SPECIFIC`; this path cannot assert `OFFICIAL_BENCHMARK/BENCHMARK_RESULT` by itself. Local completion does not automatically mean `VERIFIED`.
5. Review the sanitized **Included / Removed / Transformed / Output files** preview. The existing Public Evidence Contract adapter/serializer determines which fields are allowed. Enter an explicit existing destination directory, then confirm in a **separate action**. Workspace writes a non-overwriting run JSON or a validated four-file comparison bundle, with a local private manifest. A preview alone never creates a public artifact.

Exports stay local even when a filename resembles a public artifact. There is **no Publish button**, GitHub API write, Git commit/push, or Pages deploy action. To promote an exported artifact later, the owner must follow the independent checked-in Public Evidence Contract/index validation and normal PR review process.

## Validation and troubleshooting

```bash
ruff check .
ruff format --check .
mypy src
pytest
cd apps/workspace
npm run lint
npm run typecheck
npm test
npm run build
npm run test:e2e
```

Workspace CI also runs source browser, accessibility/no-external-network tests, exact bundle integrity checks, staged/wheel runtime-boundary scanning, clean-wheel install and packaged browser E2E. The public console has its **separate** Web/Storybook/Pages checks. None of these checks imply permission to publish private files.

If the installed command reports missing UI assets, rebuild `apps/workspace`, restage the assets, rebuild the wheel and rerun the clean-wheel verifier. Do not manually patch files under `src/evalops/workspace/static` or bypass an asset SHA mismatch.

## Owner-gated future release

A future **`v0.2.0 — Local Evaluation Workspace`** is a separate action after Phase 6.4 merge, full Python/Workspace/public regression gates, clean-wheel and no-network acceptance on the final `main` SHA, documented limitations and explicit owner approval. Do **not** create, move or repoint `v0.1.0`, change package version, publish to PyPI or deploy Workspace as part of documentation or implementation PRs.
