# Phase 5B: Repository Governance + Recruiter Evidence Design

Date: 2026-09-06
Repository: `Praciller/evalops-lab`
Status: Conversational design approved; canonical spec awaiting owner review before implementation planning

## 1. Goal

Phase 5B hardens EvalOps Lab as a **recruiter-first AI Evaluation portfolio backed by production-grade solo governance**.

The phase has two primary outcomes:

1. make repository governance, security, ownership, dependency management, and release discipline credible and enforceable without introducing team-scale bureaucracy; and
2. make the repository explain its AI-evaluation value, live evidence, claim boundaries, and engineering depth within roughly 30–90 seconds for a recruiter or technical interviewer.

The phase preserves the existing product principle:

> Evidence over decoration.

Presentation may surface evidence more clearly, but it may never create, reinterpret, amplify, or cosmetically strengthen evaluation truth.

## 2. Approved positioning

Phase 5B is **Recruiter-first** rather than community-first.

The first impression must prioritize **AI Evaluation Engineer capability**, with production software engineering acting as supporting proof.

The preferred reviewer flow is:

```text
AI evaluation problem
        ↓
What EvalOps Lab evaluates
        ↓
Why the evidence is trustworthy
        ↓
Live proof
        ↓
Architecture / engineering depth
```

The primary CTA is the **Live Evidence Console**.

The canonical 90-second review path is:

```text
Overview
  ↓
Regression Comparison
  ↓
Failure Explorer
  ↓
Architecture
  ↓
Tests / CI
```

## 3. Phase decomposition

Phase 5B is split into two implementation tracks and one release closure step:

```text
Phase 5B
│
├─ 5B.1 Repository Governance & Supply-chain Hardening
│  ├─ governance files
│  ├─ ownership and contribution policy
│  ├─ dependency/security automation
│  ├─ main-branch and merge enforcement
│  └─ governance acceptance
│
├─ 5B.2 Recruiter Evidence Presentation
│  ├─ recruiter-first README
│  ├─ live-evidence review path
│  ├─ architecture and evidence matrix
│  ├─ curated production screenshots
│  ├─ explicit trust boundaries
│  └─ GitHub metadata hardening
│
└─ 5B.3 Milestone Finalization
   └─ v0.1.0 only after 5B.1 and 5B.2 acceptance
```

5B.1 must be verified before 5B.2 may make claims about the new governance/security posture.

## 4. Authoritative scope boundaries

Phase 5B may change:

- repository governance files
- GitHub workflow/security configuration
- GitHub repository settings and rulesets
- contribution/security/ownership documentation
- dependency-update policy
- README and recruiter-facing documentation
- repository metadata
- production screenshots used as documentation evidence
- milestone release metadata

Phase 5B must not:

- change metric formulas or regression thresholds
- change evaluator semantics to improve presentation
- alter synthetic results to make the demo look stronger
- represent synthetic integration evidence as an official benchmark
- introduce external AI/provider calls
- introduce API routes, server actions, auth, persistence, analytics, or a database
- expose prompts, corpus content, raw responses, hidden reasoning, secrets, machine-local paths, or private evaluation material
- create unsupported benchmark or model-superiority claims
- perform a broad Evidence Console redesign; that remains outside this phase

The core trust direction remains:

```text
Evaluation implementation
        ↓
Deterministic evaluation artifacts
        ↓
Sanitized public evidence contract
        ↓
Evidence Console
        ↓
README / portfolio claims
```

README and GitHub metadata are downstream presentation surfaces. They are not sources of truth.

## 5. Completion model

Phase 5B uses evidence-based completion classifications:

- **COMPLETE** — governance, recruiter surfaces, repository state, CI, production evidence, and release acceptance all pass.
- **COMPLETE_WITH_LIMITATIONS** — implementation is sound but an owner/platform boundary prevents a required setting from being independently enforced or verified.
- **BLOCKED** — a material security, governance, production, or evidence-integrity requirement fails.
- **NOT_COMPLETE** — presentation exists but required governance/evidence support is incomplete.

A visually improved README does not by itself qualify as completion.

# Part I — Phase 5B.1 Repository Governance & Supply-chain Hardening

## 6. Governance philosophy

Use **solo-production governance**:

- source changes reach `main` through pull requests
- required CI must pass
- conversations must be resolved
- force-push and deletion of `main` are blocked
- no external reviewer is required
- no code-owner approval is required
- normal work uses the same PR path as future contributors

The goal is production discipline without fake team ceremony.

## 7. Target governance surface

The expected repository surface is:

```text
evalops-lab/
├─ LICENSE
├─ CONTRIBUTING.md
├─ SECURITY.md
│
├─ .github/
│  ├─ CODEOWNERS
│  ├─ PULL_REQUEST_TEMPLATE.md
│  ├─ ISSUE_TEMPLATE/
│  │  ├─ bug_report.yml
│  │  ├─ evaluation_proposal.yml
│  │  └─ config.yml
│  ├─ dependabot.yml
│  └─ workflows/
│     ├─ existing EvalOps CI
│     ├─ existing Web Evidence Console CI
│     ├─ existing Pages deployment
│     ├─ codeql.yml
│     └─ dependency-review.yml
```

Do not add a Code of Conduct, CLA, community bot, Discussions workflow, or full community governance layer in Phase 5B.

## 8. License

Use the **MIT License**.

The implementation must add the canonical MIT text and use the actual repository owner attribution.

Acceptance requires GitHub to recognize the repository license as MIT, not merely a file named `LICENSE` existing in the tree.

## 9. CONTRIBUTING.md

`CONTRIBUTING.md` is the technical contributor contract.

It must cover:

```text
Development setup
→ scoped branch
→ deterministic/testable change
→ evidence-boundary preservation
→ required verification
→ pull request
→ CI + discussion resolution
→ squash merge
```

Project-specific rules include:

- evaluation behavior changes require tests
- metric semantics cannot change silently
- public evidence must pass the sanitized export contract
- synthetic evidence cannot be promoted to benchmark evidence
- UI changes require the appropriate frontend/unit/static/Playwright/accessibility evidence
- secrets, raw external datasets, private prompts/responses, and private evaluation material must not be committed
- contributors do not create milestone releases as part of ordinary feature PRs

The README keeps a concise reviewer quickstart; deeper setup and contribution details live here or in linked docs.

## 10. SECURITY.md

The security policy must be short and operational.

Supported scope:

- latest `main`
- latest published milestone release

Sensitive reports must not be opened as public issues.

Preferred reporting path is GitHub Private Vulnerability Reporting if the repository/platform supports it and it can be enabled and verified. If it cannot be configured or verified, report that limitation rather than inventing a contact channel.

Security-sensitive project surfaces include:

- leaked credentials or secrets
- leaked raw/private evidence artifacts or datasets
- public-evidence sanitization bypass
- path traversal or unintended artifact publication
- dependency/workflow supply-chain compromise

## 11. CODEOWNERS

Use **minimal explicit ownership**.

`@Praciller` is the real owner. Rules should map to actual repository boundaries such as:

- repository default
- evaluation core
- public evidence/export boundary
- `apps/web`
- `.github/workflows`
- security/governance files

Exact paths must be derived from the actual tree during implementation.

CODEOWNERS documents critical ownership and future-proofs external contributions, but it must not become a required code-owner approval gate in the solo workflow.

## 12. Issue intake

Use only two structured issue forms:

### 12.1 Bug report

Capture at minimum:

- affected surface
- observed behavior
- expected behavior
- reproduction
- environment/version
- evidence artifact/run ID when relevant
- security-sensitive warning that directs the reporter away from public issue disclosure

### 12.2 Feature / evaluation proposal

Capture at minimum:

- problem
- intended evidence/capability
- proposed scope
- affected evaluator/metric/public contract/UI
- claim implications
- acceptance evidence

Blank issues are disabled through `config.yml`.

## 13. Pull request contract

Use a single PR template with sections equivalent to:

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

Conditional expectations:

- metric/evaluator change → semantic and regression tests
- public contract change → schema/export/frontend validation
- UI change → unit/static/Playwright/axe/screenshots as required
- dependency/workflow change → supply-chain review
- docs-only change → no artificial test requirement, but relevant link/render/security checks still apply

## 14. Dependabot

Use weekly, grouped, low-noise dependency updates for:

```text
Python dependencies     repository root
npm                     apps/web
GitHub Actions          .github/workflows
```

