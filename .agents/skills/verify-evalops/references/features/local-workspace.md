# Local Evaluation Workspace

Use the [skill](../../SKILL.md) to build Vite and start the existing Playwright
driver. The source harness runs at `http://127.0.0.1:18234/` with a temporary
store. The [clean wheel verifier](../../../../../scripts/verify_workspace_wheel.py)
starts the real CLI on a free loopback port with a separate temporary store.
Use only the synthetic test inputs. See the [Workspace trust guide](../../../../../docs/local-workspace.md).

| Journey and route | Action and result | Implementation and existing proof |
| --- | --- | --- |
| Local identity at `/`; `/workspaces/:id/inputs` | Bootstrap, create a workspace, upload matching JSONL ground truth and predictions (or use guided CSV). Expect **LOCAL WORKSPACE** and validated inputs. | [React shell](../../../../../apps/workspace/src/app.tsx), [Inputs](../../../../../apps/workspace/src/pages/WorkspaceInputs.tsx), [FastAPI app](../../../../../src/evalops/workspace/api/app.py); [workspace-smoke](../../../../../apps/workspace/tests/workspace-smoke.spec.ts) and [csv-import](../../../../../apps/workspace/tests/csv-import.spec.ts). |
| `/workspaces/:id/runs` → `/jobs/:jobId` → `/workspaces/:id/runs/:runId` | Choose inputs, set top K to 2, select **Validate & review** and **Run Evaluation**. Wait for `COMPLETE`, open **View evaluation result**, and reload. Expect unchanged metrics and **LOCAL EVIDENCE — Not published**. | [Routes](../../../../../apps/workspace/src/routes.tsx), [run service](../../../../../src/evalops/workspace/application/runs.py); [retrieval happy path](../../../../../apps/workspace/tests/retrieval-happy-path.spec.ts) covers reload, axe and three widths. [Failure paths](../../../../../apps/workspace/tests/retrieval-failure-paths.spec.ts) cover mutated inputs, cancellation without result/provenance, restart interruption and retry with a new job ID. |
| `/workspaces/:id/comparisons/:comparisonId` and `/failures` beneath that route | Compare completed reference and candidate from the same population; inspect private record transitions. Incompatible top K or ground truth blocks canonical comparison; exploratory mode cannot promote. | [Comparison detail](../../../../../apps/workspace/src/pages/ComparisonDetail.tsx), [Failures](../../../../../apps/workspace/src/pages/FailuresPage.tsx), [comparison service](../../../../../src/evalops/workspace/application/comparisons.py); [compatible](../../../../../apps/workspace/tests/comparison-happy-path.spec.ts) and [incompatible](../../../../../apps/workspace/tests/comparison-incompatible.spec.ts) browser cases. |
| `/workspaces/:id/exports` | Preview a completed run or canonical comparison, select synthetic classification, then confirm against a scratch directory. Expect sanitized output classified `SYNTHETIC_FIXTURE` / `INTEGRATION_ONLY` and separate private history. Preview alone writes no public files. | [Exports](../../../../../apps/workspace/src/pages/ExportsPage.tsx), [export service](../../../../../src/evalops/workspace/application/exports.py); [run export](../../../../../apps/workspace/tests/export-run.spec.ts) checks hashes and tamper rejection; [comparison export](../../../../../apps/workspace/tests/export-comparison.spec.ts) checks the four-file bundle and exploratory rejection. [Python write tests](../../../../../tests/workspace/test_export_write.py) cover expiry, unsafe destinations, no overwrite and stage cleanup. |

Run `npm run test:e2e` from `apps/workspace` or pass a linked spec filename
after `--`. Retain the per-case runner result and wheel hash/verification log.
The [packaged browser spec](../../../../../apps/workspace/tests/packaged-workspace.spec.ts)
runs through the wheel verifier's `--browser` option, with no source harness
or default user store. Check the [public boundary](public-console.md#public-file-boundary)
separately: a Workspace export stays local and cannot add a public Console
route or allowlist entry.

Limits: the suite exercises local sessions and run-result reload, not public
access to private routes or a deployed service. Public routes have a separate
direct-navigation matrix. Windows can skip symlink cases when the test process
lacks that OS privilege; report the skips.
