# EvalOps Evidence Console design direction

This document defines the future visual system for a public, static, read-only Evidence Dashboard. It does not authorize frontend implementation in Phase 1.

## Product stance

Evidence over decoration. The interface should make provenance, claim boundaries, metric meaning, and limitations easy to inspect. Every visual summary must link back to a named artifact and its verification context.

## Visual system

- **Color roles**: warm neutral canvas and surfaces; slate text and borders; blue for navigation and selected evidence; green for verified/pass; amber for partial or caution; red for failure/regression; indigo for benchmark/protocol context. Status is never communicated by color alone.
- **Typography**: a highly legible sans-serif for UI and prose; monospace only for run IDs, artifact IDs, commit hashes, commands, and machine values. Use tabular numerals for metric tables.
- **Spacing**: a compact 4px base scale, with 16px card padding, 24px section rhythm, and 32px page grouping. Dense tables may tighten row spacing but must retain readable hit targets.
- **Shape and elevation**: 8px card radius, 6px controls, 1px neutral borders, and restrained shadows only for layered controls. Avoid glossy or decorative gradients.

## Layout and responsive behavior

Desktop uses a narrow provenance sidebar plus a flexible evidence canvas. The primary scan path is: artifact identity and status, headline metrics, evidence table, comparison or failure detail, limitations, provenance. At tablet width the sidebar becomes a top context bar. On mobile, cards stack, tables become horizontally scrollable or switch to labeled rows, and filters remain reachable without hiding claim status.

## Information display

Use metric cards for a small set of headline values, tables for exact comparisons and record-level evidence, and restrained charts only when trends or deltas are materially easier to understand visually. Always show metric names, `k` where applicable, directionality, and denominators when available. Never use a chart to imply statistical significance that the artifact does not establish.

## Accessibility and states

Keyboard navigation, visible focus, semantic headings, sufficient contrast, reduced-motion support, and text labels for all statuses are required. Loading, empty, error, unavailable, and not-run states must explain what evidence is missing and why. A limitation must be visible near the claim it qualifies, not hidden in a tooltip. Dark mode should preserve the same semantic color roles with tested contrast rather than simply invert colors.

## Component vocabulary

Future components should include: `EvidenceHeader`, `VerificationBadge`, `ClaimScopeBadge`, `DataKindBadge`, `MetricCard`, `MetricTable`, `EvidenceTable`, `FailureSummary`, `ComparisonPanel`, `ProvenancePanel`, `LimitationsPanel`, `ArtifactSelector`, `EmptyState`, and `ErrorState`.

## Non-goals

No public write actions, model execution, prompt playground, chat surface, runtime API dependency, or dashboard claim that is not present in an approved artifact.
