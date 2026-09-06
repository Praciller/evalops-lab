# Phase 5B.1 Repository Governance & Supply-chain Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` for this repository. Before source work, use `superpowers:using-git-worktrees` to create an isolated worktree from the canonical remote base. Do not use `subagent-driven-development` or delegate to subagents unless the owner explicitly requests delegation. Track execution with the checkbox steps in this plan.

**Goal:** Add credible, low-noise solo-production governance, native GitHub security/dependency automation, and enforceable `main`-branch policy without changing EvalOps evaluation semantics or public runtime behavior.

**Architecture:** Implement version-controlled governance/security first, prove every new required check on a pull request, then perform repository-setting enforcement as a separate acceptance boundary. Required checks must be taken from real successful check contexts; no ruleset is enabled before the corresponding workflows have passed. Repository settings are read-before-write and read-after-write, with no destructive protection tests.

**Tech Stack:** GitHub Actions, GitHub CodeQL, Dependency Review Action, Dependabot, GitHub repository rulesets/settings, Python 3.11+/3.12 CI, Node.js 22, Next.js 16.3.4, React 19.2.8, Storybook 10.6.0, Playwright Chromium.

**Spec:** `docs/superpowers/specs/2026-09-06-phase-5b-repository-governance-recruiter-evidence-design.md`

## Global constraints

- Preserve evaluation formulas, thresholds, failure semantics, public artifact schemas, and current checked-in evidence exactly unless a separate approved phase changes them.
- Preserve `SYNTHETIC_FIXTURE` and `INTEGRATION_ONLY`; do not create benchmark or model-superiority claims.
- Do not add external AI/provider calls, API routes, server actions, auth, persistence, analytics, databases, paid scanners, or hosted security SaaS.
- Do not commit secrets, credentials, `.env` files, raw external datasets, raw prompts/responses, private artifacts, hidden reasoning, or machine-local paths.
- Use GitHub-native security surfaces only in this phase.
- Do not require an external reviewer or CODEOWNERS approval for the solo-maintained workflow.
- Do not require signed commits or strict branch-up-to-date status.
- Do not configure a new check as required until that exact check context has completed successfully on the final 5B.1-A PR head.
- Do not test force-push/deletion protection by actually force-pushing or deleting `main`.
- Preserve unrelated local commits/dirty state. The ordinary local checkout is not a trusted clean base.
- Stop if owner-authenticated GitHub settings access is unavailable for an enforcement step; report that boundary rather than guessing.

---

## Intended file delta

Create:

- `LICENSE`
- `CONTRIBUTING.md`
- `SECURITY.md`
- `.github/CODEOWNERS`
- `.github/PULL_REQUEST_TEMPLATE.md`
- `.github/ISSUE_TEMPLATE/bug_report.yml`
- `.github/ISSUE_TEMPLATE/evaluation_proposal.yml`
- `.github/ISSUE_TEMPLATE/config.yml`
- `.github/dependabot.yml`
- `.github/workflows/codeql.yml`
- `.github/workflows/dependency-review.yml`

Modify as required by supply-chain policy:

- `.github/workflows/ci.yml`
- `.github/workflows/web-ci.yml`
- `.github/workflows/pages.yml`

Repository settings changed only after the 5B.1-A PR is proven and merged:

- merge methods
- delete-head-branch behavior
- Wiki/Discussions/Projects feature state
- private vulnerability reporting when supported and verifiable
- repository ruleset for `main`

---

## Task 1: Establish a clean Phase 5B.1 execution base and record pre-state

**Files:** No source modification.

**Interfaces:** Git, GitHub CLI/API, repository metadata/rulesets/check runs.

- [ ] **Step 1: Read required execution skills before touching the repository**

Read `superpowers:using-git-worktrees`, then `superpowers:executing-plans`. Do not invoke a delegation/subagent workflow.

- [ ] **Step 2: Fetch remote state without rewriting the ordinary checkout**

From the existing repository checkout:

```bash
git fetch origin --prune
git status --short
git rev-parse HEAD
git rev-parse origin/main
git log --oneline --decorate -5 origin/main
```

Expected: record the ordinary checkout state and canonical `origin/main`. If the ordinary checkout contains local divergence or dirty files, leave them untouched.

