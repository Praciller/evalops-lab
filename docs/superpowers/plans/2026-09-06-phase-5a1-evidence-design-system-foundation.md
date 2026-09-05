# Phase 5A.1 Evidence Design System Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for this repository. Do not use subagent-driven-development unless the owner explicitly requests delegation. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the approved EvalOps Evidence Design System foundation, Hybrid Storybook, public-story allowlist, and Storybook CI/Pages integration without broadly migrating production pages.

**Architecture:** Keep the existing static Evidence Console and public evidence contract unchanged. Add semantic CSS tokens, locally bundled Geist typography, local shadcn-compatible primitives, EvalOps semantic product patterns, and two Storybook configurations: internal/dev and explicit public. Public Storybook is assembled under `out/storybook/` only after allowlist and leakage checks pass.

**Tech Stack:** Next.js 16.3.4, React 19.2.8, TypeScript 5.8+, Tailwind CSS 4.3.3, Vite 7.3.6, Vitest 4.1.11, Storybook 10.6.0 with `@storybook/nextjs-vite`, `@storybook/addon-a11y`, `@storybook/addon-vitest`, Playwright Chromium, Geist 1.7.2.

**Spec:** `docs/superpowers/specs/2026-09-06-phase-5a-evidence-design-system-storybook-design.md`

## Global Constraints

- Preserve the static, read-only GitHub Pages architecture under `/evalops-lab/`.
- Preserve `SYNTHETIC_FIXTURE`, `INTEGRATION_ONLY`, population compatibility, regression, and Failure Explorer semantics exactly.
- Do not add API routes, server actions, inference, auth, persistence, analytics, external runtime fetches, or database dependencies.
- Public Storybook must fail closed: a new story is internal unless explicitly included by the public story namespace/config.
- Public stories may use synthetic, portfolio-safe fixture props only.
- Public output must not expose raw prompts, raw responses, corpus content, local paths, secrets, hidden reasoning, or internal/debug story content.
- Use CSS semantic tokens as the visual source of truth; TypeScript must not duplicate a second visual token system.
- Use locally bundled fonts only; no runtime Google Fonts or font CDN requests.
- Storybook component tests do not replace existing production Playwright/axe gates.
- Keep Phase 5A.1 focused on foundation. Broad Overview/Run/Comparison/Failure page migration belongs to Phase 5A.2.

---

## File Structure

Create:
- `DESIGN.md` â€” durable design-system rules and anti-patterns.
- `apps/web/.storybook/main.ts` â€” internal/dev Storybook config, loading public + internal stories.
- `apps/web/.storybook/preview.tsx` â€” shared theme/global CSS/a11y defaults for internal Storybook.
- `apps/web/.storybook/vitest.setup.ts` â€” Storybook Vitest project setup.
- `apps/web/.storybook-public/main.ts` â€” public Storybook config with positive public story glob only.
- `apps/web/.storybook-public/preview.tsx` â€” public Storybook preview using the same production CSS/tokens.
- `apps/web/storybook.public.json` â€” exact curated public story title allowlist.
- `apps/web/scripts/verify-public-storybook.mjs` â€” compare built Storybook index with allowlist and scan for internal-story leakage.
- `apps/web/src/components/ui/button.tsx` â€” local button primitive.
- `apps/web/src/components/ui/input.tsx` â€” local input primitive.
- `apps/web/src/components/ui/select.tsx` â€” local select primitive.
- `apps/web/src/components/ui/separator.tsx` â€” local separator primitive.
- `apps/web/src/components/ui/table.tsx` â€” semantic table primitives.
- `apps/web/src/components/evidence/evidence-badges.tsx` â€” typed verification/data-kind/claim-scope badges.
- `apps/web/src/components/evidence/regression-indicator.tsx` â€” typed PASS/REGRESSION/MISSING presentation.
- `apps/web/src/components/evidence/population-compatibility-badge.tsx` â€” typed compatibility presentation.
- `apps/web/src/components/evidence/metric-stat.tsx` â€” metric value presentation with tabular numerals.
- `apps/web/src/components/evidence/metric-delta.tsx` â€” direction-aware delta presentation.
- `apps/web/src/components/evidence/empty-state.tsx` â€” shared empty/unavailable state primitive.
- `apps/web/src/stories/public/*.public.stories.tsx` â€” curated public stories only.
- `apps/web/src/stories/internal/*.internal.stories.tsx` â€” debug/edge stories never included in the public build.
- `apps/web/tests/design-system.test.tsx` â€” component behavior and semantic mapping tests.
- `apps/web/tests/storybook-publication.test.ts` â€” source-level public/internal boundary tests.

