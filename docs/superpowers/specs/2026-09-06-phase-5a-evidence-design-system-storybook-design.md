# Phase 5A: Evidence Design System + Hybrid Storybook Design

Date: 2026-09-06
Repository: `Praciller/evalops-lab`
Status: Conversational design approved; canonical specification pending owner review

## 1. Goal

Evolve the Evidence Console from a collection of strong evidence pages into a coherent, production-quality product surface while preserving the existing evaluation, claim, security, and static-publication boundaries.

Phase 5A adopts a **Refined Modern Product Console** visual direction under the existing principle:

> Evidence over decoration.

The phase must improve visual hierarchy, typography, spacing, navigation, component consistency, responsive behavior, accessibility, and portfolio/reviewer clarity without turning EvalOps Lab into a generic SaaS dashboard or broad application platform.

Phase 5A is explicitly split into two implementation PRs:

```text
Phase 5A.1
Design-system foundation + Hybrid Storybook + CI
        ↓
Phase 5A.2
Production product-shell adoption + indexes + filtering
```

Phase 5B repository governance/portfolio work is separate and out of scope here.

## 2. Existing constraints that remain authoritative

The current architecture and evidence semantics remain the source of truth:

- Evidence Console is static, read-only, and deployed through GitHub Pages under `/evalops-lab/`.
- Public evidence is sanitized and explicitly allowlisted.
- The frontend validates public artifacts fail-closed.
- Synthetic fixtures remain `SYNTHETIC_FIXTURE`.
- Current demo claims remain `INTEGRATION_ONLY` unless a future approved artifact contract supports a stronger claim.
- Population compatibility semantics remain `MATCHED`, `UNVERIFIED`, and `INCOMPATIBLE`.
- Regression verdicts remain sourced from evaluation/regression artifacts rather than visual inference.
- Failure Explorer transition semantics from Phase 4 remain unchanged.
- No API routes, server actions, runtime model inference, external provider fetches, authentication, persistence, analytics, or database are introduced.
- No raw prompts, raw responses, corpus content, hidden reasoning, machine-local paths, secrets, or unapproved evaluation internals may be published.

The design system may render evidence truth, but it may never create, override, amplify, or reinterpret that truth.

## 3. Architecture decision

Use an **Evidence Design System** architecture rather than minimal styling hardening or a standalone reusable package.

```text
Sanitized Public Evidence Contract
            ↓
     Semantic CSS Tokens
            ↓
Local shadcn-compatible UI Primitives
            ↓
   EvalOps Evidence Patterns
            ↓
       Page Compositions
```

### 3.1 Layer boundaries

The frontend component hierarchy is conceptually:

```text
components/ui/*
= generic visual/interaction primitives
= no EvalOps domain semantics

components/evidence/*
= domain-aware components
= verification/data-kind/claim-scope/regression semantics

app/* and page compositions
= routing, data mapping, composition, information architecture
```

Example:

```text
Badge                 -> generic primitive
VerificationBadge     -> EvalOps semantic pattern
RunDetail             -> page composition
```

Pages must not choose evidence colors or state wording ad hoc. Domain-aware components must map only from supported typed values.

## 4. Visual direction

The approved product character is **Modern Product Console** rather than an engineering-devtool-only console or editorial/research layout.

It should feel:

- technical and credible
- restrained and mature
- recruiter/reviewer friendly
- information-dense enough for evidence inspection
- visually polished without decorative noise

It must avoid:

- marketing-style hero treatment
- glassmorphism
- decorative gradients
- chart walls
- vanity metrics
- heavy card shadows
- traffic-light color overload
- oversized whitespace that harms evidence scanning

## 5. Semantic token system

CSS semantic tokens are the canonical design-token source of truth. TypeScript may contain domain mappings where required but must not duplicate a second visual token source.

The system should normalize the existing variables into a deliberate semantic vocabulary including, as needed:

```text
canvas
surface
surface-muted
ink
ink-muted
line
line-strong
accent
accent-soft
success
success-soft
caution
caution-soft
danger
danger-soft
scope
scope-soft
```

Additional canonical token families should cover:

```text
typography
spacing
radius
focus treatment
control sizing
border emphasis
```

Light and dark modes must consume the same semantic token names. Storybook and production must use the same token implementation.