- [ ] **Step 3: Create an isolated worktree from canonical `origin/main`**

Use a new branch such as:

```bash
git worktree add ../evalops-lab-phase-5b1 -b feat/phase-5b1-governance origin/main
cd ../evalops-lab-phase-5b1
git status --short
git rev-parse HEAD
git rev-parse origin/main
```

Expected: clean status and `HEAD == origin/main` at creation time.

- [ ] **Step 4: Confirm the approved spec exists on the base**

```bash
test -f docs/superpowers/specs/2026-09-06-phase-5b-repository-governance-recruiter-evidence-design.md
```

Expected: PASS. If the spec is not yet on canonical `main`, stop. Do not implement against an unmerged design branch.

- [ ] **Step 5: Capture repository/GitHub pre-state**

Use owner-authenticated `gh` where available:

```bash
gh repo view Praciller/evalops-lab --json nameWithOwner,description,homepageUrl,repositoryTopics,hasIssuesEnabled,hasProjectsEnabled,hasWikiEnabled,deleteBranchOnMerge,mergeCommitAllowed,rebaseMergeAllowed,squashMergeAllowed
gh api repos/Praciller/evalops-lab/rulesets
```

Also record whether private vulnerability reporting can be read/configured with the owner token. Do not mutate yet.

Expected pre-state based on the approved design review: public repo, Pages enabled, Wiki currently enabled, Discussions disabled, no MIT license detected, and no repository ruleset. Treat fresh execution output as authoritative.

**Commit:** none.

---

## Task 2: Add license, contributor contract, security policy, and explicit ownership

**Files:**

- Create: `LICENSE`
- Create: `CONTRIBUTING.md`
- Create: `SECURITY.md`
- Create: `.github/CODEOWNERS`

**Interfaces:** GitHub license detection; CODEOWNERS path matching; project security/evidence boundaries.

- [ ] **Step 1: Write a failing static pre-check for expected governance files**

Run before creation:

```bash
python - <<'PY'
from pathlib import Path
required = [
    "LICENSE",
    "CONTRIBUTING.md",
    "SECURITY.md",
    ".github/CODEOWNERS",
]
missing = [p for p in required if not Path(p).is_file()]
assert not missing, f"missing: {missing}"
PY
```

Expected: FAIL listing the four missing files.

- [ ] **Step 2: Add canonical MIT text**

Create `LICENSE` using the canonical MIT License text with:

```text
Copyright (c) 2026 Pakon Poomson
```

Do not add terms for external datasets/model weights; the project license does not override upstream asset terms.

- [ ] **Step 3: Add the technical contributor contract**

`CONTRIBUTING.md` must include:

- supported Python/Node setup and links to deeper reproducibility docs;
- scoped branch → tests → PR → CI → squash flow;
- deterministic evaluation/testing expectations;
- requirement that metric/evaluator semantic changes are explicit and tested;
- public artifact sanitization/fail-closed boundary;
- `SYNTHETIC_FIXTURE` / `INTEGRATION_ONLY` claim discipline;
- frontend verification requirements when UI changes;
- prohibition on secrets, raw external datasets, private prompts/responses/artifacts;
- normal contributors do not create release tags.

Keep commands synchronized with `AGENTS.md` and actual package scripts.

- [ ] **Step 4: Add operational SECURITY.md**

Document supported security scope as latest `main` and latest milestone release. Direct sensitive reports to GitHub Private Vulnerability Reporting **only if it is enabled/verified later**; until then phrase the policy so it does not invent an unavailable private channel. Explicitly classify sensitive surfaces: secrets, private evidence exposure, sanitization bypass, path traversal/unintended publication, and workflow/dependency supply-chain compromise.

Public issues must be explicitly discouraged for undisclosed vulnerabilities.

- [ ] **Step 5: Add minimal explicit CODEOWNERS using real paths**

Start with:

```text
* @Praciller
/src/evalops/ @Praciller
/src/evalops/export/ @Praciller
/apps/web/ @Praciller
/.github/workflows/ @Praciller
/.github/CODEOWNERS @Praciller
/CONTRIBUTING.md @Praciller
/SECURITY.md @Praciller
/LICENSE @Praciller
```

Before committing, verify every non-file directory rule exists in the current tree.