Modify:
- `apps/web/package.json` / `apps/web/package-lock.json` â€” Storybook, Geist, browser-test dependencies and scripts.
- `apps/web/vitest.config.ts` â€” define explicit `unit`, `storybook-light`, and `storybook-dark` projects using Vitest 4 `test.projects`; do not add a legacy workspace file.
- `apps/web/src/app/globals.css` â€” normalized semantic tokens, spacing/radius/type tokens, focus/reduced-motion rules.
- `apps/web/src/app/layout.tsx` â€” locally bundled Geist Sans/Mono variables.
- `apps/web/src/components/ui/badge.tsx` and `card.tsx` â€” normalize to token-backed local primitives.
- `apps/web/src/components/status-badges.tsx` â€” compatibility shim/re-export to new evidence badge components; do not duplicate semantic mappings.
- `apps/web/scripts/build-pages.mjs` â€” assemble curated Storybook under `out/storybook/` after the Next static build.
- `.github/workflows/web-ci.yml` â€” Storybook build/test/publication checks.
- `.github/workflows/pages.yml` â€” Storybook build, verification, static-output assertions, and path coverage.
- `apps/web/tests/e2e/evidence-console.spec.ts` â€” Pages-mode public Storybook accessibility/network/mobile/reduced-motion smoke coverage.

---

### Task 1: Pin a supported Storybook test stack and add fail-closed configs

**Files:**
- Modify: `apps/web/package.json`
- Modify: `apps/web/package-lock.json`
- Create: `apps/web/.storybook/main.ts`
- Create: `apps/web/.storybook/preview.tsx`
- Create: `apps/web/.storybook/vitest.setup.ts`
- Create: `apps/web/.storybook-public/main.ts`
- Create: `apps/web/.storybook-public/preview.tsx`
- Test: `apps/web/tests/storybook-publication.test.ts`

**Interfaces:**
- Consumes: existing `@/* -> ./src/*` TypeScript alias and `src/app/globals.css`.
- Produces: `npm run storybook`, `npm run storybook:build`, `npm run storybook:build:public`, `npm run storybook:test`; internal config matches public + internal stories, public config matches only `src/stories/public/**/*.public.stories.*`.

- [ ] **Step 1: Capture compatibility evidence before changing dependencies**

Run from `apps/web`:
```bash
npm view storybook version
npm view @storybook/nextjs-vite version peerDependencies
npm view @storybook/addon-vitest version peerDependencies
npm view @storybook/addon-a11y version peerDependencies
npm view geist version license
```
Expected from the verified 2026-09-06 package metadata: Storybook and Storybook addons `10.6.0`; `@storybook/nextjs-vite` peers Next `^14.1 || ^15 || ^16`, Vite `^5 || ^6 || ^7 || ^8`, React 19; `@storybook/addon-vitest` requires Vitest `^3 || ^4` and `@vitest/browser-playwright ^4`; Geist `1.7.2` with SIL Open Font License. Use the pinned compatible line below rather than the latest Vitest 5, which is outside the Storybook 10.6 addon peer range.

- [ ] **Step 2: Write the publication-boundary test first**

Create `tests/storybook-publication.test.ts`:
```ts
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("Storybook publication boundary", () => {
  it("public config uses a positive public-story glob and never imports internal stories", () => {
    const config = readFileSync(resolve(".storybook-public/main.ts"), "utf8");
    expect(config).toContain("src/stories/public/**/*.public.stories");
    expect(config).not.toContain("internal.stories");
    expect(config).not.toContain("src/**/*.stories");
  });
});
```

- [ ] **Step 3: Run the test and verify it fails because the public config does not exist**

