# Phase 5A.2 Evidence Console Product Adoption Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for this repository. Do not use subagent-driven-development unless the owner explicitly requests delegation. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adopt the Phase 5A.1 Evidence Design System across the production Evidence Console, add a lightweight product shell plus `/runs/` and `/comparisons/` indexes, and implement deterministic URL-driven client filtering without changing evidence truth.

**Architecture:** Build-time repository functions continue to load and validate the explicit public evidence allowlist. Static index pages pass validated public summaries/bundles into small client catalog components; URL query parameters control only presentation filters. Shared shell and evidence patterns replace page-local styling while the Python/public evidence contract, regression logic, comparison bundle validation, and Failure Explorer transitions remain unchanged.

**Tech Stack:** Next.js 16.3.4 static export, React 19.2.8, TypeScript, Tailwind CSS 4.3.3 semantic tokens, Phase 5A.1 local primitives/evidence patterns, Zod public evidence contract, Vitest/Testing Library, Playwright + axe, GitHub Pages.

**Spec:** `docs/superpowers/specs/2026-09-06-phase-5a-evidence-design-system-storybook-design.md`

## Global Constraints

- Phase 5A.1 must already be merged and production-verified before starting 5A.2.
- Keep the application static/read-only; no API/server action/database/auth/persistence/analytics/inference additions.
- URL filters are presentation state only and may never override artifact fields or manufacture evidence labels.
- Unknown/malformed filter values are ignored safely; they must not crash the page or become arbitrary labels.
- Different filter dimensions use AND semantics.
- Refresh and browser back/forward must reproduce valid filter state from the URL; do not use LocalStorage.
- Preserve `SYNTHETIC_FIXTURE` + `INTEGRATION_ONLY`, verification status, population compatibility, aggregate regression policy, and Failure Explorer transition semantics.
- Never infer a record-level regression policy from metric deltas.
- 390px root-page horizontal overflow is forbidden; comparison tables may retain intentional internal scroll.
- No visual polish may amplify claims into benchmark/model-superiority language.
- Storybook remains a static documentation surface under `/storybook/`, not a Next route or backend service.

---

## File Structure

Create:
- `apps/web/src/lib/evidence/catalog.ts` â€” minimal public catalog view models derived from the validated index/bundles without serializing full run evidence into index pages.
- `apps/web/src/lib/evidence/filters.ts` â€” pure query parsing, serialization, and filtering over catalog view models.
- `apps/web/tests/filters.test.ts` â€” deterministic catalog/query/filter tests.
- `apps/web/src/components/shell/primary-nav.tsx` â€” client active-route navigation.
- `apps/web/src/components/shell/product-header.tsx` â€” product identity, nav, Storybook link, theme control.
- `apps/web/src/components/catalog/filter-bar.tsx` â€” accessible filter controls and active-filter summary.
- `apps/web/src/components/catalog/run-catalog.tsx` â€” client run catalog driven by URL filters.
- `apps/web/src/components/catalog/comparison-catalog.tsx` â€” client comparison catalog driven by URL filters.
- `apps/web/src/app/runs/page.tsx` â€” static Runs index.
- `apps/web/src/app/comparisons/page.tsx` â€” static Comparisons index.

Modify:
- `apps/web/src/components/evidence-layout.tsx` â€” adopt lightweight product shell without changing error boundary semantics.
- `apps/web/src/components/overview.tsx` â€” use product patterns and add clear index entry points.
- `apps/web/src/components/run-detail.tsx` â€” adopt shared evidence/table/metric patterns.
- `apps/web/src/components/comparison-detail.tsx` â€” adopt shared regression/comparison patterns.
- `apps/web/src/components/failure-explorer.tsx` â€” adopt shared filter/table/state patterns while preserving existing transition derivation.
- `apps/web/src/components/evidence-table.tsx` and `metric-card.tsx` â€” compatibility wrappers or migration to Phase 5A.1 primitives/patterns; remove duplicate styling logic.
- `apps/web/tests/components.test.tsx` â€” shell/catalog/page component behavior.
- `apps/web/tests/e2e/evidence-console.spec.ts` â€” navigation, indexes, filtering, back/forward, theme, keyboard, mobile, axe, network boundaries.
- `apps/web/tests/e2e/__screenshots__/*` â€” intentional Phase 5A.2 visual baselines.
- `.github/workflows/pages.yml` â€” static assertions for `/runs/index.html`, `/comparisons/index.html`, and Storybook coexistence.
- `README.md` / `DEPLOY.md` â€” only after fresh production verification.