### 5.1 Color direction

Use a **refined neutral/slate foundation with blue accent**.

Blue is reserved for navigation, focus, selection, and evidence/action affordances. Success, caution, danger, and scope colors are semantic states, not decoration.

Status must never be conveyed by color alone. Text labels and appropriate semantic structure remain required.

## 6. Typography

Use a locally bundled product sans plus a locally bundled product mono font, with no runtime font network dependency.

Preferred direction:

- product sans: Geist Sans or a comparable locally bundled, license-compatible option
- product mono: Geist Mono or a comparable locally bundled, license-compatible option

The exact package/version must be validated during implementation planning against the current Next.js 16 / React 19 toolchain and licensing requirements. If a suitable local font integration is not cleanly supportable, fall back to a system font stack rather than introduce an external font request.

Sans is used for:

- navigation
- headings
- body copy
- controls
- labels
- tables

Mono is limited to technical values such as:

- metric values
- artifact IDs
- record IDs
- revisions
- hashes
- protocol/version identifiers

Important numeric comparisons should use tabular numerals where appropriate.

## 7. Density, surfaces, and responsive rhythm

The approved density is **Balanced**.

Desktop should remain compact enough for evidence scanning while providing enough spacing for hierarchy and comprehension. Mobile should stack or wrap intentionally rather than merely compress desktop layouts.

Use a single spacing scale with semantic application to:

- control gaps
- card padding
- section rhythm
- page rhythm
- table cell density

Surface design remains restrained:

- borders are the primary separation mechanism
- radius is small to medium
- shadows are rare and reserved for real overlays/elevation
- no card-everything visual treatment

At representative 390px mobile width:

- root-page horizontal overflow is forbidden
- evidence tables that require comparison may use deliberate internal horizontal scrolling
- global `overflow-x: hidden` must not be used to mask layout defects

## 8. Evidence-state visual grammar

The system must visually distinguish evidence dimensions rather than render every domain value as the same badge with a different color.

Required semantic families include:

```text
Verification
VERIFIED / PARTIAL / UNVERIFIED / NOT_RUN

Data Kind
SYNTHETIC_FIXTURE / CURATED_DATASET / OFFICIAL_BENCHMARK

Claim Scope
INTEGRATION_ONLY / PROTOCOL_SPECIFIC / BENCHMARK_RESULT

Regression
PASS / REGRESSION

Population Compatibility
MATCHED / UNVERIFIED / INCOMPATIBLE
```

Recommended component roles:

- `VerificationBadge`
- `DataKindBadge`
- `ClaimScopeBadge`
- `RegressionIndicator`
- `PopulationCompatibilityBadge`

These components accept supported typed/domain-safe values only. Pages may not inject arbitrary semantic labels or arbitrary colors.

## 9. Local shadcn-compatible primitive layer

Use a local, reviewable, shadcn-compatible component style rather than a runtime dependency on an external design-system library.

Phase 5A.1 should add only primitives with an actual approved use case, potentially including:

- `Button`
- `Badge`
- `Card`
- `Separator`
- `Tooltip`
- `Select`
- `Checkbox`
- `Input`
- `Table`
- `Popover` only if filtering/help interaction requires it
- `Tabs` only if a real product use case emerges
- `Skeleton` only for component-state documentation if useful; the production product has no runtime fetching flow that requires loading skeletons

Do not add a large speculative primitive inventory.

## 10. EvalOps product patterns

Domain-aware patterns should provide a stable product vocabulary around evidence inspection.

### 10.1 Metric patterns

Candidate patterns include:

- `MetricStat`
- `MetricDelta`
- `MetricComparisonRow`
- `RegressionSummary`
- `EvidenceSummaryCard`

`MetricDelta` must understand metric directionality, such as `HIGHER_IS_BETTER` and `LOWER_IS_BETTER`, and must not infer improvement from a raw positive sign alone.

### 10.2 Provenance and claim patterns

Candidate patterns include:

- `ProvenancePanel`
- `EvidenceClaim`
- `ArtifactIdentity`
- `DatasetIdentity`
- `ProtocolMetadata`

A reviewer should be able to identify quickly:

1. what artifact is being viewed
2. what data kind it uses
3. what claim scope is allowed
4. whether the evaluation actually ran
5. which protocol/version/revision governs the evidence