Run:
```bash
npm test -- storybook-publication.test.ts
```
Expected: FAIL with an ENOENT/read-file error for `.storybook-public/main.ts`.

- [ ] **Step 4: Install the supported packages and add explicit scripts/configs**

Install the verified versions from Step 1, keeping Storybook packages on the same release line:
```bash
npm install geist@1.7.2
npm install --save-dev storybook@10.6.0 @storybook/nextjs-vite@10.6.0 @storybook/addon-a11y@10.6.0 @storybook/addon-vitest@10.6.0 @storybook/addon-docs@10.6.0 vite@7.3.6 vitest@4.1.11 @vitest/browser-playwright@4.1.11
```
Update the existing test scripts so the normal unit suite stays isolated, then add Storybook scripts:
```json
{
  "test": "vitest run --project=unit",
  "test:watch": "vitest --project=unit",
  "storybook": "storybook dev -p 6006 --config-dir .storybook",
  "storybook:build": "storybook build --config-dir .storybook --output-dir storybook-static",
  "storybook:build:public": "storybook build --config-dir .storybook-public --output-dir storybook-public-static",
  "storybook:test": "vitest run --project=storybook-light --project=storybook-dark"
}
```
Create `.storybook/main.ts` with `@storybook/nextjs-vite`, addons `@storybook/addon-docs`, `@storybook/addon-a11y`, `@storybook/addon-vitest`, and stories:
```ts
stories: [
  "../src/stories/public/**/*.public.stories.@(ts|tsx)",
  "../src/stories/internal/**/*.internal.stories.@(ts|tsx)",
]
```
Create `.storybook-public/main.ts` with the same framework/docs/a11y support but only:
```ts
stories: ["../src/stories/public/**/*.public.stories.@(ts|tsx)"]
```
Both previews import `../src/app/globals.css`; set `parameters.a11y.test = "error"`, define 390px/768px/desktop viewport presets, and expose a `theme` toolbar with only `light` and `dark`. A shared decorator toggles the same root `.dark` class used by production, so Storybook never invents a separate theme palette.

- [ ] **Step 5: Configure explicit Vitest unit + light/dark Storybook projects**

Follow the current Storybook Vitest-addon pattern: use `defineProject({ extends: true, ... })`, the Playwright browser provider, and two Storybook projects pinned with `initialGlobals.theme` so the same curated stories are exercised in both themes:
```ts
import path from "node:path";
import { storybookTest } from "@storybook/addon-vitest/vitest-plugin";
import { playwright } from "@vitest/browser-playwright";
import { defineConfig, defineProject } from "vitest/config";

const storybookProject = (theme: "light" | "dark") =>
  defineProject({
    extends: true,
    plugins: [
      storybookTest({
        configDir: path.join(__dirname, ".storybook"),
        initialGlobals: { theme },
      }),
    ],
    test: {
      name: `storybook-${theme}`,
      browser: {
        enabled: true,
        provider: playwright({}),
        headless: true,
        instances: [{ browser: "chromium" }],
      },
      setupFiles: ["./.storybook/vitest.setup.ts"],
    },
  });

export default defineConfig({
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  test: {
    projects: [
      defineProject({
        extends: true,
        test: {
          name: "unit",
          environment: "jsdom",
          setupFiles: ["./tests/setup.ts"],
          include: ["tests/**/*.test.{ts,tsx}"],
        },
      }),
      storybookProject("light"),
      storybookProject("dark"),
    ],
  },
});
```
Create `.storybook/vitest.setup.ts` from the official portable-annotations pattern:
```ts
import { setProjectAnnotations } from "@storybook/nextjs-vite";
import * as previewAnnotations from "./preview";

setProjectAnnotations([previewAnnotations]);
```
The Storybook plugin then renders/tests stories in a real Chromium browser with the same preview globals and accessibility configuration.

- [ ] **Step 6: Run focused verification**