---

### Task 1: Add pure, fail-safe URL filter contracts

**Files:**
- Create: `apps/web/src/lib/evidence/catalog.ts`
- Create: `apps/web/src/lib/evidence/filters.ts`
- Create: `apps/web/tests/filters.test.ts`

**Interfaces:**
- Consumes: `PublicArtifactSummary`, `ComparisonBundle`, and schema-derived evidence unions.
- Produces minimal view models in `catalog.ts` plus pure filter helpers:
```ts
export type RunCatalogItem = {
  artifact_id: string;
  run_id: string | null;
  dataset_name: string | null;
  evaluation_type: string | null;
  verification_status: PublicArtifactSummary["verification_status"];
  data_kind: PublicArtifactSummary["data_kind"];
  claim_scope: PublicArtifactSummary["claim_scope"];
  metrics: Record<string, number>;
};

export type ComparisonResultFilter = "PASS" | "REGRESSION";
export type ComparisonCatalogItem = {
  artifact_id: string;
  baseline_artifact_id: string;
  candidate_artifact_id: string;
  verification_status: PublicArtifactSummary["verification_status"];
  data_kind: PublicArtifactSummary["data_kind"];
  claim_scope: PublicArtifactSummary["claim_scope"];
  population_compatibility: "MATCHED" | "UNVERIFIED" | "INCOMPATIBLE";
  result: ComparisonResultFilter | null;
  regression_count: number;
};

export type FilterKey = "verification" | "data" | "scope" | "population" | "result";
export type RunFilterState = {
  verification?: RunCatalogItem["verification_status"];
  data?: RunCatalogItem["data_kind"];
  scope?: RunCatalogItem["claim_scope"];
};
export type ComparisonFilterState = RunFilterState & {
  population?: ComparisonCatalogItem["population_compatibility"];
  result?: ComparisonResultFilter;
};

export function deriveComparisonResult(bundle: ComparisonBundle): ComparisonResultFilter | null;
export function getRunCatalogItems(): RunCatalogItem[];
export function getComparisonCatalogItems(): ComparisonCatalogItem[];
export function parseRunFilters(params: URLSearchParams): RunFilterState;
export function parseComparisonFilters(params: URLSearchParams): ComparisonFilterState;
export function withFilter(params: URLSearchParams, key: FilterKey, value: string | null): string;
export function matchesRunFilters(item: RunCatalogItem, filters: RunFilterState): boolean;
export function matchesComparisonFilters(item: ComparisonCatalogItem, filters: ComparisonFilterState): boolean;
```
`getRunCatalogItems()` preserves the explicit public index order. `getComparisonCatalogItems()` preserves comparison index order and derives result/regression count only from an already validated `ComparisonBundle`; it returns no record-level evidence.

- [ ] **Step 1: Write the complete filter tests first**

Cover:
```ts
expect(parseRunFilters(new URLSearchParams("verification=VERIFIED&data=SYNTHETIC_FIXTURE")))
  .toEqual({ verification: "VERIFIED", data: "SYNTHETIC_FIXTURE" });
expect(parseRunFilters(new URLSearchParams("verification=SUPER_VERIFIED"))).toEqual({});
expect(parseComparisonFilters(new URLSearchParams("population=MATCHED&result=REGRESSION")))
  .toEqual({ population: "MATCHED", result: "REGRESSION" });
```
Also test AND semantics, duplicate values, clear-one, clear-all serialization, and preservation of unrelated supported query keys. Because Phase 5A.2 filters are single-select per dimension, any key with zero or more than one raw value is ignored rather than guessed; a later multi-select phase must define a new contract explicitly.