For synthetic demos, `SYNTHETIC_FIXTURE` and `INTEGRATION_ONLY` must remain visible without requiring deep inspection.

### 10.3 Table patterns

Evidence tables remain semantic HTML tables and support consistent numeric alignment, technical typography, status rendering, and responsive scroll boundaries.

Potential reusable patterns include:

- `EvidenceTable`
- `MetricTable`
- `ComparisonTable`
- `RecordChangeTable`

Tables must preserve keyboard/accessibility semantics and must not solve mobile layout by hiding evidence irreversibly.

### 10.4 Empty and unavailable states

Provide separate reusable states for:

- no public artifacts
- filters yielding zero results
- comparison unavailable
- unsupported evidence state
- invalid public artifact

An invalid or unsupported artifact must never be represented as a successful state.

## 11. `DESIGN.md` source of truth

Phase 5A.1 adds a repository design-system source of truth, expected as `DESIGN.md` unless implementation planning identifies a stronger repository-local placement consistent with existing conventions.

`DESIGN.md` should document at minimum:

- `Evidence over decoration`
- Modern Product Console direction
- token architecture
- light/dark rules
- typography
- density and spacing principles
- semantic colors
- evidence-state grammar
- primitive/product-pattern/page boundaries
- responsive table policy
- accessibility expectations
- public Storybook publication rules
- non-goals and anti-patterns

Storybook is the executable catalog; `DESIGN.md` is the durable architectural/visual contract.

## 12. Hybrid Storybook architecture

Storybook is an engineering and portfolio surface, but public publication must fail closed.

The approved model is **Hybrid Storybook**:

```text
Internal/dev catalog
= public + internal/debug stories

Public catalog
= explicit curated public stories only
```

A representative structure may be:

```text
apps/web/
├─ .storybook/
├─ stories/
│  ├─ public/
│  │  └─ *.public.stories.tsx
│  └─ internal/
│     └─ *.internal.stories.tsx
```

The exact config filenames may vary according to supported Storybook tooling, but the publication behavior must not.

### 12.1 Public-story allowlist

Public Storybook must use an explicit positive publication rule, such as a dedicated public story namespace/glob and, if useful, a machine-checkable catalog/manifest.

The safety property is:

```text
new story added
!= automatically public
```

Blacklist/exclusion-only publication is not acceptable.

CI should be able to compare the expected curated public catalog with the actual public build and detect accidental internal-story leakage.

### 12.2 Public story content

Public stories must use synthetic, portfolio-safe fixture props only.

They must not expose:

- real/private data
- raw prompts
- raw responses
- corpus/document text outside approved sanitized fixtures
- local paths
- credentials/secrets
- hidden reasoning
- unsupported benchmark claims

When a domain component could be screenshotted without surrounding context, the story must preserve enough claim/provenance context to avoid implying a stronger result than the data supports.

### 12.3 Public catalog scope

The approved public catalog covers **primitives + product patterns**, not full-page duplication.

Useful curated groups include:

```text
Foundations
  Typography
  Color and semantic states
  Spacing

Primitives
  Button
  Badge
  Card
  Table
  Controls

Evidence
  Verification
  Data provenance
  Claim scope
  Metrics

Comparison
  Metric delta
  Regression summary
  Failure transitions

Patterns
  Provenance panel
  Filter bar
  Empty/unavailable states
  Product navigation
```

Full production pages remain the responsibility of the Evidence Console itself rather than being mirrored wholesale in Storybook.

### 12.4 Story controls

Public controls may expose only predefined, semantically valid values. Arbitrary values that can manufacture fake evidence states are forbidden.

Invalid combinations belong in internal/debug stories where they can exercise fail-closed behavior without being public-facing product examples.

## 13. Storybook deployment

Public Storybook is deployed under the same GitHub Pages site:

```text
https://praciller.github.io/evalops-lab/
https://praciller.github.io/evalops-lab/storybook/
```

It is a static subtree of the same versioned deployment, not a separate hosted product.

The Pages artifact therefore contains three controlled public surfaces:

```text
Next static Evidence Console
+
Sanitized allowlisted public evidence
+
Curated public Storybook static build
```