Run:
```bash
npm test -- storybook-publication.test.ts
npm run typecheck
npm run lint
```
Expected: publication-boundary test PASS; typecheck/lint PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/web/package.json apps/web/package-lock.json apps/web/.storybook apps/web/.storybook-public apps/web/vitest.config.ts apps/web/tests/storybook-publication.test.ts
git commit -m "build: add hybrid Storybook foundation"
```

### Task 2: Establish semantic tokens, Geist typography, and DESIGN.md

**Files:**
- Create: `DESIGN.md`
- Modify: `apps/web/src/app/globals.css`
- Modify: `apps/web/src/app/layout.tsx`
- Test: `apps/web/tests/design-system.test.tsx`

**Interfaces:**
- Consumes: Geist package CSS variables `--font-geist-sans` and `--font-geist-mono`.
- Produces: canonical CSS tokens for canvas/surfaces/ink/line/accent/status/spacing/radius/type, `font-sans` and `font-mono` mappings, visible focus ring, reduced-motion behavior.

- [ ] **Step 1: Write a token/typography behavior test first**

Add to `tests/design-system.test.tsx` a small render of a semantic metric component placeholder and assert that technical values can receive the documented `font-mono`/tabular-numeric class while normal body text does not. Also read `globals.css` and assert the canonical tokens exist:
```ts
expect(css).toContain("--color-accent:");
expect(css).toContain("--color-line-strong:");
expect(css).toContain("--space-md:");
expect(css).toContain("--radius-md:");
expect(css).toContain("--font-sans:");
expect(css).toContain("--font-mono:");
```

- [ ] **Step 2: Run the test and verify the new tokens fail**

Run:
```bash
npm test -- design-system.test.tsx
```
Expected: FAIL because at least the new spacing/radius/font token assertions are absent.

- [ ] **Step 3: Normalize `globals.css` around semantic tokens**

Preserve existing light/dark meanings but replace ad hoc values with canonical variables. Include the approved families `canvas`, `surface`, `surface-muted`, `ink`, `ink-muted`, `line`, `line-strong`, `accent`, `accent-soft`, `success`, `success-soft`, `caution`, `caution-soft`, `danger`, `danger-soft`, `scope`, `scope-soft`, plus spacing `2xs..2xl`, radius `sm/md/lg`, focus ring and control sizing. Keep `prefers-reduced-motion`; do not add global horizontal-overflow hiding.

- [ ] **Step 4: Wire locally bundled Geist in `layout.tsx`**

Use:
```tsx
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";

<html lang="en" className={`${GeistSans.variable} ${GeistMono.variable}`}>
```
Map CSS `--font-sans` to `var(--font-geist-sans)` and `--font-mono` to `var(--font-geist-mono)`. Do not use `next/font/google`.

- [ ] **Step 5: Write `DESIGN.md` as the durable source of truth**

Document exactly: Evidence over decoration; Modern Product Console; neutral/slate + blue accent; balanced density; semantic state colors; typography roles; spacing/radius rules; component layer boundaries; responsive table policy; 390px no-root-overflow rule; accessibility; Hybrid Storybook allowlist; no claim amplification; prohibited decorative/hosted patterns.

- [ ] **Step 6: Verify tests and static build**

Run:
```bash
npm test -- design-system.test.tsx
npm run typecheck
npm run lint
npm run build
```
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add DESIGN.md apps/web/src/app/globals.css apps/web/src/app/layout.tsx apps/web/tests/design-system.test.tsx
git commit -m "feat: define EvalOps semantic design tokens"
```

### Task 3: Build the focused local primitive layer

**Files:**
- Modify: `apps/web/src/components/ui/badge.tsx`
- Modify: `apps/web/src/components/ui/card.tsx`
- Create: `apps/web/src/components/ui/button.tsx`
- Create: `apps/web/src/components/ui/input.tsx`
- Create: `apps/web/src/components/ui/select.tsx`
- Create: `apps/web/src/components/ui/separator.tsx`
- Create: `apps/web/src/components/ui/table.tsx`
- Test: `apps/web/tests/design-system.test.tsx`

**Interfaces:**
- Produces: generic primitives that know nothing about verification, regression, data kind, or claim scope.

- [ ] **Step 1: Add failing primitive contract tests**

Test that Button forwards native props, Input has a native input role, Select is a native accessible select for the current lightweight needs, Table renders semantic table markup, and Badge/Card accept `className` without domain-specific status props.

- [ ] **Step 2: Run focused tests and confirm missing modules fail**

