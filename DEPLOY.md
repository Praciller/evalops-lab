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

## Redeploy

An eligible change pushed to `main` triggers `.github/workflows/pages.yml`. The workflow can also be started with `workflow_dispatch`.

## Rollback

Revert the offending `main` commit (or restore a known-good commit through the normal PR workflow) and allow the Pages workflow to redeploy that static output. Do not edit the deployed Pages artifact manually.

## Evidence regeneration

```bash
python scripts/generate_public_demo_evidence.py
```

Commit regenerated evidence only when the deterministic drift guard and the full Python/Web validation suite pass.
