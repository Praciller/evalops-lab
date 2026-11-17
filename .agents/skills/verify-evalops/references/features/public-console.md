# Public Evidence Console

Prerequisites: an assembled `npm run build:pages` and Chromium as in the
[skill](../../SKILL.md). Open the routes below beneath `/evalops-lab`; for
automation run the existing
[Playwright spec](../../../../../apps/web/tests/e2e/evidence-console.spec.ts).
Open a direct link in a fresh tab to distinguish static route availability
from client navigation. Screenshot filenames below refer to captures made
by the spec in the scratch checkout, not the published README images.

## Overview

- Open `/`. Expect **Evidence Console**, a read-only fixture presentation,
  three approved runs and one comparison. Check `VERIFIED`,
  `SYNTHETIC_FIXTURE` and `INTEGRATION_ONLY` scope. In **Start here**, follow
  **Regression comparison** and **Record changes** to their detail routes.
  **Decision tests in CI** links to source; it does not run anything.
- Implementation: [page](../../../../../apps/web/src/app/page.tsx),
  [Overview](../../../../../apps/web/src/components/overview.tsx).
  Evidence: `overview-desktop.png`, `overview-mobile.png` and Playwright cases
  matching `overview is accessible|overview remains usable|start here links`.
  The tests check local requests and keyboard focus/390px overflow separately
  from visual baselines. Empty catalog presentation is covered at unit level.

## Regression comparison

- From **Start here** or `/comparisons/`, open
  `/comparisons/demo-retrieval-regression-v1/`. Expect **Regression detected**,
  `MATCHED`, reference `demo-retrieval-reference-v1`, candidate
  `demo-retrieval-fixture-v1`, four regression rows and one pass under the
  fixture policy. Follow the operand links and **Explore record changes**.
- Implementation: [detail route](../../../../../apps/web/src/app/comparisons/%5BartifactId%5D/page.tsx),
  [ComparisonDetail](../../../../../apps/web/src/components/comparison-detail.tsx),
  [Python regression policy](../../../../../src/evalops/regression/comparison.py).
  Evidence: `comparison-desktop.png`, `comparison-mobile.png` and the
  `comparison detail|comparison journey` cases. The exact metric decisions
  are covered by [generator tests](../../../../../tests/test_public_demo_evidence.py)
  and [policy tests](../../../../../tests/test_regression.py); invalid
  bundles and misleading scope fail at the repository boundary.

## Record change explorer

- Follow **Explore record changes** or open
  `/comparisons/demo-retrieval-regression-v1/failures/` directly. Expect
  **Record change explorer** and five matched records. Turn on **Changed
  records only**; `THQA-004` is an introduced failure and `THQA-005`
  remains a stable pass with metric changes. Turn it off and search for
  `THQA-002` to see an unchanged persistent category. A nonmatching query
  should show an empty state; the explorer's controls are local view state.
- Implementation: [route](../../../../../apps/web/src/app/comparisons/%5BartifactId%5D/failures/page.tsx),
  [FailureExplorer](../../../../../apps/web/src/components/failure-explorer.tsx),
  [transition logic](../../../../../apps/web/src/lib/evidence/transitions.ts).
  Evidence: `failure-explorer-desktop.png`, `failure-explorer-mobile.png` and
  Playwright cases matching `failure explorer|comparison journey`.
  [Component tests](../../../../../apps/web/tests/components.test.tsx) cover
  search, persistent categories, and unavailable evidence; the
  [transition tests](../../../../../apps/web/tests/transitions.test.ts) cover
  mismatched populations. The public fixture cannot display that mismatch.

## Runs and deep links

- In **Primary navigation**, open **Runs** and select **Verification** =
  `VERIFIED`, **Data kind** = `SYNTHETIC_FIXTURE`. Expect three rows at
  `/runs/?verification=VERIFIED&data=SYNTHETIC_FIXTURE`. Reload, clear filters,
  and use Back/Forward to verify URL state. Duplicate single-select values
  are ignored. In **Comparisons**,
  `/comparisons/?population=MATCHED&result=REGRESSION` yields one row.
- Direct-load `/runs/demo-retrieval-fixture-v1/`, the comparison detail and
  the explorer. From each use Overview, Runs, Comparisons and Storybook;
  verify the prefixed URL and destination content. The run detail shows
  `retrieval-fixture` and **No combined quality score**.
- Implementation: [Runs route](../../../../../apps/web/src/app/runs/page.tsx),
  [run detail](../../../../../apps/web/src/app/runs/%5BartifactId%5D/page.tsx),
  [Comparisons route](../../../../../apps/web/src/app/comparisons/page.tsx),
  [navigation](../../../../../apps/web/src/components/shell/primary-nav.tsx),
  [URL filters](../../../../../apps/web/src/lib/evidence/filters.ts).
  Evidence: `runs-filtered-desktop.png`, `run-detail-desktop.png` and the
  spec cases matching `run detail|navigates catalogs|opening detail pages
  directly|filters|duplicate single-select`. Unit tests cover safe empty
  catalogs. The spec's full navigation matrix opens the candidate run,
  comparison and explorer directly; other run pages have static-file checks.
  To verify the assembled server's negative path, request
  `/runs/unknown-artifact/` beneath `/evalops-lab` and expect HTTP 404.

## Public file boundary

- [Evidence index](../../../../../apps/web/public/evidence/index.json) explicitly
  lists the three runs and one comparison. The [read-only repository](../../../../../apps/web/src/lib/evidence/repository.ts)
  checks index membership and comparison consistency; the
  [strict schemas](../../../../../apps/web/src/lib/evidence/schemas.ts)
  enforce the [Public Evidence Contract](../../../../../docs/specs/public-evidence-contract-v1.md).
  The [generator](../../../../../scripts/generate_public_demo_evidence.py)
  uses checked-in fixtures and the export adapter, with no Workspace input.
- From the repo root run
  `python -m pytest tests/test_public_demo_evidence.py tests/test_public_evidence_export.py`;
  from `apps/web` run `npm test`. The checks cover deterministic
  source bytes, extra JSON artifacts, unsafe metadata, unknown fields, invalid
  claims and broken references. Then run the Pages output doctor from the repo
  root. It requires the exact evidence inventory, matches the assembled Next
  assets and Storybook against their build directories, and rejects unexpected
  files anywhere in `out/`, including beside valid route pages. It logs hashes
  of the served evidence JSON after all checks pass. `build:pages` verifies the
  12 curated public Storybook titles before copying the bundle.
- The doctor verifies filenames and copied bytes from a trusted local build.
  Use the generator, web schema tests and Storybook verifier for content checks.
  Inspect route output names after a Next upgrade or a new public route.
  Review any proposed addition to the `public/` inventory explicitly.