Assembly must be explicit and deterministic. Broad copying of source/workspace directories into public output is forbidden.

Storybook adds no backend, auth, analytics, telemetry, runtime external fetch, or hosted design service.

## 14. Storybook CI gates

The approved Storybook quality gate is:

```text
Build validity
    ↓
Interaction/component behavior
    ↓
Accessibility
```

CI must verify both internal/dev stories and the curated public build as appropriate.

Required checks include:

- Storybook builds successfully
- relevant interactive stories pass interaction tests
- keyboard/focus behavior works where applicable
- automated accessibility checks pass at the agreed severity threshold
- public Storybook includes only allowlisted public stories
- public Storybook output passes leakage/security scanning

Do not add Chromatic or another hosted visual-regression SaaS in this phase.

Component-level Storybook checks do not replace production Playwright and axe checks.

## 15. Product shell

Phase 5A.2 introduces a lightweight top-level product shell:

```text
EvalOps Evidence Console
Overview | Runs | Comparisons | Storybook | Theme
```

There is no sidebar in Phase 5A.

The shell should include:

- product identity
- restrained `Evidence over decoration` context
- primary navigation
- active-route state with semantic support such as `aria-current="page"`
- theme control
- responsive navigation behavior

Storybook is a static documentation surface under the same Pages deployment and may be linked with a normal anchor to `/storybook/`.

At 390px, navigation may collapse into a compact keyboard-accessible disclosure/menu if needed; it must not become cramped or overflow.

## 16. Overview behavior

Overview remains the primary recruiter/reviewer entry point.

It should answer quickly:

1. what EvalOps Lab evaluates
2. what approved evidence exists
3. what claim boundaries apply
4. whether a regression comparison is available
5. where deeper evidence can be inspected

Suitable sections include:

- evidence snapshot
- featured/recent approved runs
- comparison snapshot
- claim/provenance boundary
- quick links to inspection surfaces

Do not add vanity metrics without evidence meaning.

## 17. `/runs/` index

Add a static route:

```text
/runs/
```

It reads only from the existing sanitized, allowlisted public evidence index.

The index is a scan/choose surface; run detail remains the inspect/verify surface.

Representative fields may include:

- artifact ID
- verification status
- data kind
- claim scope
- dataset/protocol
- concise metric summary
- execution metadata that is already approved for public use

The index links to existing `/runs/[artifactId]/` detail pages.

## 18. `/comparisons/` index

Add a static route:

```text
/comparisons/
```

It lists only comparison artifacts present in the approved public index.

Representative information may include:

- comparison ID
- reference artifact
- candidate artifact
- population compatibility
- overall result
- regression count
- claim scope

It links to:

```text
/comparisons/[artifactId]/
/comparisons/[artifactId]/failures/
```

Population compatibility and regression semantics remain exactly those defined by the public artifact/domain contract.

## 19. URL-driven filtering

The `/runs/` and `/comparisons/` indexes use lightweight client-side filtering with URL query parameters as the source of UI filter state.

Representative canonical query keys include:

```text
verification
data
scope
population
result
```

Examples:

```text
/runs/?verification=VERIFIED&data=SYNTHETIC_FIXTURE
/comparisons/?population=MATCHED&result=REGRESSION
```

Rules:

- source data remains static and sanitized
- URL parameters never override artifact truth
- supported values are validated against explicit enums/schema
- unknown values are ignored safely and must not create arbitrary semantic states
- filters across different dimensions use AND semantics
- browser back/forward must work
- refreshing or sharing a URL must reproduce the same valid filter state
- no LocalStorage or other persistence is introduced

A filtered-empty result must be visually and semantically different from an empty public source dataset.

Rich search, saved views, server queries, and broad multi-select behavior are out of scope unless implementation planning proves a minimal requirement.

## 20. Sorting and deterministic presentation

Index ordering must be deterministic and based only on public-contract fields whose semantics are trustworthy.

Do not invent a `latest` concept from a field that is not guaranteed to be chronological truth.

If an approved timestamp is suitable, use a documented deterministic primary ordering with artifact ID or another stable public identifier as tie-breaker. Otherwise retain a deterministic artifact/index order.

## 21. Accessibility requirements

Accessibility is a publication requirement, not optional polish.