- [ ] **Step 6: Re-run the static governance file check**

Expected: PASS.

- [ ] **Step 7: Inspect whitespace and secret-like content**

```bash
git diff --check
git diff -- LICENSE CONTRIBUTING.md SECURITY.md .github/CODEOWNERS
```

Run the repository's existing secret scan if one exists. Otherwise use a conservative source grep for credential assignment patterns, without printing environment values.

- [ ] **Step 8: Commit the slice**

```bash
git add LICENSE CONTRIBUTING.md SECURITY.md .github/CODEOWNERS
git commit -m "docs: add governance and security foundations"
```

---

## Task 3: Add lean structured issue intake and pull-request contract

**Files:**

- Create: `.github/ISSUE_TEMPLATE/bug_report.yml`
- Create: `.github/ISSUE_TEMPLATE/evaluation_proposal.yml`
- Create: `.github/ISSUE_TEMPLATE/config.yml`
- Create: `.github/PULL_REQUEST_TEMPLATE.md`

**Interfaces:** GitHub Issue Forms schema; PR authoring contract.

- [ ] **Step 1: Add a syntax-validation pre-check that currently fails**

Use Python with PyYAML only if already available; do not add a project dependency solely for this check. Preferred no-dependency route when Ruby is available on the GitHub runner/local environment:

```bash
ruby -e 'require "yaml"; Dir[".github/ISSUE_TEMPLATE/*.yml"].each { |f| YAML.load_file(f); puts f }'
```

Expected before creation: no form files found, which is treated as failing the task acceptance check.

- [ ] **Step 2: Create `bug_report.yml`**

Required fields:

- affected surface dropdown/text;
- observed behavior;
- expected behavior;
- reproducible steps;
- environment/version;
- artifact/run identifier when relevant;
- acknowledgement that security-sensitive issues must not be disclosed publicly.

Include a visible security warning near the top.

- [ ] **Step 3: Create `evaluation_proposal.yml`**

Required fields:

- problem/evaluation question;
- intended evidence/capability;
- proposed scope;
- evaluator/metric/public-contract/UI impact;
- expected claim implications;
- acceptance evidence.

Avoid forms that invite unsupported benchmark claims.

- [ ] **Step 4: Disable blank issues**

`config.yml` must set:

```yaml
blank_issues_enabled: false
```

Do not add fake contact links. Add a security contact link only if Private Vulnerability Reporting exposes a stable supported destination that is verified.

- [ ] **Step 5: Create one PR template**

Sections must cover:

```text
Summary
Scope
Evidence / claim impact
Verification
Security & public-data boundary
UI evidence (when applicable)
Limitations
Related issue
```

Conditional checklist items must distinguish evaluator/public-contract/UI/dependency/docs-only changes.

- [ ] **Step 6: Validate YAML and inspect template content**

```bash
ruby -e 'require "yaml"; Dir[".github/ISSUE_TEMPLATE/*.yml"].each { |f| YAML.load_file(f); puts "OK #{f}" }'
grep -n "SYNTHETIC_FIXTURE\|INTEGRATION_ONLY\|Security\|Evidence" .github/PULL_REQUEST_TEMPLATE.md .github/ISSUE_TEMPLATE/*.yml
```

Expected: all YAML parses; evidence/security boundaries are present.

- [ ] **Step 7: Commit**

```bash
git add .github/ISSUE_TEMPLATE .github/PULL_REQUEST_TEMPLATE.md
git commit -m "chore: add structured issue and pull request intake"
```

---

## Task 4: Add low-noise Dependabot policy

**Files:**

- Create: `.github/dependabot.yml`

**Interfaces:** Python project at `/`, npm project at `/apps/web`, GitHub Actions at `/`.

- [ ] **Step 1: Confirm the dependency roots before writing config**

```bash
test -f pyproject.toml
test -f apps/web/package-lock.json
test -d .github/workflows
```

Expected: PASS.

- [ ] **Step 2: Create weekly Dependabot entries**

Add `version: 2` updates for:

- `pip`, directory `/`, weekly;
- `npm`, directory `/apps/web`, weekly;
- `github-actions`, directory `/`, weekly.

Set a reasonable `open-pull-requests-limit` per ecosystem. Group non-major routine updates where supported. Keep major upgrades separately reviewable rather than folding them into a broad group.