Policy:

- group minor/patch updates where practical
- keep majors separately reviewable
- cap concurrently open update PRs
- avoid daily dependency churn
- preserve the current package-manager architecture

Security updates retain GitHub priority behavior.

## 15. GitHub Actions supply-chain policy

Review all workflows touched by Phase 5B.

Target policy:

- use official/reputable actions
- pin action dependencies to immutable commit SHAs where practical, with readable version comments if useful
- allow Dependabot to maintain GitHub Actions references
- declare minimum required workflow permissions
- avoid unsafe fork/secret/write interactions
- do not add `pull_request_target` without a separately justified design decision
- do not add paid or hosted third-party security SaaS

Typical default permission should be equivalent to:

```yaml
permissions:
  contents: read
```

Additional permissions are granted only where a job requires them, for example `security-events: write` for CodeQL.

## 16. CodeQL

Add CodeQL for the languages actually present and relevant:

```text
Python
JavaScript / TypeScript
```

Triggers:

- relevant pull requests
- push to `main`
- scheduled periodic scan

Acceptance requires successful analysis, no configuration failure, and no unnecessary write permissions.

A real critical/high alert must not be suppressed merely to make the workflow green; it must be triaged and resolved or explicitly block completion.

## 17. Dependency Review

Add PR-level dependency review.

Policy:

```text
critical → block
high     → block
moderate → report
low      → report
```

Do not add an aggressive dependency-license deny-list in this phase without a real repository requirement.

## 18. Main ruleset

Desired `main` behavior:

```text
Require pull request              YES
Required approvals                0
Require conversation resolution   YES
Required status checks            YES
Require branch up to date         NO
Require signed commits            NO
Block force push                  YES
Block deletion                    YES
```

Required checks must use the exact successful GitHub check contexts observed from real runs. Do not guess contexts from workflow filenames or display names.

Expected categories after the new workflows are proven include:

- EvalOps validation
- Web Evidence Console validation
- Dependency Review
- CodeQL

Pages deployment is not a pre-merge required check if it only executes after merge.

New security checks must be proven on a PR before they become required, preventing a ruleset deadlock.

## 19. Merge policy

Repository merge settings target:

```text
Squash merge          ON
Merge commit          OFF
Rebase merge          OFF
Delete head branch    ON
```

The intent is a clean, linear recruiter-facing `main` history without intermediate implementation/debug commits.

## 20. Repository feature settings

Target state:

| Surface | State |
|---|---|
| Issues | ON |
| GitHub Pages | ON |
| Wiki | OFF |
| Discussions | OFF |
| Projects | OFF only if confirmed unused |
| Private vulnerability reporting | ON if supported and verified |
| Squash merge | ON |
| Merge commits | OFF |
| Rebase merge | OFF |

Do not disable Projects without first confirming that no active project board depends on it.

## 21. Governance verification

Governance is verified at three levels:

```text
Static
  YAML/forms/CODEOWNERS/workflows valid

CI
  existing + security workflows pass

GitHub repository state
  license detection
  ruleset/settings
  merge methods
  repository features
```

A setting that cannot be read through one connector is not assumed configured. Use available owner-authenticated tooling where possible; otherwise classify the unverifiable boundary explicitly.

# Part II — Phase 5B.2 Recruiter Evidence Presentation

## 22. README information architecture

The README uses **progressive disclosure**.

The first one to two screens must complete the recruiter story. Deeper technical material remains available lower in the README or in `docs/`.

Canonical order:

```text
Hero / positioning
Live Evidence CTA
Capability signals + trustworthy badges
Primary production screenshot

90-second Review Path

Why EvalOps Lab exists
Evidence Matrix
What this demonstrates

Architecture
Evaluation & regression model
Trust & Limitations

Selected production evidence
Engineering quality

Reviewer-friendly quickstart
Repository structure / deeper docs

Contributing
Security
License
Roadmap
```

Detailed implementation history, exhaustive commands, deployment internals, and phase-specific specs should be linked rather than dominating the README.

## 23. Above-the-fold positioning

The top of the README must answer quickly:

```text
What is EvalOps Lab?
        ↓
What AI-evaluation problem does it solve?
        ↓
What can I inspect live?
        ↓
What capabilities does it demonstrate?
        ↓
Can I trust the claims?
```

