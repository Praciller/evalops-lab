# EvalOps Evidence Console Deployment

## Production

- **Hosting:** GitHub Pages
- **Canonical URL:** https://praciller.github.io/evalops-lab/
- **Source branch:** `main`
- **Frontend:** `apps/web`
- **Production base path:** `/evalops-lab`
- **Static artifact:** `apps/web/out`
- **Deployment workflow:** `.github/workflows/pages.yml`
- **Provider credentials:** none

The Evidence Console is a static, read-only presentation of the checked-in Public Evidence Contract V1 bundle. Deployment does not execute evaluators, call model providers, download external datasets, or publish raw corpus/model-response data.

## Build and verification

The Pages workflow runs the frontend quality gates, builds the Pages-mode static export, verifies the `/evalops-lab` browser path, checks the expected generated routes, and uploads only `apps/web/out` with the official GitHub Pages artifact action.

Local Pages-mode verification:

```bash
cd apps/web
npm ci
npm run lint
npm run typecheck
npm test
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

## Redeploy

An eligible change pushed to `main` triggers `.github/workflows/pages.yml`. The workflow can also be started with `workflow_dispatch`.

## Rollback

Revert the offending `main` commit (or restore a known-good commit through the normal PR workflow) and allow the Pages workflow to redeploy that static output. Do not edit the deployed Pages artifact manually.

## Evidence regeneration

```bash
python scripts/generate_public_demo_evidence.py
```

Commit regenerated evidence only when the deterministic drift guard and the full Python/Web validation suite pass.