Run:
```bash
npm test -- design-system.test.tsx
```
Expected: FAIL on missing primitive imports.

- [ ] **Step 3: Implement minimal local primitives**

Use native elements and the existing `cn()` helper. Example Button contract:
```tsx
type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement>;
export function Button({ className, type = "button", ...props }: ButtonProps) {
  return <button type={type} className={cn("control focus-ring", className)} {...props} />;
}
```
Keep Table primitives semantic (`table`, `thead`, `tbody`, `tr`, `th`, `td`) and let `Table` wrap only the internal scroll boundary needed by evidence tables.

- [ ] **Step 4: Run tests, lint, and typecheck**

```bash
npm test -- design-system.test.tsx
npm run lint
npm run typecheck
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/ui apps/web/tests/design-system.test.tsx
git commit -m "feat: add local Evidence Console primitives"
```

### Task 4: Move evidence semantics into typed product patterns

**Files:**
- Create: `apps/web/src/components/evidence/evidence-badges.tsx`
- Create: `apps/web/src/components/evidence/regression-indicator.tsx`
- Create: `apps/web/src/components/evidence/population-compatibility-badge.tsx`
- Create: `apps/web/src/components/evidence/metric-stat.tsx`
- Create: `apps/web/src/components/evidence/metric-delta.tsx`
- Create: `apps/web/src/components/evidence/empty-state.tsx`
- Modify: `apps/web/src/components/status-badges.tsx`
- Test: `apps/web/tests/design-system.test.tsx`

**Interfaces:**
- Consumes: `PublicClaimArtifact`, `PublicComparisonArtifact["comparisons"][number]`, `PopulationCompatibility` values from `lib/evidence/schemas.ts`.
- Produces: `VerificationBadge`, `DataKindBadge`, `ClaimScopeBadge`, `ArtifactBadges`, `RegressionIndicator`, `PopulationCompatibilityBadge`, `MetricStat`, `MetricDelta`, `EmptyState`.

- [ ] **Step 1: Write failing semantic mapping tests**

Cover every verification value, all three data kinds, all three claim scopes, MATCHED/UNVERIFIED/INCOMPATIBLE, PASS/REGRESSION/MISSING, and metric directionality. Include this critical assertion:
```ts
render(<MetricDelta delta={0.05} direction="lower_is_better" status="REGRESSION" />);
expect(screen.getByText(/regression/i)).toBeInTheDocument();
```
This prevents interpreting `+0.05` as improvement based only on sign.

- [ ] **Step 2: Run focused tests and verify failures**

```bash
npm test -- design-system.test.tsx
```
Expected: FAIL because the evidence pattern modules do not yet exist.

- [ ] **Step 3: Implement typed patterns with exhaustive mappings**

Use `Record<Union, Presentation>` maps keyed by exact schema-derived unions. Never accept arbitrary color/style props for evidence meaning. Keep `status-badges.tsx` as a compatibility re-export so existing production pages continue working without duplicating maps.

- [ ] **Step 4: Verify semantic and existing component tests**