Interactive components and production compositions must provide:

- visible focus states
- keyboard-operable controls
- appropriate accessible names
- semantic roles and native elements where possible
- contrast appropriate to supported WCAG expectations
- reduced-motion support
- non-color-only state communication

Representative public Storybook stories should cover light, dark, reduced-motion-relevant behavior, and viewports including 390px mobile, tablet, and desktop where the component is responsive.

## 22. Migration strategy

Phase 5A is implemented in two separately reviewable PRs.

### 22.1 Phase 5A.1 — Foundation

Primary deliverables:

- `DESIGN.md`
- semantic CSS token normalization
- locally bundled sans/mono typography or approved fallback
- local shadcn-compatible primitives needed by the product
- EvalOps semantic patterns
- Hybrid Storybook
- explicit public story allowlist
- Storybook build/interaction/accessibility CI
- public `/storybook/` deployment

Broad production-page redesign is intentionally avoided in 5A.1. Small production changes are allowed only where necessary to prove shared contracts and must not alter evidence semantics.

### 22.2 Phase 5A.2 — Adoption

Migrate shared/product surfaces in a controlled order:

```text
Product Shell
→ shared evidence/status patterns
→ Overview
→ Runs index
→ Run Detail
→ Comparisons index
→ Comparison Detail
→ Failure Explorer
```

Phase 5A.2 also adds URL-driven filtering and the new top-level index routes.

If a desired UI pattern requires data absent from the existing public contract, implementation must stop and treat that as a separate contract-design decision rather than add ad hoc frontend data.

## 23. Testing matrix

Testing responsibility remains layered:

```text
Domain/public contract tests
        ↓
Component/unit tests
        ↓
Storybook interaction + accessibility
        ↓
Production Playwright + axe
        ↓
GitHub Pages production verification
```

### 23.1 Python/repository gates

Do not weaken existing repository gates. When relevant, the canonical verification remains:

```bash
python -m pytest -q
ruff check .
ruff format --check .
mypy .
```

### 23.2 Unit/component tests

Vitest/Testing Library coverage should focus on meaning and behavior rather than brittle class-name assertions.

Required behavior candidates include:

- semantic state mappings
- metric directionality rendering
- active navigation state
- valid filter parsing/serialization
- invalid query values
- filtered-empty vs source-empty state
- clear-one / clear-all behavior

### 23.3 Storybook tests

Test only real interactions for interaction stories, such as:

- select/filter controls
- disclosure/popover behavior if present
- theme controls if the implementation exposes them at component level
- keyboard navigation

Pure presentation components do not need artificial interaction tests.

### 23.4 Production Playwright

Representative route groups include:

```text
/
/runs/
/runs/[artifactId]/
/comparisons/
/comparisons/[artifactId]/
/comparisons/[artifactId]/failures/
/storybook/
```

Critical production tests must cover, where applicable:

- navigation
- active route state
- light/dark theme
- keyboard behavior
- URL filtering
- refresh persistence through URL
- browser back/forward
- valid/unknown filter values
- zero-result filtering
- evidence labels and claim scope
- root overflow at 390px
- deliberate internal table scrolling
- axe serious/critical issues
- static asset availability
- unexpected external runtime requests

Representative screenshots should cover at least Overview light/dark, Runs filtered state, a regression comparison, Failure Explorer, and a 390px shell/catalog state.

## 24. CI and path coverage

Web/Pages workflows must run whenever design-system or product-surface behavior can change.

Relevant paths include at least:

```text
apps/web/components/**
apps/web/stories/**
apps/web/.storybook/**
apps/web/app/**
apps/web/lib/**
apps/web/public/**
apps/web/package*.json
apps/web/*config*
DESIGN.md
relevant public-evidence contract/export paths
```

The exact workflow path list must be based on the real repository layout during implementation planning.

Do not reduce existing Python/Web quality gates simply because the work is primarily frontend.

## 25. Public-output safety and leakage scanning

Before Pages assembly, scan the generated public output rather than source code alone.

Checks should detect accidental publication of:

- absolute Windows or Unix local paths
- obvious secret/token patterns
- `.env` material
- raw prompts/responses
- unapproved corpus/document text
- hidden reasoning/debug payloads
- internal story names/IDs
- unexpected source/debug artifacts