- [ ] **Step 2: Add minimal catalog-view-model and safe comparison-result tests**

Assert a run catalog item contains only summary-safe fields and does not contain `evidence`, `failures`, retrieved IDs, relevant IDs, scores, raw text, or record transitions. For comparisons define only:
```text
passed === true -> PASS
passed === false AND at least one metric status === REGRESSION -> REGRESSION
otherwise -> null
```
Test that a future MISSING-only comparison does not get mislabeled as REGRESSION and that the comparison catalog item exposes only IDs, claim dimensions, compatibility, result, and regression count.

- [ ] **Step 3: Run tests and verify missing module failure**

```bash
npm test -- filters.test.ts
```
Expected: FAIL because `lib/evidence/filters.ts` does not exist.

- [ ] **Step 4: Implement minimal catalog projection plus filters with explicit allowlists**

In `catalog.ts`, build run items from `getEvidenceIndex().artifacts.filter(artifact_type === "run")` without loading/serializing full run artifacts. Build comparison items from `getApprovedComparisonBundles(index)` and project only the catalog fields above; this preserves the explicit index order while keeping full run/comparison objects server-side. In `filters.ts`, use immutable arrays/Sets of supported enum literals; never echo unknown query text into UI. Parsing a single-select key first requires `params.getAll(key).length === 1`; otherwise ignore that dimension. `withFilter()` clones `URLSearchParams`, deletes all existing occurrences of the typed key, optionally sets one supported value, and returns canonical `params.toString()`.

- [ ] **Step 5: Run focused tests and static checks**

```bash
npm test -- filters.test.ts
npm run typecheck
npm run lint
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/lib/evidence/catalog.ts apps/web/src/lib/evidence/filters.ts apps/web/tests/filters.test.ts
git commit -m "feat: add evidence catalog filter contracts"
```

### Task 2: Replace the header with a lightweight product shell

**Files:**
- Create: `apps/web/src/components/shell/primary-nav.tsx`
- Create: `apps/web/src/components/shell/product-header.tsx`
- Modify: `apps/web/src/components/evidence-layout.tsx`
- Modify/Test: `apps/web/tests/components.test.tsx`

**Interfaces:**
- `PrimaryNav({ storybookHref }: { storybookHref: string })` uses `usePathname()` for app route state and a normal `<a>` for Storybook.
- `ProductHeader({ storybookHref }: { storybookHref: string })` composes product identity, nav, and ThemeToggle.
- `EvidenceLayout` computes `storybookHref` server-side from `process.env.GITHUB_PAGES === "true" ? "/evalops-lab/storybook/" : "/storybook/"` and passes it down.

- [ ] **Step 1: Write shell tests first**

Mock `usePathname()` and test:
```text
/ -> Overview aria-current=page
/runs/... -> Runs aria-current=page
/comparisons/... -> Comparisons aria-current=page
```
Assert Storybook uses a plain anchor to the supplied static URL, all four nav labels exist, theme control remains accessible, and footer claim-boundary text remains present.

- [ ] **Step 2: Run focused tests and confirm missing shell modules fail**

```bash
npm test -- components.test.tsx
```
Expected: FAIL on missing shell imports.

- [ ] **Step 3: Implement `PrimaryNav` using route-prefix semantics**

Use exact `/` for Overview and prefix matches for Runs/Comparisons. Apply active styling plus `aria-current="page"`; never rely on color alone. Storybook is never marked as a Next active route.

- [ ] **Step 4: Implement responsive ProductHeader and refactor EvidenceLayout**

Keep a horizontal desktop shell and a wrap/disclosure-friendly 390px layout. Do not add a sidebar. Preserve footer text `Public Evidence Contract V1 Â· explicit allowlist` and `No runtime API Â· no inference Â· no raw corpus`.

- [ ] **Step 5: Verify tests, keyboard DOM semantics, and build**