Do not change package managers or introduce lockfiles unrelated to the existing projects.

- [ ] **Step 3: Validate syntax and semantics**

Parse YAML locally and inspect directories/package managers. Expected: valid YAML and all configured directories exist.

- [ ] **Step 4: Commit**

```bash
git add .github/dependabot.yml
git commit -m "chore: configure low-noise dependency updates"
```

---

## Task 5: Harden existing workflow action references and make Web CI safe as a required check

**Files:**

- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/web-ci.yml`
- Modify: `.github/workflows/pages.yml`

**Interfaces:** Existing GitHub Actions jobs `quality`, `web`, Pages build/deploy; future ruleset required-check contexts.

**Critical design consequence:** `web-ci.yml` currently path-filters pull requests. A globally required Web check would be absent on governance/docs-only PRs and could deadlock `main`. Therefore the pull-request trigger must become unconditional before the Web check can be globally required. The push trigger may remain path-filtered.

- [ ] **Step 1: Inventory all current `uses:` references**

```bash
grep -R -nE '^\s*-?\s*uses:' .github/workflows
```

Record every action owner/repository and current major tag.

- [ ] **Step 2: Resolve each current action major to a fresh immutable commit SHA**

For each current action/tag, use owner-authenticated GitHub API, for example:

```bash
gh api repos/actions/checkout/git/ref/tags/v4 --jq '.object.sha'
gh api repos/actions/setup-python/git/ref/tags/v5 --jq '.object.sha'
```

Repeat for the actual versions present in all three workflows (`checkout`, `setup-python`, `setup-node`, `configure-pages`, `upload-pages-artifact`, `deploy-pages`, etc.). Do **not** paste plan-time SHAs without resolving them again at execution time.

- [ ] **Step 3: Pin every external action to a full 40-character SHA**

Use readable comments such as:

```yaml
uses: actions/checkout@<40-char-sha> # v4
```

Keep official/reputable actions only.

- [ ] **Step 4: Make Web CI unconditional for pull requests**

Change `web-ci.yml` so:

```yaml
pull_request:
```

has no `paths:` filter, while `push.paths` may stay scoped. Do not reduce the existing Web verification steps.

- [ ] **Step 5: Preserve minimum permissions**

Ensure existing workflows remain at `contents: read` unless a job has a proven additional requirement. Do not add `pull_request_target`.

- [ ] **Step 6: Add a static SHA-pin verifier before considering the task complete**

Run:

```bash
python - <<'PY'
import pathlib, re
bad = []
for path in pathlib.Path('.github/workflows').glob('*.yml'):
    for line_no, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        m = re.search(r'uses:\s*([^\s]+)@([^\s#]+)', line)
        if not m:
            continue
        ref = m.group(2)
        if not re.fullmatch(r'[0-9a-f]{40}', ref):
            bad.append(f'{path}:{line_no}:{m.group(1)}@{ref}')
assert not bad, 'unpinned actions:\n' + '\n'.join(bad)
print('all workflow actions pinned')
PY
```

Expected: PASS after all existing workflow refs are pinned. This check will also cover the new workflows added next.

- [ ] **Step 7: Parse workflow YAML and inspect diff**

Use a local YAML parser available in the environment without adding a runtime project dependency. Then:

```bash
git diff --check
git diff -- .github/workflows/ci.yml .github/workflows/web-ci.yml .github/workflows/pages.yml
```

Expected: only action pinning, PR-trigger stabilization, and required permission comments/adjustments.

- [ ] **Step 8: Commit**

```bash
git add .github/workflows/ci.yml .github/workflows/web-ci.yml .github/workflows/pages.yml
git commit -m "ci: pin actions and stabilize required checks"
```

---

## Task 6: Add CodeQL for Python and JavaScript/TypeScript

**Files:**

- Create: `.github/workflows/codeql.yml`

**Interfaces:** GitHub CodeQL action; Security tab; future required check contexts.

- [ ] **Step 1: Resolve the current supported CodeQL action major and pin it**

Use GitHub API to resolve the supported `github/codeql-action` release line available at execution time. Use the same immutable SHA for init/analyze where appropriate, annotated with the release major comment.

- [ ] **Step 2: Create a minimal-permission workflow**

Trigger on:

- pull requests;
- pushes to `main`;
- a weekly scheduled scan.

Use a matrix for the actual languages:

```text
python
javascript-typescript
```

Start permissions with:

```yaml
permissions:
  contents: read
  security-events: write