Legitimate public hashes or identifiers may require explicit classification rather than broad scanner disablement.

The public Storybook output must be mechanically checked for internal-story leakage.

## 26. External-request policy

Both the Evidence Console and public Storybook should operate from the same static deployment without third-party runtime service dependencies.

Phase 5A does not add:

- runtime font CDNs
- analytics/telemetry
- hosted icon services
- Chromatic/runtime visual-testing services
- remote design tokens
- external JSON/API calls
- embedded third-party widgets

Production browser verification must confirm the expected network boundary.

## 27. URL safety

Query parameters are presentation/filter state only and can never act as evidence authority.

For example:

```text
?verification=VERIFIED
```

means “show already-public records whose artifact verification status is VERIFIED.” It must never transform a non-verified artifact into a verified-looking state.

Malformed, duplicate, or unknown values must not introduce arbitrary labels, HTML, or unsafe state.

## 28. No claim amplification

Visual polish must never imply a stronger claim than the underlying artifact permits.

A synthetic integration demonstration must continue to read as:

```text
SYNTHETIC_FIXTURE
INTEGRATION_ONLY
```

It must not be presented as an official benchmark, production model superiority result, leaderboard, or state-of-the-art claim.

Avoid wording such as `best model`, `benchmark leader`, `production-ready accuracy`, or similar unsupported marketing language.

## 29. Failure handling

Use **fail closed, diagnose before bypass**.

If an unsupported evidence state is encountered:

```text
do not invent a visual mapping
→ render a safe unavailable state or fail validation/test
→ diagnose the contract mismatch
```

If an accessibility rule fails, do not disable the rule simply to green the build.

If mobile overflows, do not globally hide overflow.

If Storybook compatibility with Next.js 16 / React 19 is problematic, verify current official compatibility and choose a supported integration rather than random downgrades or unreviewed workarounds.

## 30. Production acceptance

### 30.1 Phase 5A.1 acceptance

5A.1 is complete only after:

- implementation PR reviewed and merged
- existing repository CI passes
- Storybook build/interaction/accessibility gates pass
- Pages deployment succeeds
- `/evalops-lab/storybook/` is reachable in production
- existing Evidence Console semantics remain intact
- public Storybook contains only curated public stories
- no unexpected external runtime requests are observed
- public-output leakage/security checks pass

### 30.2 Phase 5A.2 acceptance

5A.2 is complete only after:

- implementation PR reviewed and merged
- full relevant CI/E2E gates pass
- Pages deployment succeeds
- production browser verification covers Overview, Runs, Run Detail, Comparisons, Comparison Detail, Failure Explorer, and Storybook as relevant
- URL filters behave deterministically through refresh/back/forward
- 390px root pages do not horizontally overflow
- evidence tables remain intentionally scrollable where needed
- automated axe checks pass at the agreed severity threshold
- evidence/claim semantics remain unchanged
- no unexpected runtime network dependencies appear

README/DEPLOY production claims are updated only after fresh production verification.

## 31. Non-goals

Phase 5A does not include:

- interactive evaluation runner
- model inference
- uploads
- accounts/authentication
- database
- server/API layer
- persistence
- analytics or telemetry
- generic charting framework
- generic enterprise dashboard shell
- standalone design-system npm package
- a separate Storybook hosting product
- official benchmark claims
- Python evaluation-engine rewrite
- changed Phase 4 regression semantics
- saved views
- rich application search
- broad multi-select filtering without a proven need
- full-page Storybook duplication of the production app
- Phase 5B repository governance/portfolio work

## 32. Success signal

A reviewer should be able to open the live product and conclude, without reading repository internals:

1. EvalOps Lab presents a coherent, mature evaluation product rather than disconnected demo pages.
2. The visual system consistently separates verification, provenance, claim scope, regression, and compatibility semantics.
3. Runs and comparisons can be scanned and filtered without adding backend/runtime complexity.
4. Storybook demonstrates a real, intentional design system without exposing internal/debug material.
5. The public surfaces remain static, deterministic, accessible, evidence-safe, and explicit about synthetic/integration-only limitations.
6. Visual refinement has not changed the source or strength of any evidence claim.

If those conditions are met and all release gates pass, Phase 5A has achieved its purpose.