Preferred positioning direction:

> A reproducible AI evaluation framework for RAG retrieval, regression decisions, failure analysis, and evidence-backed engineering.

A short secondary sentence may explain that deterministic evaluation artifacts are validated and sanitized before publication in a static, read-only Evidence Console.

The primary CTA is the Live Evidence Console. Secondary CTAs are the 90-second review path and architecture section.

Storybook remains a useful engineering/design-system proof, but it is not a primary recruiter CTA.

## 24. Capability signals and badges

Above the fold may use compact capability signals such as:

```text
AI Evaluation
RAG Regression
Failure Analysis
Deterministic Evidence
Python / TypeScript
CI/CD
```

Use only a small set of live/trustworthy badges. Candidates include:

- EvalOps CI
- Web CI
- Pages deployment
- supported Python version
- MIT License

Do not use ungrounded badges or claims such as `enterprise-grade`, `best-in-class`, or `100% production-ready`.

## 25. 90-second review path

Add a short recruiter section such as **Review EvalOps Lab in 90 seconds**.

The canonical path is:

1. **Overview** — understand the public evidence model and verification boundaries.
2. **Regression Comparison** — inspect deterministic metric-level regression decisions.
3. **Failure Explorer** — inspect changed, persistent, improved, and regressed records.
4. **Architecture** — trace evidence from evaluation to sanitized public artifacts.
5. **Tests & CI** — verify that claims are supported by automated validation.

Each step explains what it proves, not merely which feature it shows.

## 26. Production screenshots

Use only **2–3 curated production screenshots**.

Preferred set:

1. Evidence Console Overview
2. Regression Comparison
3. Failure Explorer or a filtered evidence catalog

Requirements:

- capture from production GitHub Pages after the relevant accepted merge
- preserve visible evidence labels when they are necessary to understand claim scope
- do not use localhost screenshots as production proof
- do not edit metrics/results for presentation
- do not use a Storybook mock as a substitute for live product evidence
- captions describe the evidence being shown, not marketing adjectives

Screenshot provenance should be traceable to route and production commit.

## 27. Evidence Matrix

Add a concise matrix with dimensions equivalent to:

| Capability | Evidence | Data kind | Claim scope | Verification |
|---|---|---|---|---|

The actual rows must be derived from current repository truth.

Examples of legitimate categories include retrieval evaluation, regression detection, failure-transition analysis, and public-evidence isolation.

If an official external benchmark result does not exist, the matrix must not imply that it does.

Labels such as `SYNTHETIC_FIXTURE`, `INTEGRATION_ONLY`, and `VERIFIED` remain explicit where applicable.

## 28. What this demonstrates

Add a short recruiter-facing competency translation section.

Candidate competencies, only when supported by evidence, include:

- AI Evaluation Design
- RAG Retrieval Metrics & Regression
- Failure Taxonomy and Root-cause Investigation
- Evidence / Claim Quality
- Deterministic Python Evaluation Engineering
- Type-safe Public Evidence Interfaces
- CI/CD, Accessibility, and Production Verification

Do not add self-ratings or star-based proficiency scales.

Each competency should link to implementation, evidence, tests, or architecture where practical.

## 29. Architecture presentation

Use one GitHub-native Mermaid diagram showing the conceptual evidence flow:

```text
Dataset / Ground Truth
        ↓
Evaluation Runner
        ↓
Retrieval / Groundedness Evaluators
        ↓
Deterministic Run Artifacts
        ↓
Comparison + Regression Policy
        ↓
Failure Analysis
        ↓
Sanitized Public Evidence Contract
        ↓
Static Evidence Console
```

CI/testing are cross-cutting validation boundaries rather than ordinary data-flow nodes.

The diagram must remain conceptual and traceable to actual architecture; it should not mirror every file/module.

## 30. Engineering quality proof

Include a compact evidence-backed engineering section covering only capabilities that are active and verified, such as:

- deterministic evaluation
- typed Pydantic contracts
- public artifact sanitization
- Python + TypeScript validation
- unit/integration/Playwright tests
- accessibility checks
- static GitHub Pages deployment
- CodeQL + dependency review, but only after 5B.1 acceptance
- PR-governed `main`, but only after repository enforcement is verified