```bash
npm test -- components.test.tsx
npm run typecheck
npm run lint
npm run build
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/components/shell apps/web/src/components/evidence-layout.tsx apps/web/tests/components.test.tsx
git commit -m "feat: add lightweight Evidence Console shell"
```

### Task 3: Build the static `/runs/` catalog with URL-driven filters

**Files:**
- Create: `apps/web/src/components/catalog/filter-bar.tsx`
- Create: `apps/web/src/components/catalog/run-catalog.tsx`
- Create: `apps/web/src/app/runs/page.tsx`
- Modify/Test: `apps/web/tests/components.test.tsx`
- Modify/Test: `apps/web/tests/filters.test.ts`

**Interfaces:**
- Server page calls `getRunCatalogItems()` only; no full run evidence array crosses into the client bundle.
- `RunCatalog({ runs }: { runs: RunCatalogItem[] })` is a client component.
- `FilterBar` receives supported option arrays plus active values and callbacks; it never accepts arbitrary HTML labels from query params.

- [ ] **Step 1: Write Runs index rendering tests first**

Test that a synthetic run row displays artifact ID, verification, data kind, claim scope, dataset/evaluation identity, a concise metric summary, and a detail link. Assert `SYNTHETIC_FIXTURE` and `INTEGRATION_ONLY` are visible in the catalog.

- [ ] **Step 2: Write filter interaction tests first**

Mock URL navigation behavior and verify selecting `VERIFIED` plus `SYNTHETIC_FIXTURE` produces canonical query params, clear-one removes only the selected key, clear-all removes all supported filter keys, and no-result state says `No evidence matches these filters.` rather than `No public artifacts exist.`.

- [ ] **Step 3: Run tests and verify missing catalog/page failure**

```bash
npm test -- components.test.tsx filters.test.ts
```
Expected: FAIL because RunCatalog/FilterBar do not exist.

- [ ] **Step 4: Implement the server index page**

`src/app/runs/page.tsx` loads `getRunCatalogItems()` at build time and passes only the minimal catalog array into a `<Suspense>`-wrapped `RunCatalog`. No filesystem discovery, full evidence serialization, or client fetch is introduced.

- [ ] **Step 5: Implement URL state in `RunCatalog`**

Use `useSearchParams()`, `usePathname()`, and `useRouter()`. Parse only with `parseRunFilters(new URLSearchParams(searchParams.toString()))`. On a user filter change call `router.push(query ? `${pathname}?${query}` : pathname, { scroll: false })` so browser Back/Forward traverses filter states. Filter with `matchesRunFilters`; URL is the source of UI filter state. Preserve the order of the incoming catalog array; do not sort by timestamp or invent a `latest` concept. Do not rewrite unknown query values merely by rendering the page; they remain inert until the user changes a supported filter.

- [ ] **Step 6: Implement balanced-density catalog presentation**

Use the shared semantic Table/internal-scroll primitive on desktop. Preserve full artifact IDs through wrapping or accessible full-value presentation; do not irreversibly truncate evidence identifiers.

- [ ] **Step 7: Verify static export includes `/runs/index.html`**

```bash
npm test -- components.test.tsx filters.test.ts
npm run build
npm run build:pages
```
Expected: PASS and `out/runs/index.html` exists.

- [ ] **Step 8: Commit**

```bash
git add apps/web/src/components/catalog apps/web/src/app/runs/page.tsx apps/web/tests/components.test.tsx apps/web/tests/filters.test.ts
git commit -m "feat: add filterable public runs catalog"
```

### Task 4: Build the static `/comparisons/` catalog with safe result filtering

**Files:**
- Create: `apps/web/src/components/catalog/comparison-catalog.tsx`
- Create: `apps/web/src/app/comparisons/page.tsx`
- Modify/Test: `apps/web/tests/components.test.tsx`
- Modify/Test: `apps/web/tests/filters.test.ts`