```

Add any additional read permission only if a real CodeQL run demonstrates it is required. Do not grant broad repository write permissions.

- [ ] **Step 3: Keep analysis separate from product execution semantics**

The workflow scans source; it must not call external AI providers, download full benchmark corpora, or execute opt-in model evaluation paths.

- [ ] **Step 4: Re-run the immutable action-ref verifier**

Expected: PASS including CodeQL.

- [ ] **Step 5: Parse YAML and inspect permissions**

```bash
grep -n "permissions:\|security-events:\|contents:" .github/workflows/codeql.yml
git diff --check
```

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/codeql.yml
git commit -m "ci: add CodeQL analysis"
```

---

## Task 7: Add pull-request Dependency Review with high/critical blocking

**Files:**

- Create: `.github/workflows/dependency-review.yml`

**Interfaces:** `actions/dependency-review-action`; pull-request dependency diff; future required check context.

- [ ] **Step 1: Resolve and pin the current supported Dependency Review action major**

Use GitHub API at execution time; record the major version comment next to the full SHA.

- [ ] **Step 2: Create the workflow**

Trigger only on `pull_request`. Use minimum permissions (`contents: read`) and configure:

```yaml
fail-on-severity: high
```

This blocks high and critical vulnerabilities while lower severities remain review signals. Do not add an aggressive license deny-list in Phase 5B.1.

- [ ] **Step 3: Re-run SHA-pin and YAML validation**

Expected: all workflow action refs immutable and YAML valid.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/dependency-review.yml
git commit -m "ci: add dependency review gate"
```

---

## Task 8: Run full local 5B.1-A regression verification before opening the PR

**Files:** No new intended source files unless a failing test exposes a real issue.

**Interfaces:** Python core, CLI, public evidence generator, Web/Storybook/Pages build and browser tests.

- [ ] **Step 1: Python baseline**

From repository root:

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
ruff format --check .
mypy src
```

Expected: all PASS.

- [ ] **Step 2: Exercise deterministic included-fixture CLI paths**

```bash
python -m evalops dataset validate datasets/fixtures/thai-rag-sample.jsonl --document-catalog datasets/fixtures/document-catalog.txt
python -m evalops retrieval evaluate --ground-truth datasets/fixtures/retrieval-ground-truth.jsonl --predictions datasets/fixtures/retrieval-predictions.jsonl --k 5
python -m evalops benchmark miracl --language th --split dev --retriever bm25 --k 5 --mini
```

Expected: commands succeed using local/synthetic included data only.

- [ ] **Step 3: Verify public evidence regeneration is deterministic**

Run the existing public demo generator:

```bash
python scripts/generate_public_demo_evidence.py
git diff --exit-code -- apps/web/public/evidence
```

Expected: no generated evidence drift.

- [ ] **Step 4: Web/Storybook baseline**

```bash
cd apps/web
npm ci
npm run lint
npm run typecheck
npm test
npm run storybook:build
npm run storybook:build:public
node scripts/verify-public-storybook.mjs
npx playwright install --with-deps chromium
npm run storybook:test
npm run build
npm run test:e2e
npm run build:pages
npm run test:e2e:pages
cd ../..
```

Expected: all PASS; public Storybook remains allowlisted and Pages mode remains functional.

- [ ] **Step 5: Final source hygiene checks**

```bash
git diff --check
git status --short
```

Re-run the immutable workflow action-ref verifier. Scan changed files for obvious secrets/private paths. Expected: only intended governance/security/workflow changes plus no generated drift.

- [ ] **Step 6: Commit any validation-only corrections separately**

If a real defect is found, fix only within approved 5B.1 scope, rerun the failing check, then rerun the full applicable baseline before moving on.

---

## Task 9: Open and prove PR 5B.1-A before any repository enforcement

**Files:** PR metadata only.

**Interfaces:** GitHub Actions check runs and Security results.

- [ ] **Step 1: Push and open the PR**

Suggested title:

```text
chore: harden repository governance and supply chain
```

The PR body must reference the Phase 5B.1 issue and approved spec, summarize governance/security boundaries, and state explicitly:

```text
Repository ruleset enforcement is NOT part of this PR and will occur only after these checks are proven.
```

- [ ] **Step 2: Wait for all check runs on the final head**

Inspect exact contexts:

```bash
HEAD_SHA=$(git rev-parse HEAD)
gh api repos/Praciller/evalops-lab/commits/$HEAD_SHA/check-runs \
  --jq '.check_runs[] | [.name,.status,.conclusion] | @tsv'
```

Expected categories must include successful:

- EvalOps `quality` check;
- Web `web` check, including on this governance-heavy PR because PR path filtering was removed;
- CodeQL analysis for Python;
- CodeQL analysis for JavaScript/TypeScript;
- Dependency Review.

Use the **exact names returned here** later for the ruleset.

- [ ] **Step 3: Triage security failures instead of suppressing them**

If CodeQL or Dependency Review reports a relevant critical/high issue, classify and fix it before merge. Do not weaken the gate merely to obtain green CI.

- [ ] **Step 4: Review the complete PR diff**

Verify there are no evaluation-result, public-evidence, runtime feature, or README recruiter-claim changes in 5B.1-A.

- [ ] **Step 5: Merge only after final-head proof**

Use squash merge. Record:

- PR number;
- final head SHA;
- squash merge SHA;
- successful check run IDs/context names.

Do not enable new rules before this merge is complete.

---

## Task 10: Enforce 5B.1-B repository settings using the proven checks

**Files:** No version-controlled source changes unless a verification record is later required.

**Interfaces:** owner-authenticated GitHub Repository API/rulesets.

- [ ] **Step 1: Refresh canonical `main` and re-read current effective state**

```bash
git fetch origin --prune
git rev-parse origin/main
gh repo view Praciller/evalops-lab --json nameWithOwner,hasIssuesEnabled,hasProjectsEnabled,hasWikiEnabled,deleteBranchOnMerge,mergeCommitAllowed,rebaseMergeAllowed,squashMergeAllowed
gh api repos/Praciller/evalops-lab/rulesets
```

Record the delta before mutating anything.

- [ ] **Step 2: Confirm whether GitHub Projects is actually unused**

Inspect repository-linked Projects through available owner tooling/UI/API. If an active project exists or usage cannot be determined, leave Projects enabled and report the limitation. Do not disable it from assumption.

- [ ] **Step 3: Apply repository feature and merge settings**

Using owner-authenticated API/CLI, set the approved values:

```text
Wiki                OFF
Discussions          OFF (preserve)
Projects             OFF only if confirmed unused
Squash merge         ON
Merge commits        OFF
Rebase merge         OFF
Delete head branch   ON
```

Do not alter Pages or Issues away from ON.

- [ ] **Step 4: Enable Private Vulnerability Reporting only if supported and verifiable**

Use the supported owner-authenticated GitHub security API/UI. If unsupported by the available API/account surface, leave it unchanged and record `UNVERIFIED`/limitation. Do not invent a private reporting email/channel.

- [ ] **Step 5: Create one active repository ruleset for the default branch**

