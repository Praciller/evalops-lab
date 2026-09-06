# EvalOps Evidence Console Design System

## Direction

The console follows **Evidence over decoration**: every visual decision should make an evidence claim easier to inspect, compare, or qualify. The product direction is a **Modern Product Console** with a refined neutral/slate foundation, a restrained blue accent, and balanced density. Borders provide most separation; small-to-medium radii are preferred, while shadows are reserved for real overlays.

Blue is used for navigation, focus, selection, and evidence/action affordances. Success, caution, danger, and scope colors are semantic states. Status is never conveyed by color alone: a visible text label and appropriate semantic structure are required.

## Semantic tokens

`src/app/globals.css` is the single implementation of the token system used by production and Storybook. Light and dark modes use the same semantic names:

- surfaces: `canvas`, `surface`, `surface-muted`
- text and separation: `ink`, `ink-muted`, `line`, `line-strong`
- action: `accent`, `accent-soft`
- states: `success`, `success-soft`, `caution`, `caution-soft`, `danger`, `danger-soft`
- evidence scope: `scope`, `scope-soft`

The spacing scale is `2xs`, `xs`, `sm`, `md`, `lg`, `xl`, `2xl`. Radius tokens are `sm`, `md`, and `lg`. Focus treatment, control height, and border emphasis are tokenized as well. Components consume semantic tokens or Tailwind mappings; they do not introduce a second visual-token system in TypeScript.

## Typography

Geist Sans and Geist Mono are bundled locally through `geist@1.7.2`; no runtime font request is allowed. Sans is used for navigation, headings, body copy, controls, labels, and tables. Mono is limited to technical values such as metrics, artifact IDs, record IDs, revisions, hashes, and protocol/version identifiers. Important numeric comparisons use tabular numerals.

## Component boundaries

The local UI layer in `src/components/ui/` contains generic, semantic primitives: buttons, badges, cards, inputs, selects, separators, and tables. These components do not know EvalOps statuses or claim policy. Domain-aware presentation belongs in `src/components/evidence/`, where schema-derived unions and exhaustive mappings keep evidence vocabulary typed.

Pages compose primitives and evidence patterns. A page may not inject arbitrary semantic labels, arbitrary status colors, raw evidence internals, or a stronger claim than the checked-in public contract permits.

## Evidence visual grammar

The console distinguishes these dimensions:

- verification: `VERIFIED`, `PARTIAL`, `UNVERIFIED`, `NOT_RUN`
- data kind: `SYNTHETIC_FIXTURE`, `CURATED_DATASET`, `OFFICIAL_BENCHMARK`
- claim scope: `INTEGRATION_ONLY`, `PROTOCOL_SPECIFIC`, `BENCHMARK_RESULT`
- regression: `PASS`, `REGRESSION`
- population compatibility: `MATCHED`, `UNVERIFIED`, `INCOMPATIBLE`

Synthetic demonstrations retain `SYNTHETIC_FIXTURE` and `INTEGRATION_ONLY` visibly. Unsupported or invalid evidence is rendered as unavailable or unsupported, never as success. Metric deltas interpret metric directionality; a positive raw sign is not automatically an improvement.

## Tables, density, and responsive behavior

Evidence tables remain semantic HTML tables with keyboard-accessible headers, consistent numeric alignment, technical typography, and deliberate internal horizontal scrolling where comparison requires it. At 390px, root-page horizontal overflow is forbidden. Tables may scroll inside their own bounded container. Global `overflow-x: hidden` is prohibited because it masks layout defects.

Use balanced spacing for control gaps, card padding, section rhythm, and page rhythm. Mobile layouts stack or wrap intentionally rather than merely compressing desktop layouts.

## Accessibility

Use native interactive elements and semantic headings, labels, table headers, and status text. Every focusable control has a visible `:focus-visible` treatment. Storybook runs the a11y addon with violations treated as errors. Reduced-motion preferences disable meaningful transitions and animations while preserving the information hierarchy.

## Hybrid Storybook boundary

The internal Storybook at `.storybook/` is the development catalog and may load public stories plus explicitly named internal stress stories. The public Storybook at `.storybook-public/` uses a positive allowlist of `src/stories/public/**/*.public.stories.@(ts|tsx)` and is the only Storybook subtree copied into the static Pages output at `/evalops-lab/storybook/`.

Public stories use synthetic, safe props and preserve evidence labels. They may not expose raw prompts, answers, corpus text, hidden reasoning, local paths, secrets, provider data, or unsupported production claims. Internal/debug stories and broad stress cases never enter the public build.

## Prohibited patterns

Do not add hosted font dependencies, runtime fetches, APIs, server actions, providers, authentication, persistence, analytics, or a new visual-token registry for this foundation phase. Do not use decorative gradients, excessive shadows, card-everything treatment, arbitrary colors, or copy that amplifies synthetic or integration-only evidence into a benchmark or production claim. Broad production-page migration and `/runs/` or `/comparisons/` index pages are deferred to Phase 5A.2.