**Interfaces:**
- Server page calls `getComparisonCatalogItems()`; that helper performs existing bundle validation server-side and returns a minimal view model.
- `ComparisonCatalog({ comparisons }: { comparisons: ComparisonCatalogItem[] })` is client-side presentation only.

- [ ] **Step 1: Write comparison catalog tests first**

Assert display of comparison ID, reference/candidate IDs, MATCHED compatibility, aggregate result derived by `deriveComparisonResult()`, regression count based on actual comparison rows, claim scope, and links to comparison/failure details.

- [ ] **Step 2: Test filter semantics**

Cover `population=MATCHED`, `result=REGRESSION`, AND semantics, unknown population/result values, and a MISSING-only synthetic test bundle that must not be displayed as REGRESSION by the result helper.

- [ ] **Step 3: Run tests and verify missing module failure**

```bash
npm test -- components.test.tsx filters.test.ts
```
Expected: FAIL on missing ComparisonCatalog/page.

- [ ] **Step 4: Implement build-time validated index and client catalog**

Use `getComparisonCatalogItems()`. It obtains validated bundles through `getApprovedComparisonBundles(index)` server-side, then projects only the catalog-safe fields. Preserve explicit index order; do not sort by timestamp or infer a `latest` comparison.

- [ ] **Step 5: Add population/result filters through the same FilterBar contract**

Supported `result` values are only `PASS` and `REGRESSION`. If `deriveComparisonResult()` returns null, show a safe neutral/unavailable result label and do not match either result filter.

- [ ] **Step 6: Verify static export includes `/comparisons/index.html`**

```bash
npm test -- components.test.tsx filters.test.ts
npm run build
npm run build:pages
```
Expected: PASS and `out/comparisons/index.html` exists.

- [ ] **Step 7: Commit**

```bash
git add apps/web/src/components/catalog/comparison-catalog.tsx apps/web/src/app/comparisons/page.tsx apps/web/tests/components.test.tsx apps/web/tests/filters.test.ts
git commit -m "feat: add filterable comparison catalog"
```

### Task 5: Migrate Overview and detail surfaces to the Evidence Design System

**Files:**
- Modify: `apps/web/src/components/overview.tsx`
- Modify: `apps/web/src/components/run-detail.tsx`
- Modify: `apps/web/src/components/comparison-detail.tsx`
- Modify: `apps/web/src/components/failure-explorer.tsx`
- Modify: `apps/web/src/components/evidence-table.tsx`
- Modify: `apps/web/src/components/metric-card.tsx`
- Modify: `apps/web/src/components/provenance-panel.tsx`
- Modify/Test: `apps/web/tests/components.test.tsx`
- Modify/Test: `apps/web/tests/transitions.test.ts`

**Interfaces:**
- Consumes: Phase 5A.1 UI primitives/evidence patterns.
- Produces: no new evidence-domain values; all existing page data flow remains intact.

- [ ] **Step 1: Expand page-semantic tests before refactoring**

Lock in current behavior: Overview identifies synthetic/integration-only evidence and regression evidence; Run Detail shows approved metrics/provenance; Comparison Detail shows MATCHED plus metric policy reasons; Failure Explorer preserves all five transition semantics and changed-only behavior including THQA-002 persistent category exclusion and THQA-004/THQA-005 changed records.

- [ ] **Step 2: Run tests to establish the pre-refactor green baseline**

```bash
npm test -- components.test.tsx transitions.test.ts
```
Expected: PASS before visual refactor. Treat this as the semantic preservation baseline.

- [ ] **Step 3: Refactor Overview first**

Replace duplicated cards/badges/metric styling with shared components. Add restrained direct links to `/runs/` and `/comparisons/`. Keep recruiter-facing copy explicit that regression evidence is synthetic same-population integration evidence, not an official benchmark/model-superiority claim.

- [ ] **Step 4: Refactor Run Detail and provenance**

Use shared ArtifactBadges, MetricStat, table/surface primitives, and provenance pattern. Preserve all currently approved public fields and do not expose query/corpus text.

- [ ] **Step 5: Refactor Comparison Detail**