Do not claim governance controls before they are active.

## 31. Trust & Limitations

Trust boundaries must be visible in the README, not hidden only in detailed docs.

The README must distinguish at least:

```text
SYNTHETIC_FIXTURE
≠
OFFICIAL_BENCHMARK
```

and:

```text
INTEGRATION_ONLY
≠
real-world model superiority
```

Current synthetic reference/candidate comparisons prove the integration/regression/failure-analysis pipeline. They do not prove production model superiority unless a future approved benchmark artifact explicitly supports that claim.

This limitation is part of the product's evaluation discipline, not a disclaimer to hide.

## 32. Reviewer-friendly quickstart

The README includes a short clean-checkout route for technical reviewers, for example:

```text
clone
→ install dev dependencies
→ run evaluation/tests
→ build or inspect Evidence Console
```

Exact commands must be verified against the current repository before publication.

Playwright, Storybook, artifact generation, deployment, troubleshooting, and contributor detail should remain in `CONTRIBUTING.md` or linked docs where appropriate.

## 33. GitHub repository metadata

Synchronize GitHub About metadata with recruiter positioning.

Description should clearly include the concepts of:

- AI evaluation
- RAG regression
- failure analysis
- reproducible evidence

Homepage remains:

`https://praciller.github.io/evalops-lab/`

Topics should be recruiter/search relevant without keyword stuffing. Candidate topics include:

- `ai-evaluation`
- `llm-evaluation`
- `rag-evaluation`
- `ai-engineering`
- `mlops`
- `testing`
- `python`

The final set should remain concise and truthful.

## 34. GitHub rendering acceptance

README acceptance must inspect real GitHub rendering rather than only a local Markdown preview.

Check:

- Mermaid rendering
- table readability
- screenshot sizing
- GitHub light and dark themes
- relative links
- heading anchors
- mobile-width readability

Avoid fragile HTML layout tricks that depend on undocumented GitHub rendering behavior.

A human reviewer should be able to identify within about 90 seconds:

1. what problem the project solves
2. the main AI-evaluation capability
3. where the live evidence exists
4. the current evidence limitations
5. how the implementation demonstrates production discipline

# Part III — Verification and Release

## 35. Verification layers

Use five verification layers:

```text
Static validation
      ↓
Local repository verification
      ↓
Pull-request CI verification
      ↓
GitHub repository-state verification
      ↓
Production / recruiter-surface verification
```

No single layer substitutes for the others.

## 36. Static validation

Before opening/merging implementation PRs, validate:

Governance:

- MIT text is canonical
- CODEOWNERS paths are real
- Issue Forms YAML is valid
- PR template links/checklists are valid
- Dependabot syntax and ecosystem directories are valid
- workflow YAML parses
- contribution/security links resolve

Recruiter presentation:

- internal README anchors resolve
- screenshot files exist
- production URLs are valid
- Mermaid syntax is valid
- no local Windows paths or placeholders remain
- no unsupported benchmark/superiority claim is introduced

Security:

- no secret/token/key
- no raw/private artifact
- no build/cache output committed accidentally

## 37. Local regression verification

Phase 5B must preserve existing product behavior.

The final implementation plan should require the appropriate subset of the established suite, with full baseline verification before final completion, including:

Python:

- `pytest`
- Ruff check
- Ruff format check
- mypy

Evidence:

- deterministic artifact regeneration
- generated-output drift check
- public evidence boundary tests

Web:

- lint
- typecheck
- unit tests
- static build
- public Storybook build
- Storybook tests

Browser:

- Playwright
- accessibility / axe
- representative mobile overflow
- fail-closed public-contract behavior

Docs/governance-only deltas do not require artificial screenshot regeneration if no public visual surface changed, but completion still requires a clean product baseline.

## 38. PR CI acceptance

The 5B.1 governance foundation PR must prove the existing product checks and the new security checks before new checks are enforced by the ruleset.

Expected categories:

```text
Existing EvalOps CI          PASS
Existing Web CI              PASS
CodeQL                       PASS
Dependency Review            PASS
Governance validation        PASS if a dedicated validator is introduced
```

Order is mandatory:

```text
add workflow
→ prove workflow
→ identify exact check context
→ configure main ruleset
```

## 39. GitHub repository-state verification

After enforcement changes, inspect effective state:

```text
main
├─ PR required
├─ approvals = 0
├─ conversation resolution required
├─ required successful checks
├─ force push blocked
└─ deletion blocked
```

Also inspect:

```text
Squash       ON
Merge commit OFF
Rebase       OFF
Delete branch ON
```

Do not test protection by actually force-pushing or deleting `main`.

Repository feature state, license recognition, and private vulnerability reporting should also be checked directly when platform access permits.

## 40. Production evidence verification

After 5B.2 merges, verify the live public deployment again:

```text
Overview
Runs
Comparisons
Regression Comparison
Failure Explorer
Storybook
```

At minimum verify:

- successful page responses
- expected headings/content
- correct evidence labels
- README deep links resolve
- no unexpected external requests
- representative axe checks pass
- representative 390px root overflow remains absent
- Storybook public allowlist still excludes internal stories

## 41. Claim audit

Before final acceptance, classify meaningful README claims as:

```text
A. Directly evidenced
B. Implementation-derived
C. Bounded inference
D. Unsupported
```

Policy:

- A/B may remain
- C requires constrained wording
- D must be removed

Example allowed direction:

> Deterministic regression decisions are generated from versioned comparison artifacts.

Example disallowed direction when current evidence is synthetic/integration-only:

> Production-proven RAG performance improvements.

## 42. Documentation provenance

After production acceptance, record the final Phase 5B verification in durable docs rather than overloading the README.

Record as available:

- 5B.1 merge SHA
- 5B.2 merge SHA
- relevant CI run IDs
- production verification date
- live routes
- governance/security limitations

README is the recruiter surface; verification docs are the operational record.

## 43. v0.1.0 release gate

Create `v0.1.0` only when all of the following are true:

```text
5B.1 governance accepted
5B.2 recruiter presentation accepted
main CI green
security workflows green
production deployment verified
README claim audit passed
GitHub metadata synchronized
no unresolved critical/high security issue
canonical main clean
```

The tag must point to the accepted canonical `main` SHA.

`v0.1.0` means:

> first recruiter-ready, evidence-governed public milestone

It does not promise a stable 1.0 public API.

No Python/npm package publication is required. The GitHub Release is a milestone marker, not a packaging project.

## 44. Release notes

Keep release notes concise and evidence-bounded. They may summarize:

- reproducible evaluation core
- run/comparison/failure evidence
- public Evidence Console
- Evidence Design System / Storybook
- repository governance/security
- explicit evidence limitations
- live demo links

Release notes must not make stronger claims than the README or public evidence supports.

# Part IV — Execution Boundaries and Rollback

## 45. PR decomposition

Use separate PR boundaries to reduce risk.

### 45.1 PR 5B.1-A — Governance foundations

Contains version-controlled governance/security work:

- LICENSE
- CONTRIBUTING.md
- SECURITY.md
- CODEOWNERS
- Issue Forms
- PR template
- Dependabot
- CodeQL
- Dependency Review
- required workflow permission/pinning hardening

Do not enforce new required checks until this PR has proven them successfully.

### 45.2 PR 5B.1-B — Repository enforcement

After 5B.1-A is merged and checks are proven, configure and verify:

- `main` ruleset
- merge methods
- Wiki / Discussions / Projects state
- private vulnerability reporting if supported
- governance-related repository settings

This step may be a settings-only change rather than a source PR, but it remains a separate acceptance boundary.

### 45.3 PR 5B.2-A — Recruiter presentation

Contains:

- README information architecture
- CTA hierarchy
- 90-second review path
- Mermaid architecture
- Evidence Matrix
- What this demonstrates
- Trust & Limitations
- reviewer quickstart
- curated screenshot references/assets as appropriate
- docs links
- version-controlled metadata preparation

It must not change evaluation semantics or runtime behavior solely to improve presentation.

### 45.4 PR 5B.2-B — Verification record, only if needed

If production screenshots or verification records must be committed only after the final deployment, use a docs/evidence-only closure PR. Do not mix new source behavior into this verification PR.

## 46. Issue structure

Use one Phase 5B epic and two implementation issues:

