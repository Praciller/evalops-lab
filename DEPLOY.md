# EvalOps Evidence Console Deployment

## Production

- **Hosting:** GitHub Pages
- **Canonical URL:** https://praciller.github.io/evalops-lab/
- **Public Storybook:** https://praciller.github.io/evalops-lab/storybook/
- **Source branch:** `main`
- **Frontend:** `apps/web`
- **Production base path:** `/evalops-lab`
- **Static artifact:** `apps/web/out`
- **Deployment workflow:** `.github/workflows/pages.yml`
- **Provider credentials:** none

The Evidence Console is a static, read-only presentation of the checked-in Public Evidence Contract V1 bundle. Deployment does not execute evaluators, call model providers, download external datasets, or publish raw corpus/model-response data.

## Build and verification

The Pages workflow runs the frontend quality gates, builds and verifies the curated public Storybook, assembles the Pages-mode static export, verifies the `/evalops-lab` browser path, checks the expected generated routes, and uploads only `apps/web/out` with the official GitHub Pages artifact action.

Local Pages-mode verification:

```bash
cd apps/web
npm ci
npm run lint
npm run typecheck
npm test
npm run storybook:build:public
node scripts/verify-public-storybook.mjs
npm run storybook:test
npm run build:pages
npm run test:e2e:pages
```

The checked-in public evidence remains guarded by the Python test that requires freshly generated demo evidence to be byte-identical to `apps/web/public/evidence/`.

## First verified deployment

- **Deployed commit:** `efd6ba214b95a99c71de018983ce09c1111c123f`
- **GitHub Actions run:** `33971676615`
- **Verified URL:** https://praciller.github.io/evalops-lab/

The deployment job reported success and GitHub returned the canonical environment URL above. Production smoke verification confirmed HTTP 200 for the Overview and both generated run-detail routes, visible `SYNTHETIC_FIXTURE` / `INTEGRATION_ONLY` labels, zero serious/critical axe violations on checked routes, working dark-theme toggle, and no unexpected external requests.

## Phase 4 verified deployment

- **Deployed commit:** `8ac61656b27e827a9d1008631e6067f92f5f857e`
- **EvalOps CI:** `33981831150` — success
- **Web Evidence Console CI:** `33981831135` — success
- **GitHub Pages:** `33981831167` — success
- **Comparison:** https://praciller.github.io/evalops-lab/comparisons/demo-retrieval-regression-v1/
- **Failure Explorer:** https://praciller.github.io/evalops-lab/comparisons/demo-retrieval-regression-v1/failures/

Production browser verification covered the Overview, comparison, Failure Explorer, reference run, and candidate run. All five routes returned HTTP 200. The comparison rendered `MATCHED`, four aggregate `REGRESSION` rows and one `PASS`, and the evidence-correct two-record change summary. The Failure Explorer kept `THQA-002` as `Persistent category` but excluded it from changed-only results; `THQA-004` remained an introduced failure and `THQA-005` a stable pass with metric deltas. Checked comparison/explorer routes had zero axe violations, dark theme worked, 390 px pages had no root horizontal overflow while wide tables scrolled internally, and no unexpected external requests or HTTP >=400 responses were observed.

This remains `SYNTHETIC_FIXTURE` + `INTEGRATION_ONLY` evidence. It is not an official benchmark result or model-superiority claim.

## Evidence Console Phase 5A.1 verified deployment

- **Deployed commit:** `f2c2bc2973206a58f1895b832589d082ffb84ec7`
- **EvalOps CI:** `34012232212` — success
- **Web Evidence Console CI:** `34012232221` — success
- **GitHub Pages:** `34012232095` — success
- **Public Storybook:** https://praciller.github.io/evalops-lab/storybook/

Fresh production browser verification confirmed HTTP 200 for the Evidence Console and public Storybook. The Storybook production index contained exactly 12 curated public titles with no internal/debug title leakage. Light and dark `colorScheme` rendering both worked, the checked 390 px story had no root horizontal overflow, and axe reported zero violations on the checked Overview and Storybook story. No unexpected third-party runtime requests or HTTP >=400 responses were observed.

This release adds the Evidence Design System foundation and curated component catalog only. Existing public evidence remains `SYNTHETIC_FIXTURE` + `INTEGRATION_ONLY`; the Storybook does not expand the Public Evidence Contract or support benchmark/model-superiority claims.

## Evidence Console Phase 5A.2 verified deployment

- **Deployed commit:** `b4eda4394795aeaf83436ac406e50289f2f0bd1b`
- **EvalOps CI:** `34020372319` — success
- **Web Evidence Console CI:** `34020372287` — success
- **GitHub Pages:** `34020372326` — success
- **Runs catalog:** https://praciller.github.io/evalops-lab/runs/
- **Comparisons catalog:** https://praciller.github.io/evalops-lab/comparisons/
- **Public Storybook:** https://praciller.github.io/evalops-lab/storybook/

Fresh production browser verification covered the Overview, filtered Runs and Comparisons catalogs, Comparison Detail, Failure Explorer, and a representative public Storybook story. The filtered Runs catalog rendered three verified synthetic artifacts and duplicate single-select query values remained inert. The filtered Comparisons catalog rendered the validated `MATCHED` comparison with four aggregate regressions and one pass. Comparison Detail retained the two-record change summary, while changed-only Failure Explorer results excluded `THQA-002` and included `THQA-004` and `THQA-005`.