Use PopulationCompatibilityBadge, RegressionIndicator, MetricDelta/Comparison table patterns. Keep metric status/reason sourced from the comparison artifact; do not recompute policy status from presentation values.

- [ ] **Step 6: Refactor Failure Explorer without changing transition logic**

Keep transition derivation in `lib/evidence/transitions.ts`. Reuse FilterBar/table/empty-state components only at the presentation layer. `SHOULD_ABSTAIN` persistent state remains `Persistent category`, not `Persistent system failure`.

- [ ] **Step 7: Remove compatibility wrappers only when no production imports remain**

Search first:
```bash
rg "metric-card|evidence-table|status-badges" apps/web/src apps/web/tests
```
If a wrapper remains useful for stable imports, keep it thin. Do not delete merely for cleanup if it increases migration risk.

- [ ] **Step 8: Run full unit/component suite**

```bash
npm test
npm run lint
npm run typecheck
npm run build
```
Expected: PASS with the same evidence semantics.

- [ ] **Step 9: Commit**

```bash
git add apps/web/src/components apps/web/tests/components.test.tsx apps/web/tests/transitions.test.ts
git commit -m "refactor: adopt Evidence Design System across console"
```

### Task 6: Expand production E2E, accessibility, responsive, and Pages gates

**Files:**
- Modify: `apps/web/tests/e2e/evidence-console.spec.ts`
- Modify/Create: `apps/web/tests/e2e/__screenshots__/overview-desktop.png`
- Create: `apps/web/tests/e2e/__screenshots__/runs-filtered-desktop.png`
- Create: `apps/web/tests/e2e/__screenshots__/shell-mobile.png`
- Refresh only intentional existing Comparison/Failure screenshots.
- Modify: `.github/workflows/pages.yml`

**Interfaces:**
- Produces: page-level regression proof for shell, indexes, filtering, details, Storybook coexistence, theme, keyboard, 390px, axe, and network boundary.

- [ ] **Step 1: Add E2E route/navigation assertions first**

Cover:
```text
Overview -> Runs -> Run Detail
Overview -> Comparisons -> Comparison Detail -> Failure Explorer
Product shell -> Storybook static URL (Pages mode only)
```
Assert active nav state via `aria-current` on app routes.

- [ ] **Step 2: Add URL filter behavior tests**

For `/runs/`, select VERIFIED and SYNTHETIC_FIXTURE, assert URL/query/result count, reload and assert state persists, clear one/all, then use `page.goBack()` / `page.goForward()` to verify history behavior. Repeat population/result coverage for `/comparisons/`. Navigate to an unknown query such as `?verification=SUPER_VERIFIED` and assert HTTP/render success with no fabricated active filter.

- [ ] **Step 3: Add accessibility/theme/keyboard assertions**

At minimum run axe on Overview, Runs filtered, Comparisons, one detail page, Failure Explorer, and representative Storybook page. Keep zero serious/critical automated violations. Keyboard-smoke product navigation and filter controls; verify dark theme survives navigation.

- [ ] **Step 4: Add 390px root-overflow and internal-scroll assertions**

For Overview, Runs, Comparisons, Comparison Detail, Failure Explorer:
```ts
expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(
  await page.evaluate(() => document.documentElement.clientWidth),
);
```
Separately assert designated wide table container has `scrollWidth > clientWidth` where internal horizontal scroll is intended. Never fix failures with global `overflow-x: hidden`.

- [ ] **Step 5: Preserve the external-network boundary**

Collect browser requests and fail on runtime requests whose origin is not the local test server / GitHub Pages origin. This must include locally bundled Geist fonts and Storybook assets with no font CDN/analytics calls.

- [ ] **Step 6: Capture intentional visual baselines**

Capture Overview light/dark, Runs filtered, regression Comparison, Failure Explorer, and 390px shell/catalog. Review actual images before accepting snapshots; do not auto-update unexplained diffs.

- [ ] **Step 7: Extend Pages static assertions**