```text
Phase 5B epic
├─ 5B.1 Repository governance & supply-chain hardening
└─ 5B.2 Recruiter evidence presentation
```

Do not create issue-per-file ceremony.

Implementation issues remain open until post-merge acceptance passes.

## 47. Branch/worktree policy

The normal local checkout has historically contained local-only divergence, so Phase 5B must not reset or reuse it blindly.

Each implementation slice should start from a clean isolated worktree/branch based on canonical `origin/main` and verify:

```text
git status --short
git rev-parse HEAD
git rev-parse origin/main
```

Preserve unrelated local commits/dirty work rather than discarding them.

## 48. Codex execution contract

After this design is approved and an implementation plan is written, each Codex slice receives a full scoped prompt containing:

- exact canonical base SHA/ref
- design spec and implementation plan paths
- allowed files/surfaces
- explicit non-goals
- tests and acceptance checks
- security/public-evidence constraints
- claim-boundary constraints
- stop conditions
- final report schema

Codex must not broaden scope, alter metrics, invent benchmark claims, enable paid/external services, or change approved governance policy without owner approval.

No subagent/delegation workflow is introduced unless the owner explicitly requests it.

## 49. Settings mutation policy

For settings outside version control:

```text
read current state
→ record intended delta
→ mutate only approved settings
→ read effective state again
→ report result
```

Do not use destructive behavioral tests such as force-pushing or deleting `main`.

## 50. Rollback strategy

Security/governance configuration must remain recoverable.

If a new security workflow is misconfigured, fix it in PR rather than disabling security to obtain a green merge.

If a ruleset accidentally blocks the normal owner PR path:

- use the minimum owner/admin recovery route
- restore the last verified ruleset
- fix configuration
- re-apply only after proof

If README/Mermaid rendering fails, fix presentation rather than weakening claim labels or limitations.

If a new production screenshot is stale or misleading, revert the asset/reference; do not alter runtime evidence to make the screenshot look better.

## 51. Stop conditions

Stop and do not merge when any of the following is true:

- relevant critical/high security issue remains unresolved
- CodeQL or Dependency Review configuration is failing
- the ruleset risks locking the owner out of the normal PR workflow
- README claims exceed evidence scope
- synthetic evidence is presented as benchmark evidence
- a public screenshot leaks raw/private material
- production evidence routes are broken
- canonical branch/base is ambiguous
- unexpected dirty/local state risks overwriting unrelated work

## 52. Final verification artifact

The final closure record should use actual verified values, for example:

```text
PHASE_5B_CLASSIFICATION=<COMPLETE|COMPLETE_WITH_LIMITATIONS|BLOCKED|NOT_COMPLETE>

5B1_GOVERNANCE=<PASS|...>
5B2_RECRUITER_PRESENTATION=<PASS|...>

CANONICAL_MAIN=<sha>
RELEASE=<v0.1.0 or none>
RELEASE_SHA=<sha or none>

EVALOPS_CI=<run>
WEB_CI=<run>
CODEQL=<run>
DEPENDENCY_REVIEW=<run>
PAGES=<run>

LICENSE=<MIT|...>
MAIN_PR_REQUIRED=<YES|NO|UNVERIFIED>
SQUASH_ONLY=<YES|NO|UNVERIFIED>
FORCE_PUSH_BLOCKED=<YES|NO|UNVERIFIED>
DELETE_MAIN_BLOCKED=<YES|NO|UNVERIFIED>

README_CLAIM_AUDIT=<PASS|...>
PRODUCTION_EVIDENCE=<PASS|...>
TRUST_BOUNDARIES_PRESERVED=<YES|NO>
KNOWN_LIMITATIONS=<explicit list or none>
```

No field may be filled optimistically before verification.

## 53. Final design decision

Phase 5B adopts **Portfolio-grade Governance + Recruiter Evidence Funnel**.

The canonical product/repository direction is:

> A recruiter-first AI Evaluation portfolio backed by enforceable solo-production governance, bounded evidence claims, reproducible verification, and a milestone release only after acceptance.

The final ordering remains:

```text
evaluation truth
→ evidence
→ presentation
```

Never:

```text
presentation
→ claim
→ retrofit evidence
```

Implementation planning may begin only after the owner reviews and approves this canonical written specification.