```bash
npm test -- design-system.test.tsx components.test.tsx
npm run typecheck
npm run lint
```
Expected: PASS and no broad production-page rewrite.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/evidence apps/web/src/components/status-badges.tsx apps/web/tests/design-system.test.tsx
git commit -m "feat: add typed evidence presentation patterns"
```

### Task 5: Add curated public stories, internal stress stories, and a machine-checkable allowlist

**Files:**
- Create: `apps/web/storybook.public.json`
- Create: `apps/web/src/stories/public/foundations.public.stories.tsx`
- Create: `apps/web/src/stories/public/primitives.public.stories.tsx`
- Create: `apps/web/src/stories/public/evidence-states.public.stories.tsx`
- Create: `apps/web/src/stories/public/metrics.public.stories.tsx`
- Create: `apps/web/src/stories/public/patterns.public.stories.tsx`
- Create: `apps/web/src/stories/internal/stress.internal.stories.tsx`
- Create: `apps/web/scripts/verify-public-storybook.mjs`
- Modify/Test: `apps/web/tests/storybook-publication.test.ts`

**Interfaces:**
- Produces: exact public title allowlist and a verifier that checks `storybook-public-static/index.json` story titles plus static-output leakage patterns.

- [ ] **Step 1: Extend the publication test to require an exact allowlist**

Assert `storybook.public.json` contains only the approved title groups and no title beginning `Internal/` or `Debug/`.

- [ ] **Step 2: Run test and verify allowlist absence fails**

```bash
npm test -- storybook-publication.test.ts
```
Expected: FAIL because the manifest/public stories do not exist.

- [ ] **Step 3: Create public stories using synthetic safe props only**

Use literal synthetic IDs such as `demo-retrieval-fixture-v1`, `THQA-004`, and explicit labels `SYNTHETIC_FIXTURE` + `INTEGRATION_ONLY`. Public stories cover Foundations, Button/Badge/Card/Table, evidence badges, metric stat/delta, empty/unavailable states, and a compact provenance/evidence pattern. Do not reproduce full production pages. For domain controls, define `argTypes` with `control: { type: "select" }` and an explicit `options` array of supported enum values; do not expose arbitrary free-text controls that can manufacture evidence states. Responsive patterns must include representative 390px mobile, 768px tablet, and desktop story parameters; theme-capable stories must be checked in both light and dark.

- [ ] **Step 4: Create internal-only stress stories**

Include long identifiers, mobile width pressure, every dark/light permutation, and intentionally unsupported presentation inputs only when the component contract can represent a safe unavailable state. Title all internal stories under `Internal/...`.

- [ ] **Step 5: Implement the public build verifier**

`verify-public-storybook.mjs` must:
```js
const index = JSON.parse(readFileSync("storybook-public-static/index.json", "utf8"));
const actualTitles = new Set(Object.values(index.entries).map((entry) => entry.title));
const expectedTitles = new Set(JSON.parse(readFileSync("storybook.public.json", "utf8")).titles);
```
Fail when sets differ, when any title starts `Internal/` or `Debug/`, or when generated text contains `.internal.stories`, a Windows drive path pattern, `/home/`, `.env`, secret-like patterns such as `sk-[A-Za-z0-9_-]{20,}` or `gsk_[A-Za-z0-9_-]{20,}`, or known raw-data markers. Treat public commit/artifact SHA-like identifiers as allowed only when they originate from curated story literals.

- [ ] **Step 6: Build and test Storybook**

```bash
npm run storybook:build
npm run storybook:build:public
node scripts/verify-public-storybook.mjs
npm run storybook:test
```
Expected: both builds PASS; public verifier PASS; Storybook interaction/a11y tests PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/web/storybook.public.json apps/web/src/stories apps/web/scripts/verify-public-storybook.mjs apps/web/tests/storybook-publication.test.ts
git commit -m "feat: add curated public Storybook catalog"
```

### Task 6: Assemble public Storybook into Pages and enforce it in CI

**Files:**
- Modify: `apps/web/scripts/build-pages.mjs`
- Modify: `apps/web/package.json`
- Modify: `.github/workflows/web-ci.yml`
- Modify: `.github/workflows/pages.yml`
- Modify/Test: `apps/web/tests/e2e/evidence-console.spec.ts`
- Test: `apps/web/tests/storybook-publication.test.ts`

**Interfaces:**
- Produces: deterministic `out/storybook/index.html` after `npm run build:pages`; CI gates for internal Storybook test/build and public Storybook build/verifier.

- [ ] **Step 1: Write a build-pages source test first**

Assert `scripts/build-pages.mjs` invokes the Next build, public Storybook build, public verifier, removes any stale `out/storybook`, then copies only `storybook-public-static` to `out/storybook`.

- [ ] **Step 2: Run the source test and confirm failure**

```bash
npm test -- storybook-publication.test.ts
```
Expected: FAIL because `build-pages.mjs` currently invokes only `npm run build`.

- [ ] **Step 3: Update `build-pages.mjs` for explicit assembly**

Keep `GITHUB_PAGES=true` for the Next build. After a successful Next build, execute `npm run storybook:build:public`, execute `node scripts/verify-public-storybook.mjs`, remove `out/storybook` if present, and `cpSync("storybook-public-static", "out/storybook", { recursive: true })`. Exit non-zero on any failed subprocess.