Add:
```bash
test -f out/runs/index.html
test -f out/comparisons/index.html
test -f out/storybook/index.html
```
Retain every existing detail-route, evidence-file, reports/datasets exclusion, and Storybook leakage assertion from 5A.1.

- [ ] **Step 8: Run complete local web gates**

```bash
npm run lint
npm run typecheck
npm test
npm run storybook:build
npm run storybook:build:public
node scripts/verify-public-storybook.mjs
npm run storybook:test
npm run build
npm run test:e2e
npm run build:pages
npm run test:e2e:pages
```
Expected: all PASS in local and Pages modes.

- [ ] **Step 9: Commit**

```bash
git add apps/web/tests/e2e .github/workflows/pages.yml
git commit -m "test: verify Phase 5A product adoption"
```

### Task 7: Phase 5A.2 full release and production verification

**Files:**
- Modify only after production verification: `README.md`, `DEPLOY.md`
- Update recruiter-facing screenshots only after the deployed build is verified.

**Interfaces:**
- Produces: verified public Product Console with Overview, Runs, Comparisons, details, Failure Explorer, and curated Storybook.

- [ ] **Step 1: Run repository-wide verification before PR**

From repository root:
```bash
python -m pytest -q
ruff check .
ruff format --check .
mypy .
cd apps/web
npm run lint
npm run typecheck
npm test
npm run storybook:build
npm run storybook:build:public
node scripts/verify-public-storybook.mjs
npm run storybook:test
npm run build
npm run test:e2e
npm run build:pages
npm run test:e2e:pages
```
Expected: all PASS.

- [ ] **Step 2: Run safety/drift checks**

Regenerate public evidence with the canonical generator and verify `apps/web/public/evidence/` has no unexpected diff. Scan `out/` for internal stories, local paths, secrets/provider-key patterns, raw prompts/responses/corpus markers, forbidden datasets/reports, and unexpected external URLs. Run `git diff --check` and inspect `git status --short`.

- [ ] **Step 3: Open the Phase 5A.2 PR and require full Web/Pages CI**

PR title:
```text
feat: adopt Evidence Design System across console
```
PR description must call out the new `/runs/` and `/comparisons/` static indexes, URL-driven filters, product shell, semantic-preservation tests, Storybook coexistence, and unchanged synthetic/integration-only boundary.

- [ ] **Step 4: After merge and successful Pages deploy, perform fresh production browser verification**

Verify HTTP 200 and product behavior at:
```text
/evalops-lab/
/evalops-lab/runs/
/evalops-lab/runs/demo-retrieval-reference-v1/
/evalops-lab/runs/demo-retrieval-fixture-v1/
/evalops-lab/comparisons/
/evalops-lab/comparisons/demo-retrieval-regression-v1/
/evalops-lab/comparisons/demo-retrieval-regression-v1/failures/
/evalops-lab/storybook/
```
Check active nav, valid/unknown filters, refresh/back/forward, theme, keyboard, axe, 390px no-root-overflow, internal table scroll, static assets, public Storybook allowlist, no external runtime requests, and unchanged comparison/failure semantics.

- [ ] **Step 5: Verify the known Phase 4 evidence story explicitly**

Production must still show MATCHED population compatibility, four aggregate REGRESSION rows plus one PASS in the demo comparison, changed-record summary 2, THQA-002 persistent category excluded from changed-only, THQA-004 and THQA-005 included in changed-only for their actual changes, and visible `SYNTHETIC_FIXTURE` + `INTEGRATION_ONLY` framing.

- [ ] **Step 6: Update README/DEPLOY only from verified production evidence**

Record merged SHA, CI/Web/Pages run IDs, direct Overview/Runs/Comparisons/Storybook URLs, browser verification matrix, accessibility/network/mobile results, and claim limitations. Do not write `production verified` before these checks complete.

- [ ] **Step 7: Commit post-production documentation separately**

```bash
git add README.md DEPLOY.md docs/screenshots/evidence-console
git commit -m "docs: record Phase 5A production verification"
```
