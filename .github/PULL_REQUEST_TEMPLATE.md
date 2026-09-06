## Summary

<!-- What changed and why? Keep this concise and evidence-oriented. -->

## Scope

- [ ] I kept this change within the linked issue and stated non-goals.
- [ ] I did not change evaluation formulas, thresholds, ground truth, or failure semantics without explicit scope.

## Evidence / claim impact

<!-- What evidence supports this change? Does it change what the repository can claim? Preserve SYNTHETIC_FIXTURE and INTEGRATION_ONLY boundaries. -->

## Verification

<!-- List exact commands and their results. Link hosted runs where available. -->

- [ ] Python tests and static checks, when applicable.
- [ ] CLI or artifact verification, when applicable.
- [ ] Web, Storybook, accessibility, static-build, and browser checks, when applicable.

### Conditional verification checklist

- [ ] Evaluator/metric change: added semantic tests and regression coverage; documented formula/threshold impact.
- [ ] Public evidence contract/export change: validated strict schemas, sanitized output, generated-output drift, and frontend consumers.
- [ ] UI change: ran lint, typecheck, unit, Storybook, axe/Playwright, mobile overflow, and reviewed visual evidence as applicable.
- [ ] Dependency/workflow change: reviewed action/dependency provenance, immutable pins, permissions, and relevant security checks.
- [ ] Docs-only change: checked links, rendering-sensitive syntax, claim boundaries, and relevant documentation validation.

## Security & public-data boundary

- [ ] No API keys, tokens, credentials, `.env` files, private prompts/responses, hidden reasoning, raw private evidence, raw external datasets, or machine-local paths are included.
- [ ] Public evidence remains fail-closed and exposes only the approved artifact allowlist.
- [ ] Security-sensitive issues are not disclosed in this PR description or public issue discussion.

## UI evidence (when applicable)

<!-- Include routes, screenshots, accessibility results, and production-vs-local status when the UI changes. -->

## Limitations

<!-- State what remains unverified, synthetic, integration-only, owner-gated, or planned. -->

## Related issue

<!-- Link the issue, for example: Closes #25 or Related to #25. -->