- [ ] **Step 4: Extend Web CI**

After unit tests, run:
```yaml
- run: npm run storybook:build
- run: npm run storybook:build:public
- run: node scripts/verify-public-storybook.mjs
- run: npm run storybook:test
```
Then keep the existing production `npm run build` and Playwright gates. Ensure workflow paths include `DESIGN.md` and Storybook config/story/script paths; `apps/web/**` already covers app-local files.

- [ ] **Step 5: Extend Pages CI**

Keep `npm run build:pages` as the assembly command. Add static assertions:
```bash
test -f out/storybook/index.html
test -f out/storybook/index.json
! grep -R -n -E 'Internal/|Debug/|\.internal\.stories' out/storybook
```
Retain all existing Evidence Console artifact and forbidden-directory checks.


- [ ] **Step 6: Add a Pages-mode Storybook browser smoke test**

In `tests/e2e/evidence-console.spec.ts`, add a test guarded with `test.skip(process.env.PAGES_MODE !== "true", "public Storybook exists only in assembled Pages output")`. Navigate to `${appBasePath}/storybook/`, assert the Storybook shell loads, capture requests and require the same local origin/data URLs only, run axe against a representative curated story iframe or docs canvas, assert 390px root width does not overflow, switch the Storybook theme global between light/dark, and use `page.emulateMedia({ reducedMotion: "reduce" })` to verify the curated story remains usable without required animation.

- [ ] **Step 7: Run full frontend verification locally**

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
Expected: all PASS; existing Evidence Console E2E behavior remains unchanged.

- [ ] **Step 8: Commit**

```bash
git add apps/web/scripts/build-pages.mjs apps/web/package.json .github/workflows/web-ci.yml .github/workflows/pages.yml apps/web/tests/storybook-publication.test.ts apps/web/tests/e2e/evidence-console.spec.ts
git commit -m "ci: publish and verify curated Storybook"
```

### Task 7: Phase 5A.1 release verification and evidence capture

**Files:**
- Modify only after production verification: `README.md`, `DEPLOY.md`
- Optional screenshot refresh only after production behavior is verified: `docs/screenshots/evidence-console/**`

**Interfaces:**
- Produces: verified production evidence for `/evalops-lab/storybook/` while existing Evidence Console remains semantically unchanged.

- [ ] **Step 1: Run repository-wide pre-PR gates**

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

- [ ] **Step 2: Run source/public-output safety scans**

Scan `apps/web/storybook-public-static` and `apps/web/out/storybook` for `.internal.stories`, `Internal/`, local absolute paths, `.env`, provider-key prefixes, raw-prompt/raw-response markers, and unexpected external URLs. Classify any hash-like public identifier false positives individually; do not suppress broad patterns.

- [ ] **Step 3: Open PR 5A.1 and wait for CI**

PR title:
```text
feat: add Evidence Design System foundation and hybrid Storybook
```
PR body must state that Phase 5A.1 intentionally avoids broad production-page migration and preserves synthetic/integration-only claim semantics.

- [ ] **Step 4: After merge, verify production in a real browser**

Verify HTTP 200 and assets for:
```text
https://praciller.github.io/evalops-lab/
https://praciller.github.io/evalops-lab/storybook/
```
Check public Storybook contains only curated groups, light/dark theme works, representative stories at 390px have no root overflow, axe serious/critical count is zero for representative curated stories, and network logs contain no unexpected third-party runtime requests. Re-open existing Overview/Run/Comparison/Failure Explorer flows and verify claim labels and Phase 4 behavior remain intact.

- [ ] **Step 5: Only after fresh production verification, update README/DEPLOY**

Record the merged SHA, workflow run IDs, Pages result, Storybook URL, public-story allowlist result, accessibility/network result, and explicit limitation that the catalog demonstrates synthetic/integration-only UI states rather than benchmark/model-superiority claims.

- [ ] **Step 6: Commit post-production docs separately**

```bash
git add README.md DEPLOY.md docs/screenshots/evidence-console
git commit -m "docs: record Phase 5A.1 production verification"
```