Use the exact successful check contexts from Task 9. Target the default branch (`~DEFAULT_BRANCH` or the API's equivalent) and configure:

```text
Pull request required                 YES
Required approving reviews            0
Code-owner review required             NO
Last-push approval required            NO
Review-thread resolution               YES
Allowed merge method                   squash only
Required successful status checks      exact proven contexts
Strict/up-to-date requirement           NO
Deletion                               blocked
Non-fast-forward / force push          blocked
Signed commits                          NOT required
```

Do not add a routine bypass actor. Preserve the minimum owner/admin recovery route provided by GitHub platform administration.

- [ ] **Step 6: Read back the effective repository settings and ruleset**

```bash
gh repo view Praciller/evalops-lab --json hasIssuesEnabled,hasProjectsEnabled,hasWikiEnabled,deleteBranchOnMerge,mergeCommitAllowed,rebaseMergeAllowed,squashMergeAllowed
gh api repos/Praciller/evalops-lab/rulesets
gh api repos/Praciller/evalops-lab/rulesets/<RULESET_ID>
```

Expected: settings/rules reflect the approved model. Do not claim protection from the request payload alone.

- [ ] **Step 7: Verify MIT license recognition**

```bash
gh api repos/Praciller/evalops-lab/license --jq '.license.spdx_id'
```

Expected: `MIT`.

- [ ] **Step 8: Verify issue-form/community surfaces are recognized**

Inspect the repository's new-issue chooser and PR-template behavior through GitHub or supported API/UI. Confirm blank issues are disabled and both forms are available.

- [ ] **Step 9: Do not perform destructive ruleset tests**

Do not force-push `main` and do not attempt branch deletion. Effective ruleset inspection is the acceptance evidence.

---

## Task 11: Prove post-enforcement workflow behavior and classify Phase 5B.1

**Files:** Prefer no source changes. A docs-only verification PR may be used later by 5B.2 closure if durable records are needed.

**Interfaces:** normal owner PR flow under the newly enforced ruleset.

- [ ] **Step 1: Use the next legitimate docs/5B.2 PR as behavioral proof when possible**

Because Web CI is now unconditional on pull requests, a docs-only/recruiter PR should receive all globally required checks. Avoid creating a throwaway PR solely for optics unless no real follow-up PR is available.

- [ ] **Step 2: Confirm the owner can follow the normal PR path without bypass**

For the next real PR, verify:

- required checks appear;
- no external approval is demanded;
- unresolved review threads block completion when applicable;
- squash is the allowed merge method;
- no stale missing-check deadlock occurs.

- [ ] **Step 3: Record final 5B.1 acceptance values**

At minimum record:

```text
5B1_GOVERNANCE=<PASS|COMPLETE_WITH_LIMITATIONS|BLOCKED>
LICENSE=MIT
MAIN_PR_REQUIRED=<YES|NO|UNVERIFIED>
REQUIRED_CHECKS=<exact contexts>
REVIEW_THREAD_RESOLUTION=<YES|NO|UNVERIFIED>
SQUASH_ONLY=<YES|NO|UNVERIFIED>
FORCE_PUSH_BLOCKED=<YES|NO|UNVERIFIED>
DELETE_MAIN_BLOCKED=<YES|NO|UNVERIFIED>
WIKI=OFF
DISCUSSIONS=OFF
PROJECTS=<OFF|ON_WITH_REASON|UNVERIFIED>
PRIVATE_VULNERABILITY_REPORTING=<ON|UNVERIFIED|UNSUPPORTED>
```

- [ ] **Step 4: Stop before Phase 5B.2 if governance is materially incomplete**

Phase 5B.2 may proceed only when 5B.1 is accepted or the owner explicitly accepts a non-material platform limitation. README must not claim controls that are not active.

---

## Final 5B.1 verification checklist

Before claiming Phase 5B.1 acceptance:

- [ ] `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`, CODEOWNERS, issue forms, PR template, Dependabot config exist and are valid.
- [ ] GitHub recognizes MIT.
- [ ] all GitHub Actions `uses:` refs are pinned to immutable full SHAs.
- [ ] Web CI runs on every PR so a global required `web` context cannot be skipped by path filters.
- [ ] CodeQL Python + JavaScript/TypeScript passes on the final implementation head.
- [ ] Dependency Review passes on the final implementation head.
- [ ] Python + CLI + public-evidence + Web/Storybook/Pages regression baseline passes.
- [ ] required-check contexts come from real check runs.
- [ ] repository settings are read back after mutation.
- [ ] `main` requires PRs, conversations resolved, exact required checks, blocks deletion/non-fast-forward, and allows squash only.
- [ ] no external reviewer, code-owner review, signed commit, or strict-up-to-date gate was accidentally introduced.
- [ ] Issues and Pages remain enabled; Wiki is off; Discussions remains off; Projects was changed only with evidence.
- [ ] no secrets/private artifacts/runtime/evaluation semantic changes were introduced.
- [ ] known owner/platform limitations are recorded explicitly.

## Completion handoff

When all boxes above are evidence-backed, report the 5B.1 merge SHA, security/CI run IDs, exact required check contexts, ruleset ID/effective state, repository setting state, and limitations. Do **not** create `v0.1.0`; release remains gated on successful Phase 5B.2 acceptance.