Axe reported zero violations on all checked surfaces. At 390 px, the Overview, Runs, Comparisons, Comparison Detail, Failure Explorer, and checked Storybook story had no root horizontal overflow. The production Storybook index still exposed exactly 12 curated public titles with zero internal/debug title leakage. No unexpected third-party runtime requests or HTTP >=400 responses were observed during the production smoke run.

This remains `SYNTHETIC_FIXTURE` + `INTEGRATION_ONLY` evidence. URL filters are presentation state only and cannot override artifact semantics. Phase 5A.2 adds no runtime API, inference, authentication, persistence, analytics, database, or external data-fetch path.

## Phase 5B verification

- **Phase 5B.1:** PR [#27](https://github.com/Praciller/evalops-lab/pull/27), merged commit `bfda0b165dda5dcdc6c9cf5532b8c2b051ebf085`.
- **Phase 5B.2-A:** PR [#40](https://github.com/Praciller/evalops-lab/pull/40), merged commit `0cf7baa062f89d10990e6e330a55f8473e0931e0`.
- **Accepted final `main`:** `0cf7baa062f89d10990e6e330a55f8473e0931e0`.
- **Final-head checks:** EvalOps CI `34035285132`, Web Evidence Console CI `34035285108`, CodeQL `34035285164`, and Dependency Review `34035285137` — all successful on the Phase 5B.2-A head.
- **Post-merge checks:** EvalOps CI `34035554745` and CodeQL `34035554744` — successful on the accepted `main` commit.
- **Pages:** workflow run `34035570914` — successful with `headSha` equal to the accepted final `main` commit.
- **Production verification:** `2026-09-06 20:21 +07:00` against the canonical Pages URL.

Verified routes:

- https://praciller.github.io/evalops-lab/
- https://praciller.github.io/evalops-lab/runs/
- https://praciller.github.io/evalops-lab/comparisons/
- https://praciller.github.io/evalops-lab/comparisons/demo-retrieval-regression-v1/
- https://praciller.github.io/evalops-lab/comparisons/demo-retrieval-regression-v1/failures/
- https://praciller.github.io/evalops-lab/storybook/

The five Evidence Console routes returned HTTP 200, had zero axe violations,
no root horizontal overflow at 390 px, and no unexpected external runtime
requests. The public Storybook route had no root overflow and exposed the
curated public story set without internal/debug titles. The public evidence
remains `VERIFIED` / `SYNTHETIC_FIXTURE` / `INTEGRATION_ONLY`; it is not an
official benchmark or model-superiority result.

The active `main-governance` ruleset requires pull requests, resolved review
threads, the `quality`, `web`, CodeQL, and `Dependency Review` checks, and
squash-only merges. It blocks deletion and non-fast-forward updates; its
required approval count is zero. Wiki and Discussions are disabled. Repository
license is MIT. The recruiter metadata is synchronized as follows:

- **Description:** `AI evaluation framework for RAG regression, failure analysis, and reproducible evidence.`
- **Homepage:** https://praciller.github.io/evalops-lab/
- **Topics:** `ai-evaluation`, `llm-evaluation`, `rag-evaluation`, `ai-engineering`, `reliability`, `testing`, `python`

The README screenshots were not changed in Phase 5B.2 because the change was
presentation/documentation-only and the public route output remained unchanged.
The checked-in `overview-desktop.png`, `comparison-desktop.png`, and
`failure-explorer-desktop.png` retain the Phase 5A.2 production provenance at
commit `b4eda4394795aeaf83436ac406e50289f2f0bd1b`; final production routes
were re-verified after the Phase 5B.2 merge. A pixel-for-pixel recapture at the
final SHA was not performed.

### Final canonical readback

After the documentation closure PR [#41](https://github.com/Praciller/evalops-lab/pull/41),
the canonical `main` commit is `168ba90fdf1b036d5c874949d5d5209120ca11fe`.
EvalOps CI run `34036041914` and CodeQL run `34036041903` completed
successfully at that SHA. The SHA-matched Pages run is `34036071846`, which
completed successfully and ran the Pages-mode browser/static-output checks.
The final Phase 5B recruiter presentation is therefore
`COMPLETE_WITH_LIMITATIONS`: the README, production verification, metadata,
governance record, and evidence boundaries are complete, but the planned
milestone release gate is not re-run because `v0.1.0` already exists.

The pre-existing `v0.1.0` tag resolves to `f50c725c13db58abf7a62c7b0f2d678539984a5f`
and its published release predates Phase 5B. It remains unchanged; no tag or
release was force-replaced. Phase 5B must not be described as the target of that
existing release, and Issue #26 remains open for owner-level acceptance of this
release limitation.

## Redeploy

An eligible change pushed to `main` triggers `.github/workflows/pages.yml`. The workflow can also be started with `workflow_dispatch`.

## Rollback

Revert the offending `main` commit (or restore a known-good commit through the normal PR workflow) and allow the Pages workflow to redeploy that static output. Do not edit the deployed Pages artifact manually.

## Evidence regeneration

```bash
python scripts/generate_public_demo_evidence.py
```

Commit regenerated evidence only when the deterministic drift guard and the full Python/Web validation suite pass.
