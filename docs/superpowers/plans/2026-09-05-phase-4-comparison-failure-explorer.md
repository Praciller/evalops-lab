# Phase 4 Comparison + Failure Explorer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic same-population synthetic regression comparison and a static comparison-scoped Failure Explorer to the public Evidence Console.

**Architecture:** Extend the existing Public Evidence Contract V1 with typed population compatibility and full comparison parsing, generate a reference retrieval run plus comparison through the existing evaluator/regression engine, then render only validated `MATCHED` comparison bundles. Record transitions are derived at build time/client render from the two approved run artifacts; they are not a second persisted evidence format.

**Tech Stack:** Python 3.11+/Pydantic/pytest/ruff/mypy; Next.js 16 App Router, React 19, TypeScript 5.8, Zod 4, Tailwind CSS 4, Vitest/Testing Library, Playwright + axe; GitHub Pages static export.

**Spec:** `docs/superpowers/specs/2026-09-05-phase-4-comparison-failure-explorer-design.md`

## Global Constraints

- Public schema version remains exactly `public-evidence-v1`.
- New public artifacts are `demo-retrieval-reference-v1` and `demo-retrieval-regression-v1`; preserve `demo-retrieval-fixture-v1` semantics.
- All five regression rules use `HIGHER_IS_BETTER` and `max_degradation = 0.10`.
- Comparison population states are exactly `MATCHED`, `UNVERIFIED`, `INCOMPATIBLE`.
- The Evidence Console may render comparison verdicts/record transitions only for recomputed `MATCHED` population compatibility.
- No runtime API, provider inference, external dataset download, authentication, analytics, raw prompt/response/corpus/reasoning publication, or benchmark/model-superiority claim.
- GitHub Pages base path remains `/evalops-lab`; mobile root horizontal overflow must remain false at 390 px.
- Implement with TDD, fail closed on malformed/mismatched evidence, and commit each task independently.

---
## File map

**Python/public contract**
- Create `src/evalops/export/compatibility.py`: derive population compatibility and validate comparison claims against operand runs.
- Modify `src/evalops/export/models.py`: add `PopulationCompatibility` enum and type the comparison field.
- Modify `src/evalops/export/adapters.py`: explicit run IDs and typed compatibility on comparison adaptation; validate mixed indexes through compatibility policy.
- Modify `src/evalops/export/__init__.py`: export new enum/helper.
- Modify `tests/test_public_evidence_export.py`: contract/claim/population tests.

**Deterministic public demo**
- Create `datasets/fixtures/retrieval-reference-predictions.jsonl`: same five IDs, reference predictions from the approved spec.
- Modify `scripts/generate_public_demo_evidence.py`: generate reference run and real regression report/comparison.
- Modify `tests/test_public_demo_evidence.py`: exact 5-file bundle inventory, 4-regression/1-pass assertions, byte drift guard.
- Regenerate `apps/web/public/evidence/index.json` and four artifact JSON files.

**Frontend contract/data**
- Modify `apps/web/src/lib/evidence/schemas.ts`: full comparison schema/parser and typed compatibility.
- Modify `apps/web/src/lib/evidence/repository.ts`: `ComparisonBundle`, comparison payload/index/run integrity, recomputed population checks.
- Create `apps/web/src/lib/evidence/transitions.ts`: pure record transition derivation.
- Modify `apps/web/tests/evidence-contract.test.ts`, `apps/web/tests/repository.test.ts`; create `apps/web/tests/transitions.test.ts`.

**Frontend presentation**
- Create `apps/web/src/components/comparison-detail.tsx` and `apps/web/src/components/failure-explorer.tsx`.
- Modify `apps/web/src/components/overview.tsx`, `status-badges.tsx`, and `apps/web/src/app/globals.css` only where needed.
- Create routes under `apps/web/src/app/comparisons/[artifactId]/` and `/failures/`.
- Modify `apps/web/tests/components.test.tsx` and `apps/web/tests/e2e/evidence-console.spec.ts` plus visual baselines.
- Modify `.github/workflows/web-ci.yml` and `.github/workflows/pages.yml`. README/DEPLOY documentation is deferred until production deployment is verified, per the approved spec.

---
### Task 1: Harden public comparison compatibility and claim policy

**Files:**
- Create: `src/evalops/export/compatibility.py`
- Modify: `src/evalops/export/models.py:22-352`
- Modify: `src/evalops/export/adapters.py:205-320`
- Modify: `src/evalops/export/__init__.py`
- Modify: `src/evalops/cli.py:198-218,526-557`
- Test: `tests/test_public_evidence_export.py:1-344`
- Test: `tests/test_public_evidence_cli.py:1-241`

**Interfaces:**
- Produces `PopulationCompatibility(StrEnum)` with `MATCHED`, `UNVERIFIED`, `INCOMPATIBLE`.
- Produces `assess_population_compatibility(baseline: PublicRunArtifactV1, candidate: PublicRunArtifactV1) -> PopulationCompatibility`.
- Produces `validate_comparison_operands(comparison, baseline, candidate) -> None` for index publication.
- `adapt_regression_report(source: RegressionReport | Mapping[str, Any], *, artifact_id: str, baseline_artifact_id: str, candidate_artifact_id: str, verification_status: VerificationStatus, data_kind: DataKind, claim_scope: ClaimScope, limitations: Sequence[str] = (), baseline_run_id: str | None = None, candidate_run_id: str | None = None, population_compatibility: PopulationCompatibility = PopulationCompatibility.UNVERIFIED) -> PublicComparisonArtifactV1`.

- [ ] **Step 1: Extend the existing comparison test helper, then write failing enum/model and compatibility tests**

```python
def _comparison_artifact(
    *,
    artifact_id: str = "comparison-v1",
    baseline_artifact_id: str = "baseline-artifact-v1",
    candidate_artifact_id: str = "candidate-artifact-v1",
    verification_status: VerificationStatus = VerificationStatus.VERIFIED,
    data_kind: DataKind = DataKind.SYNTHETIC_FIXTURE,
    claim_scope: ClaimScope = ClaimScope.INTEGRATION_ONLY,
    population_compatibility: PopulationCompatibility = PopulationCompatibility.UNVERIFIED,
):
    return adapt_regression_report(
        {
            "baseline_run_id": "baseline-v1",
            "candidate_run_id": "candidate-v1",
            "passed": True,
            "comparisons": [],
        },
        artifact_id=artifact_id,
        baseline_artifact_id=baseline_artifact_id,
        candidate_artifact_id=candidate_artifact_id,
        verification_status=verification_status,
        data_kind=data_kind,
        claim_scope=claim_scope,
        population_compatibility=population_compatibility,
    )

def test_population_compatibility_is_typed_and_same_population_matches() -> None:
    baseline = _artifact(artifact_id="baseline-run-v1")
    candidate = _artifact(artifact_id="candidate-run-v1")
    assert assess_population_compatibility(baseline, candidate) is PopulationCompatibility.MATCHED


def test_population_mismatch_is_incompatible() -> None:
    baseline = _artifact(artifact_id="baseline-run-v1")
    candidate = _artifact(
        _run_payload() | {"run": _run_payload()["run"] | {"dataset_version": "synthetic-v2"}},
        artifact_id="candidate-run-v1",
    )
    assert assess_population_compatibility(baseline, candidate) is PopulationCompatibility.INCOMPATIBLE
```
```python
def test_index_rejects_matched_comparison_when_population_differs() -> None:
    baseline = _artifact(artifact_id="baseline-run-v1")
    candidate = _artifact(
        _run_payload() | {"run": _run_payload()["run"] | {"top_k": 10}},
        artifact_id="candidate-run-v1",
    )
    comparison = _comparison_artifact(
        baseline_artifact_id=baseline.artifact_id,
        candidate_artifact_id=candidate.artifact_id,
        population_compatibility=PopulationCompatibility.MATCHED,
    )
    with pytest.raises(ValueError, match="population compatibility"):
        build_public_index([baseline, candidate, comparison])


def test_index_rejects_comparison_claim_stronger_than_operand() -> None:
    baseline = _artifact(artifact_id="baseline-run-v1", verification_status=VerificationStatus.PARTIAL)
    candidate = _artifact(artifact_id="candidate-run-v1")
    comparison = _comparison_artifact(
        baseline_artifact_id=baseline.artifact_id,
        candidate_artifact_id=candidate.artifact_id,
        verification_status=VerificationStatus.VERIFIED,
    )
    with pytest.raises(ValueError, match="verification"):
        build_public_index([baseline, candidate, comparison])
```

- [ ] **Step 2: Run focused tests and verify RED**

Run: `python -m pytest tests/test_public_evidence_export.py -q`
Expected: FAIL because `PopulationCompatibility`/compatibility helpers and stricter index validation do not exist yet.
- [ ] **Step 3: Implement typed compatibility and publication validation**

```python
# models.py
class PopulationCompatibility(StrEnum):
    MATCHED = "MATCHED"
    UNVERIFIED = "UNVERIFIED"
    INCOMPATIBLE = "INCOMPATIBLE"

class PublicComparisonArtifactV1(PublicEvidenceArtifactBase):
    artifact_type: Literal["comparison"] = "comparison"
    baseline_artifact_id: str
    candidate_artifact_id: str
    baseline_run_id: str | None = None
    candidate_run_id: str | None = None
    passed: bool
    comparisons: list[PublicComparisonMetric] = Field(default_factory=list)
    population_compatibility: PopulationCompatibility = PopulationCompatibility.UNVERIFIED
```

```python
# compatibility.py
POPULATION_FIELDS = (
    "dataset_name", "dataset_version", "dataset_revision", "evaluation_type",
    "benchmark", "language", "split", "top_k", "evaluator_versions",
)
VERIFICATION_STRENGTH = {
    VerificationStatus.UNVERIFIED: 0,
    VerificationStatus.PARTIAL: 1,
    VerificationStatus.VERIFIED: 2,
}

def assess_population_compatibility(baseline, candidate):
    return PopulationCompatibility.MATCHED if all(
        getattr(baseline.run, field) == getattr(candidate.run, field)
        for field in POPULATION_FIELDS
    ) else PopulationCompatibility.INCOMPATIBLE
```
```python
# compatibility.py
def validate_comparison_operands(comparison, baseline, candidate) -> None:
    if comparison.data_kind is not baseline.data_kind or comparison.data_kind is not candidate.data_kind:
        raise ValueError("comparison data_kind must match both operand runs")
    if comparison.claim_scope is not baseline.claim_scope or comparison.claim_scope is not candidate.claim_scope:
        raise ValueError("comparison claim_scope must match both operand runs")
    max_strength = min(
        VERIFICATION_STRENGTH[baseline.verification_status],
        VERIFICATION_STRENGTH[candidate.verification_status],
    )
    if VERIFICATION_STRENGTH[comparison.verification_status] > max_strength:
        raise ValueError("comparison verification cannot be stronger than operand evidence")
    actual = assess_population_compatibility(baseline, candidate)
    if comparison.population_compatibility is PopulationCompatibility.MATCHED and actual is not PopulationCompatibility.MATCHED:
        raise ValueError("comparison population compatibility does not match operand metadata")
```

Update `build_public_index()` to resolve both referenced runs and call `validate_comparison_operands()` before creating the index. Replace the previous mixed synthetic/official comparison acceptance test with a rejection test because Phase 4 forbids contradictory operand claims.

- [ ] **Step 4: Type the CLI population flag instead of accepting arbitrary free text**

```python
# cli.py parser
evidence_export.add_argument(
    "--population-compatibility",
    choices=[status.value for status in PopulationCompatibility],
    default=PopulationCompatibility.UNVERIFIED.value,
)

# _evidence_export comparison branch
population_compatibility=PopulationCompatibility(args.population_compatibility),
```

Add this CLI test; keep the existing invalid-claim and dangling-index tests unchanged:

```python
def test_evidence_cli_types_population_compatibility(tmp_path, capsys) -> None:
    source_path = tmp_path / "comparison.json"
    output_path = tmp_path / "comparison-public.json"
    source_path.write_text(json.dumps({"passed": True, "comparisons": []}), encoding="utf-8")
    assert main([
        "evidence", "export", "--source", str(source_path), "--source-type", "comparison",
        "--output", str(output_path), "--artifact-id", "comparison-v1",
        "--verification-status", "VERIFIED", "--data-kind", "SYNTHETIC_FIXTURE",
        "--claim-scope", "INTEGRATION_ONLY",
        "--baseline-artifact-id", "baseline-v1",
        "--candidate-artifact-id", "candidate-v1",
        "--population-compatibility", "UNVERIFIED",
    ]) == 0
    capsys.readouterr()
    artifact = json.loads(output_path.read_text(encoding="utf-8"))
    assert artifact["population_compatibility"] == "UNVERIFIED"
```

- [ ] **Step 5: Run focused tests and verify GREEN**

Run: `python -m pytest tests/test_public_evidence_export.py tests/test_public_evidence_cli.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/evalops/export src/evalops/cli.py tests/test_public_evidence_export.py tests/test_public_evidence_cli.py
git commit -m "feat: harden public comparison compatibility"
```
### Task 2: Generate the deterministic reference run and comparison artifact

**Files:**
- Create: `datasets/fixtures/retrieval-reference-predictions.jsonl`
- Modify: `scripts/generate_public_demo_evidence.py:1-172`
- Modify: `tests/test_public_demo_evidence.py:1-46`
- Regenerate: `apps/web/public/evidence/index.json`
- Regenerate/Create: `apps/web/public/evidence/artifacts/*.json`

**Interfaces:**
- `REFERENCE_ARTIFACT_ID = "demo-retrieval-reference-v1"`.
- `COMPARISON_ARTIFACT_ID = "demo-retrieval-regression-v1"`.
- Reuse `compare_metrics(current_metrics, baseline_metrics, rules)` with candidate as current and reference as baseline.
- Comparison uses explicit baseline/candidate run IDs and `assess_population_compatibility(reference, candidate)`.

- [ ] **Step 1: Add the approved reference predictions fixture**

```jsonl
{"query_id":"THQA-001","retrieved_document_ids":["doc-th-001","doc-th-999"]}
{"query_id":"THQA-002","retrieved_document_ids":[]}
{"query_id":"THQA-003","retrieved_document_ids":["doc-th-003","doc-th-002"]}
{"query_id":"THQA-004","retrieved_document_ids":["doc-th-004"]}
{"query_id":"THQA-005","retrieved_document_ids":["doc-th-005","doc-th-006"]}
```

- [ ] **Step 2: Write failing generator tests for exact inventory and regression semantics**

```python
EXPECTED_FILES = [
    Path("artifacts/demo-miracl-th-mini-v1.json"),
    Path("artifacts/demo-retrieval-fixture-v1.json"),
    Path("artifacts/demo-retrieval-reference-v1.json"),
    Path("artifacts/demo-retrieval-regression-v1.json"),
    Path("index.json"),
]
```
```python
def test_generated_comparison_uses_expected_policy(tmp_path: Path) -> None:
    generated = tmp_path / "generated"
    generate(generated)
    comparison = json.loads(
        (generated / "artifacts" / "demo-retrieval-regression-v1.json").read_text()
    )
    statuses = {item["metric_name"]: item["status"] for item in comparison["comparisons"]}
    assert comparison["passed"] is False
    assert comparison["population_compatibility"] == "MATCHED"
    assert sum(status == "REGRESSION" for status in statuses.values()) == 4
    assert sum(status == "PASS" for status in statuses.values()) == 1
    assert statuses["precision_at_5"] == "PASS"
```

- [ ] **Step 3: Run generator tests and verify RED**

Run: `python -m pytest tests/test_public_demo_evidence.py -q`
Expected: FAIL because the reference fixture/comparison artifact and 5-file inventory do not exist yet.

- [ ] **Step 4: Refactor retrieval fixture evaluation just enough to support reference/candidate inputs**

```python
def _retrieval_result(*, predictions_file: str, run_id: str, system_name: str) -> Any:
    ground_truth_rows = _read_jsonl(
        REPOSITORY_ROOT / "datasets" / "fixtures" / "retrieval-ground-truth.jsonl"
    )
    prediction_rows = _read_jsonl(
        REPOSITORY_ROOT / "datasets" / "fixtures" / predictions_file
    )
    ground_truth = {row["query_id"]: row["relevant_document_ids"] for row in ground_truth_rows}
    predictions = {row["query_id"]: row["retrieved_document_ids"] for row in prediction_rows}
    result = run_retrieval_evaluation(
        ground_truth,
        predictions,
        RunConfig(
            run_id=run_id,
            dataset_name="retrieval-fixture",
            dataset_version="synthetic-v1",
            dataset_revision="checked-in-fixture-v1",
            system_name=system_name,
            top_k=5,
            evaluator_versions={"retrieval": "deterministic-metrics-v1"},
            timestamp=FIXED_TIMESTAMP,
        ),
    )
    public_per_query = {
        query_id: {
            "metrics": query_result.metrics,
            "failure_category": query_result.failure_category.value,
            "retrieved_document_ids": list(predictions.get(query_id, [])),
            "relevant_document_ids": list(ground_truth.get(query_id, [])),
        }
        for query_id, query_result in result.details["per_query"].items()
    }
    return result.model_copy(update={"details": {"per_query": public_per_query}})
```
- [ ] **Step 5: Generate the reference run and comparison through the real engine**

```python
rules = [
    MetricRule(
        metric_name=name,
        direction=MetricDirection.HIGHER_IS_BETTER,
        max_degradation=0.10,
    )
    for name in (
        "hit_rate_at_5", "mrr", "ndcg_at_5", "precision_at_5", "recall_at_5"
    )
]
report = compare_metrics(candidate.metrics, reference.metrics, rules)
comparison = adapt_regression_report(
    report,
    artifact_id=COMPARISON_ARTIFACT_ID,
    baseline_artifact_id=reference.artifact_id,
    candidate_artifact_id=candidate.artifact_id,
    baseline_run_id=reference.run.run_id,
    candidate_run_id=candidate.run.run_id,
    population_compatibility=assess_population_compatibility(reference, candidate),
    limitations=[
        "Synthetic same-population regression demonstration; not a benchmark or model-superiority result.",
        "Regression status uses a fixed aggregate max degradation allowance of 0.10 per configured metric.",
    ],
    **common,
)
```

Build the index from `[reference, candidate, miracl, comparison]`, write all four artifact files explicitly, and do not scan `artifacts/`.

- [ ] **Step 6: Regenerate tracked evidence and run deterministic drift tests**

Run: `python scripts/generate_public_demo_evidence.py && python -m pytest tests/test_public_demo_evidence.py -q`
Expected: PASS; generated and committed bytes match, exact file inventory is five JSON files.
- [ ] **Step 7: Verify the existing candidate payload was not semantically rewritten**

Run: `git diff -- apps/web/public/evidence/artifacts/demo-retrieval-fixture-v1.json datasets/fixtures/retrieval-predictions.jsonl`
Expected: no change to `retrieval-predictions.jsonl`; candidate artifact changes only if deterministic serialization metadata necessarily changes, otherwise byte-identical.

- [ ] **Step 8: Commit**

```bash
git add datasets/fixtures/retrieval-reference-predictions.jsonl \
  scripts/generate_public_demo_evidence.py tests/test_public_demo_evidence.py \
  apps/web/public/evidence
git commit -m "feat: publish deterministic regression evidence"
```

---

### Task 3: Add the full comparison schema mirror in TypeScript

**Files:**
- Modify: `apps/web/src/lib/evidence/schemas.ts:1-236`
- Modify: `apps/web/tests/evidence-contract.test.ts:1-135`

**Interfaces:**
- Produces `PopulationCompatibility = z.enum(["MATCHED", "UNVERIFIED", "INCOMPATIBLE"])`.
- Produces `PublicComparisonArtifactSchema`, `PublicComparisonArtifact`, and `parsePublicComparisonArtifact(value)`.
- Extend `PublicClaimArtifact` to include full comparison artifacts.

- [ ] **Step 1: Update the checked-in bundle test, then add failing comparison parser tests**

```ts
it("parses the checked-in explicit index, three runs, and one comparison", () => {
  const index = parsePublicEvidenceIndex(readJson("index.json"));
  expect(index.catalog_status).toBe("EXPLICIT_ALLOWLIST");
  expect(index.artifacts).toHaveLength(4);
  const runSummaries = index.artifacts.filter((artifact) => artifact.artifact_type === "run");
  expect(runSummaries).toHaveLength(3);
  for (const summary of runSummaries) {
    expect(parsePublicRunArtifact(readJson(`artifacts/${summary.artifact_id}.json`)).artifact_id)
      .toBe(summary.artifact_id);
  }
  const comparisonSummary = index.artifacts.find((artifact) => artifact.artifact_type === "comparison");
  expect(comparisonSummary?.artifact_id).toBe("demo-retrieval-regression-v1");
  expect(parsePublicComparisonArtifact(
    readJson("artifacts/demo-retrieval-regression-v1.json"),
  ).artifact_id).toBe("demo-retrieval-regression-v1");
});

it("parses the checked-in full comparison artifact", () => {
  const artifact = parsePublicComparisonArtifact(
    readJson("artifacts/demo-retrieval-regression-v1.json"),
  );
  expect(artifact.population_compatibility).toBe("MATCHED");
  expect(artifact.passed).toBe(false);
  expect(artifact.comparisons.filter((item) => item.status === "REGRESSION")).toHaveLength(4);
});
```
```ts
function readComparisonArtifact() {
  return readJson("artifacts/demo-retrieval-regression-v1.json") as Record<string, unknown> & {
    comparisons: Array<Record<string, unknown>>;
  };
}

const validComparisonMetric = readComparisonArtifact().comparisons[0];

it.each([
  ["unknown compatibility", { population_compatibility: "SAMEISH" }],
  ["unknown direction", { comparisons: [{ ...validComparisonMetric, direction: "sideways" }] }],
  ["unknown status", { comparisons: [{ ...validComparisonMetric, status: "WARN" }] }],
  ["not-run comparison", { verification_status: "NOT_RUN" }],
  ["synthetic benchmark claim", { claim_scope: "BENCHMARK_RESULT" }],
  ["self comparison", { candidate_artifact_id: "demo-retrieval-reference-v1" }],
])("rejects full comparison %s", (_label, overrides) => {
  expect(() => parsePublicComparisonArtifact({ ...readComparisonArtifact(), ...overrides }))
    .toThrow("Evidence unavailable");
});
```

- [ ] **Step 2: Run contract tests and verify RED**

Run: `cd apps/web && npm test -- evidence-contract.test.ts`
Expected: FAIL because the comparison parser/types do not exist.

- [ ] **Step 3: Implement the strict Zod schema**

```ts
const MetricDirection = z.enum(["higher_is_better", "lower_is_better"]);
const RegressionStatus = z.enum(["PASS", "REGRESSION", "MISSING"]);
export const PopulationCompatibility = z.enum(["MATCHED", "UNVERIFIED", "INCOMPATIBLE"]);

const PublicComparisonMetricSchema = z.object({
  metric_name: SafeIdentifier,
  direction: MetricDirection,
  baseline_value: z.number().finite().nullable(),
  candidate_value: z.number().finite().nullable(),
  delta: z.number().finite().nullable(),
  status: RegressionStatus,
  reason: SafeText,
}).strict();
```
```ts
export const PublicComparisonArtifactSchema = z.object({
  schema_version: z.literal("public-evidence-v1"),
  artifact_id: SafeIdentifier,
  artifact_type: z.literal("comparison"),
  ...ClaimFields,
  baseline_artifact_id: SafeIdentifier,
  candidate_artifact_id: SafeIdentifier,
  baseline_run_id: SafeIdentifier.nullable(),
  candidate_run_id: SafeIdentifier.nullable(),
  passed: z.boolean(),
  comparisons: z.array(PublicComparisonMetricSchema),
  population_compatibility: PopulationCompatibility,
}).strict().superRefine((value, ctx) => {
  validateClaimDimensions(value, ctx);
  if (value.baseline_artifact_id === value.candidate_artifact_id) {
    ctx.addIssue({ code: "custom", path: ["candidate_artifact_id"], message: "self comparison" });
  }
});
```

- [ ] **Step 4: Run contract tests and verify GREEN**

Run: `cd apps/web && npm test -- evidence-contract.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/lib/evidence/schemas.ts apps/web/tests/evidence-contract.test.ts
git commit -m "feat: validate public comparison artifacts"
```

---
### Task 4: Build a fail-closed comparison repository bundle

**Files:**
- Modify: `apps/web/src/lib/evidence/repository.ts:1-74`
- Modify: `apps/web/tests/repository.test.ts:1-52`

**Interfaces:**
- Produces `ComparisonBundle = { comparison: PublicComparisonArtifact; baseline: PublicRunArtifact; candidate: PublicRunArtifact }`.
- Produces `getComparisonArtifact(artifactId: string) -> PublicComparisonArtifact`.
- Produces `getComparisonBundle(artifactId: string) -> ComparisonBundle`.
- Produces `getApprovedComparisonBundles(index = getEvidenceIndex()) -> ComparisonBundle[]`.

- [ ] **Step 1: Write failing happy-path and tamper tests**

```ts
it("loads exactly the three run artifacts named by the explicit index", () => {
  const runs = getApprovedRunArtifacts(getEvidenceIndex());
  expect(runs.map((artifact) => artifact.artifact_id)).toEqual([
    "demo-miracl-th-mini-v1",
    "demo-retrieval-fixture-v1",
    "demo-retrieval-reference-v1",
  ]);
});

function withArtifactMutation(
  artifactId: string,
  mutate: (artifact: Record<string, unknown>) => void,
  assertion: () => void,
) {
  const artifactPath = path.join(process.cwd(), "public/evidence/artifacts", `${artifactId}.json`);
  const originalReadFileSync = fs.readFileSync;
  const spy = vi.spyOn(fs, "readFileSync").mockImplementation((file, options) => {
    const content = originalReadFileSync(file, options);
    if (String(file) !== artifactPath || typeof content !== "string") return content;
    const artifact = JSON.parse(content) as Record<string, unknown>;
    mutate(artifact);
    return JSON.stringify(artifact);
  });
  try { assertion(); } finally { spy.mockRestore(); }
}

it("loads the matched comparison bundle", () => {
  const bundle = getComparisonBundle("demo-retrieval-regression-v1");
  expect(bundle.baseline.artifact_id).toBe("demo-retrieval-reference-v1");
  expect(bundle.candidate.artifact_id).toBe("demo-retrieval-fixture-v1");
  expect(bundle.comparison.population_compatibility).toBe("MATCHED");
  expect(bundle.comparison.data_kind).toBe("SYNTHETIC_FIXTURE");
  expect(bundle.comparison.claim_scope).toBe("INTEGRATION_ONLY");
});

it("fails closed for unknown or unsafe comparison IDs", () => {
  expect(() => getComparisonArtifact("missing-comparison")).toThrow("Evidence unavailable");
  expect(() => getComparisonArtifact("../secrets")).toThrow("Evidence unavailable");
});

it.each([
  ["baseline run id", (artifact: any) => { artifact.baseline_run_id = "edited-run"; }],
  ["candidate reference", (artifact: any) => { artifact.candidate_artifact_id = "demo-miracl-th-mini-v1"; }],
  ["comparison delta", (artifact: any) => { artifact.comparisons[0].delta = 0.123; }],
  ["population flag", (artifact: any) => { artifact.population_compatibility = "UNVERIFIED"; }],
])("rejects comparison %s tampering", (_label, mutate) => {
  withArtifactMutation("demo-retrieval-regression-v1", mutate, () => {
    expect(() => getComparisonBundle("demo-retrieval-regression-v1")).toThrow("Evidence unavailable");
  });
});
```
- [ ] **Step 2: Add failing population-mismatch tests**

```ts
it.each([
  ["dataset_name", { dataset_name: "other-fixture" }],
  ["dataset_version", { dataset_version: "synthetic-v2" }],
  ["dataset_revision", { dataset_revision: "other-revision" }],
  ["evaluation_type", { evaluation_type: "other-eval" }],
  ["top_k", { top_k: 10 }],
  ["benchmark", { benchmark: "other" }],
  ["language", { language: "th" }],
  ["split", { split: "test" }],
  ["evaluator_versions", { evaluator_versions: { retrieval: "deterministic-metrics-v2" } }],
])("rejects recomputed population mismatch: %s", (_field, runOverrides) => {
  withArtifactMutation("demo-retrieval-fixture-v1", (artifact) => {
    artifact.run = { ...(artifact.run as Record<string, unknown>), ...runOverrides };
  }, () => {
    expect(() => getComparisonBundle("demo-retrieval-regression-v1")).toThrow("Evidence unavailable");
  });
});
```

- [ ] **Step 3: Run repository tests and verify RED**

Run: `cd apps/web && npm test -- repository.test.ts`
Expected: FAIL because comparison loading/bundle validation does not exist.

- [ ] **Step 4: Implement bundle integrity helpers**

```ts
const POPULATION_FIELDS = [
  "dataset_name", "dataset_version", "dataset_revision", "evaluation_type",
  "benchmark", "language", "split", "top_k",
] as const;

function stringMapMatch(left: Record<string, string>, right: Record<string, string>): boolean {
  const leftKeys = Object.keys(left).sort();
  const rightKeys = Object.keys(right).sort();
  return leftKeys.length === rightKeys.length &&
    leftKeys.every((key, index) => key === rightKeys[index] && left[key] === right[key]);
}

function populationsMatch(baseline: PublicRunArtifact, candidate: PublicRunArtifact): boolean {
  return POPULATION_FIELDS.every((field) => Object.is(baseline.run[field], candidate.run[field])) &&
    stringMapMatch(baseline.run.evaluator_versions, candidate.run.evaluator_versions);
}

const VERIFICATION_STRENGTH = { UNVERIFIED: 0, PARTIAL: 1, VERIFIED: 2 } as const;
```
```ts
function comparisonValuesMatch(
  comparison: PublicComparisonArtifact,
  baseline: PublicRunArtifact,
  candidate: PublicRunArtifact,
): boolean {
  const allRowsValid = comparison.comparisons.every((row) => {
    const baselineValue = baseline.metrics[row.metric_name];
    const candidateValue = candidate.metrics[row.metric_name];
    return baselineValue !== undefined && candidateValue !== undefined &&
      Object.is(row.baseline_value, baselineValue) &&
      Object.is(row.candidate_value, candidateValue) &&
      Object.is(row.delta, candidateValue - baselineValue);
  });
  const expectedPassed = comparison.comparisons.every((row) => row.status === "PASS");
  return allRowsValid && comparison.passed === expectedPassed;
}
```

`getComparisonBundle()` must also require summary/payload IDs and claim dimensions to match, baseline/candidate run IDs to match payloads, data kind and claim scope to equal both operands, comparison verification not stronger than either operand, and `population_compatibility === "MATCHED"` plus recomputed population match. For the Phase 4 public console, additionally require `comparison.data_kind === "SYNTHETIC_FIXTURE"` and `comparison.claim_scope === "INTEGRATION_ONLY"`; future official comparison publication requires a new approved slice. Use the sorted-key equality helper for `evaluator_versions` rather than relying on object insertion order.

- [ ] **Step 5: Run repository tests and verify GREEN**

Run: `cd apps/web && npm test -- repository.test.ts`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/lib/evidence/repository.ts apps/web/tests/repository.test.ts
git commit -m "feat: load validated comparison bundles"
```

---
### Task 5: Derive record transitions without creating a second evidence format

**Files:**
- Create: `apps/web/src/lib/evidence/transitions.ts`
- Create: `apps/web/tests/transitions.test.ts`

**Interfaces:**
- Produces `FailureTransitionKind = "STABLE_PASS" | "INTRODUCED_FAILURE" | "RESOLVED_FAILURE" | "PERSISTENT_CATEGORY" | "CHANGED_FAILURE_CATEGORY"`.
- Produces `FailureTransitionRow` with `recordRef`, baseline/candidate category, changed metric deltas, and both approved evidence records.
- Produces `FailureTransitionResult = { status: "AVAILABLE"; rows: FailureTransitionRow[] } | { status: "UNAVAILABLE"; reason: "RECORD_SET_MISMATCH" }`.
- Produces `buildFailureTransitions(baseline: PublicRunArtifact, candidate: PublicRunArtifact) -> FailureTransitionResult`; it never invents partial joins.

- [ ] **Step 1: Write table-driven transition tests**

```ts
function runPairWithCategories(baselineCategory: string, candidateCategory: string) {
  const baseline = structuredClone(getRunArtifact("demo-retrieval-reference-v1"));
  const candidate = structuredClone(getRunArtifact("demo-retrieval-fixture-v1"));
  baseline.evidence = [{ ...baseline.evidence[0], record_ref: "case-1", failure_category: baselineCategory }];
  candidate.evidence = [{ ...candidate.evidence[0], record_ref: "case-1", failure_category: candidateCategory }];
  return { baseline, candidate };
}

it.each([
  ["PASS", "PASS", "STABLE_PASS"],
  ["PASS", "RETRIEVAL_MISS", "INTRODUCED_FAILURE"],
  ["RETRIEVAL_MISS", "PASS", "RESOLVED_FAILURE"],
  ["RETRIEVAL_MISS", "RETRIEVAL_MISS", "PERSISTENT_CATEGORY"],
  ["RETRIEVAL_MISS", "SHOULD_ABSTAIN", "CHANGED_FAILURE_CATEGORY"],
])("classifies %s -> %s", (baselineCategory, candidateCategory, expected) => {
  const { baseline, candidate } = runPairWithCategories(baselineCategory, candidateCategory);
  const result = buildFailureTransitions(baseline, candidate);
  expect(result.status).toBe("AVAILABLE");
  if (result.status === "AVAILABLE") expect(result.rows[0].kind).toBe(expected);
});

it("fails closed when record populations differ", () => {
  const baseline = getRunArtifact("demo-retrieval-reference-v1");
  const candidate = structuredClone(getRunArtifact("demo-retrieval-fixture-v1"));
  candidate.evidence.pop();
  expect(buildFailureTransitions(baseline, candidate)).toEqual({
    status: "UNAVAILABLE",
    reason: "RECORD_SET_MISMATCH",
  });
});
```
- [ ] **Step 2: Add metric-delta and deterministic-order tests**

```ts
it("keeps stable category separate from changed record metrics", () => {
  const baseline = getRunArtifact("demo-retrieval-reference-v1");
  const candidate = getRunArtifact("demo-retrieval-fixture-v1");
  const result = buildFailureTransitions(baseline, candidate);
  expect(result.status).toBe("AVAILABLE");
  if (result.status !== "AVAILABLE") return;
  const row = result.rows.find((item) => item.recordRef === "THQA-005");
  expect(row?.kind).toBe("STABLE_PASS");
  expect(row?.metricDeltas.find((item) => item.metricName === "recall_at_5")).toEqual({
    metricName: "recall_at_5",
    baselineValue: 1,
    candidateValue: 0.5,
    delta: -0.5,
  });
});

it("sorts rows by record_ref regardless of input evidence order", () => {
  const baseline = structuredClone(getRunArtifact("demo-retrieval-reference-v1"));
  const candidate = structuredClone(getRunArtifact("demo-retrieval-fixture-v1"));
  baseline.evidence.reverse();
  candidate.evidence.reverse();
  const result = buildFailureTransitions(baseline, candidate);
  expect(result.status).toBe("AVAILABLE");
  if (result.status === "AVAILABLE") {
    expect(result.rows.map((row) => row.recordRef))
      .toEqual(["THQA-001", "THQA-002", "THQA-003", "THQA-004", "THQA-005"]);
  }
});
```

- [ ] **Step 3: Run transition tests and verify RED**

Run: `cd apps/web && npm test -- transitions.test.ts`
Expected: FAIL because the transition module does not exist.
- [ ] **Step 4: Implement pure deterministic transition derivation**

```ts
type PublicEvidenceRecord = PublicRunArtifact["evidence"][number];

export type FailureTransitionKind =
  | "STABLE_PASS"
  | "INTRODUCED_FAILURE"
  | "RESOLVED_FAILURE"
  | "PERSISTENT_CATEGORY"
  | "CHANGED_FAILURE_CATEGORY";

export type MetricDelta = {
  metricName: string;
  baselineValue: number | null;
  candidateValue: number | null;
  delta: number | null;
};

export type FailureTransitionRow = {
  recordRef: string;
  kind: FailureTransitionKind;
  baselineCategory: string;
  candidateCategory: string;
  metricDeltas: MetricDelta[];
  baselineRecord: PublicEvidenceRecord;
  candidateRecord: PublicEvidenceRecord;
};

export type FailureTransitionResult =
  | { status: "AVAILABLE"; rows: FailureTransitionRow[] }
  | { status: "UNAVAILABLE"; reason: "RECORD_SET_MISMATCH" };

function classifyTransition(baseline: string, candidate: string): FailureTransitionKind {
  if (baseline === "PASS" && candidate === "PASS") return "STABLE_PASS";
  if (baseline === "PASS") return "INTRODUCED_FAILURE";
  if (candidate === "PASS") return "RESOLVED_FAILURE";
  return baseline === candidate ? "PERSISTENT_CATEGORY" : "CHANGED_FAILURE_CATEGORY";
}

export function buildFailureTransitions(
  baseline: PublicRunArtifact,
  candidate: PublicRunArtifact,
): FailureTransitionResult {
  const baselineById = new Map(baseline.evidence.map((record) => [record.record_ref, record]));
  const candidateById = new Map(candidate.evidence.map((record) => [record.record_ref, record]));
  const baselineIds = [...baselineById.keys()].sort();
  const candidateIds = [...candidateById.keys()].sort();
  if (baselineIds.length !== candidateIds.length || baselineIds.some((id, i) => id !== candidateIds[i])) {
    return { status: "UNAVAILABLE", reason: "RECORD_SET_MISMATCH" };
  }
  return {
    status: "AVAILABLE",
    rows: baselineIds.map((recordRef) => buildTransitionRow(
      recordRef,
      baselineById.get(recordRef)!,
      candidateById.get(recordRef)!,
    )),
  };
}
```

Add these helpers before `buildFailureTransitions()`:

```ts
function metricDeltas(baseline: PublicEvidenceRecord, candidate: PublicEvidenceRecord): MetricDelta[] {
  const names = [...new Set([...Object.keys(baseline.metrics), ...Object.keys(candidate.metrics)])].sort();
  return names.flatMap((metricName) => {
    const baselineValue = baseline.metrics[metricName] ?? null;
    const candidateValue = candidate.metrics[metricName] ?? null;
    if (baselineValue !== null && candidateValue !== null && Object.is(baselineValue, candidateValue)) return [];
    return [{
      metricName,
      baselineValue,
      candidateValue,
      delta: baselineValue === null || candidateValue === null ? null : candidateValue - baselineValue,
    }];
  });
}

function buildTransitionRow(recordRef: string, baseline: PublicEvidenceRecord, candidate: PublicEvidenceRecord): FailureTransitionRow {
  return {
    recordRef,
    kind: classifyTransition(baseline.failure_category, candidate.failure_category),
    baselineCategory: baseline.failure_category,
    candidateCategory: candidate.failure_category,
    metricDeltas: metricDeltas(baseline, candidate),
    baselineRecord: baseline,
    candidateRecord: candidate,
  };
}
```

This preserves metric change evidence without assigning the aggregate `REGRESSION` label at record level.

- [ ] **Step 5: Run transition tests and verify GREEN**

Run: `cd apps/web && npm test -- transitions.test.ts`
Expected: PASS.
- [ ] **Step 6: Commit**

```bash
git add apps/web/src/lib/evidence/transitions.ts apps/web/tests/transitions.test.ts
git commit -m "feat: derive public failure transitions"
```

---

### Task 6: Add comparison detail and overview regression evidence

**Files:**
- Create: `apps/web/src/components/comparison-detail.tsx`
- Create: `apps/web/src/app/comparisons/[artifactId]/page.tsx`
- Modify: `apps/web/src/components/overview.tsx:1-64`
- Modify: `apps/web/src/components/status-badges.tsx:1-37`
- Modify: `apps/web/tests/components.test.tsx:1-33`

**Interfaces:**
- `ComparisonDetail({ bundle }: { bundle: ComparisonBundle })` renders verdict, operand links, matched-population badge, metric comparison table, record-change summary, limitations.
- Overview loads `getApprovedComparisonBundles()` and links only validated comparisons.
- Status badges accept `PublicRunArtifact | PublicComparisonArtifact | PublicArtifactSummary`.

- [ ] **Step 1: Write failing component tests for the comparison story**

```tsx
it("renders updated catalog counts and all synthetic claim badges", () => {
  render(<Overview />);
  expect(screen.getByText("4", { selector: "p" })).toBeInTheDocument();
  expect(screen.getByText("3", { selector: "p" })).toBeInTheDocument();
  expect(screen.getAllByText("SYNTHETIC_FIXTURE", { exact: false })).toHaveLength(4);
});

it("renders comparison verdict and operand links", () => {
  render(<ComparisonDetail bundle={getComparisonBundle("demo-retrieval-regression-v1")} />);
  expect(screen.getByRole("heading", { name: "Regression detected" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /demo-retrieval-reference-v1/ })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /demo-retrieval-fixture-v1/ })).toBeInTheDocument();
  expect(screen.getByText(/Population compatibility: MATCHED/i)).toBeInTheDocument();
  expect(screen.getAllByText(/REGRESSION/)).toHaveLength(4);
});
```
```tsx
it("adds a regression evidence section to the overview", () => {
  render(<Overview />);
  expect(screen.getByRole("heading", { name: "Regression evidence" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /demo-retrieval-regression-v1/ })).toBeInTheDocument();
  expect(screen.getByText(/Synthetic same-population regression demonstration/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run component tests and verify RED**

Run: `cd apps/web && npm test -- components.test.tsx`
Expected: FAIL because comparison components/routes/overview section do not exist.

- [ ] **Step 3: Implement the static comparison route**

```tsx
// app/comparisons/[artifactId]/page.tsx
import { ComparisonDetail } from "@/components/comparison-detail";
import { getEvidenceIndex, getComparisonBundle } from "@/lib/evidence/repository";

export const dynamicParams = false;

export function generateStaticParams() {
  return getEvidenceIndex().artifacts
    .filter((artifact) => artifact.artifact_type === "comparison")
    .map((artifact) => ({ artifactId: artifact.artifact_id }));
}

export default async function ComparisonPage({ params }: { params: Promise<{ artifactId: string }> }) {
  const { artifactId } = await params;
  return <ComparisonDetail bundle={getComparisonBundle(artifactId)} />;
}
```
- [ ] **Step 4: Implement comparison presentation and overview entry**

`ComparisonDetail` must render these exact semantic regions: breadcrumb, `Regression detected`/`Comparison passed` heading from `comparison.passed`, `ArtifactBadges`, baseline and candidate run links, `Population compatibility: MATCHED`, a six-column metric table (`Metric`, `Reference`, `Candidate`, `Delta`, `Direction`, `Result`) where the `Result` cell includes both the artifact status and its exact artifact `reason` text, record-change summary from `buildFailureTransitions()`, an `Explore record changes →` link to `/comparisons/${artifact_id}/failures`, limitations, and the explicit synthetic/non-benchmark interpretation boundary.

Wrap the metric table in the existing `.table-scroll` container so wide evidence stays internally scrollable without root overflow. Use `formatMetricValue()` for values and signed deltas; render `row.baseline_value`, `row.candidate_value`, `row.delta`, `row.direction`, `row.status`, and `row.reason` directly from the comparison artifact. Use text labels `Regression`, `Within allowance`, and `Missing` alongside semantic danger/success/caution colors. Do not recalculate regression status, infer significance, or create record-level regression labels in the UI.

Update `Overview` to compute `comparisons = getApprovedComparisonBundles(index)` and add a `Regression evidence` section after run artifacts. Show reference/candidate IDs, overall result, `MATCHED`, count of `REGRESSION` vs `PASS` metric rows, claim badges, and the exact limitation sentence `Synthetic same-population regression demonstration; not a benchmark or model-superiority result.`

- [ ] **Step 5: Run component/type tests and verify GREEN**

Run: `cd apps/web && npm test -- components.test.tsx && npm run typecheck`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/components/comparison-detail.tsx \
  apps/web/src/components/overview.tsx apps/web/src/components/status-badges.tsx \
  apps/web/src/app/comparisons apps/web/tests/components.test.tsx
git commit -m "feat: add regression comparison view"
```

---
### Task 7: Add the comparison-scoped Failure Explorer

**Files:**
- Create: `apps/web/src/components/failure-explorer.tsx`
- Create: `apps/web/src/app/comparisons/[artifactId]/failures/page.tsx`
- Modify: `apps/web/tests/components.test.tsx`

**Interfaces:**
- `FailureExplorer({ bundle }: { bundle: ComparisonBundle })` is a client component that calls `buildFailureTransitions()` once and filters only those approved derived rows.
- Filter state: transition kind, candidate category, changed-only boolean, record-ID search.
- No global `/failures/` route.

- [ ] **Step 1: Write failing explorer rendering/filter tests**

```tsx
it("renders introduced failure and persistent category without overstating abstention", () => {
  render(<FailureExplorer bundle={getComparisonBundle("demo-retrieval-regression-v1")} />);
  expect(screen.getByText("THQA-004")).toBeInTheDocument();
  expect(screen.getByText("Introduced failure")).toBeInTheDocument();
  expect(screen.getByText("THQA-002")).toBeInTheDocument();
  expect(screen.getByText("Persistent category")).toBeInTheDocument();
  expect(screen.queryByText(/persistent system failure/i)).not.toBeInTheDocument();
});

it("filters to changed records", () => {
  render(<FailureExplorer bundle={getComparisonBundle("demo-retrieval-regression-v1")} />);
  fireEvent.click(screen.getByRole("checkbox", { name: "Changed records only" }));
  expect(screen.queryByText("THQA-001")).not.toBeInTheDocument();
  expect(screen.getByText("THQA-004")).toBeInTheDocument();
  expect(screen.getByText("THQA-005")).toBeInTheDocument();
});

it("renders an unavailable state instead of partially joining record populations", () => {
  const bundle = structuredClone(getComparisonBundle("demo-retrieval-regression-v1"));
  bundle.candidate.evidence.pop();
  render(<FailureExplorer bundle={bundle} />);
  expect(screen.getByRole("heading", { name: "Record-level comparison unavailable" }))
    .toBeInTheDocument();
  expect(screen.queryByRole("checkbox", { name: "Changed records only" })).not.toBeInTheDocument();
});
```
- [ ] **Step 2: Run component tests and verify RED**

Run: `cd apps/web && npm test -- components.test.tsx`
Expected: FAIL because `FailureExplorer` and its route do not exist.

- [ ] **Step 3: Implement the static nested route**

```tsx
// app/comparisons/[artifactId]/failures/page.tsx
import { FailureExplorer } from "@/components/failure-explorer";
import { getEvidenceIndex, getComparisonBundle } from "@/lib/evidence/repository";

export const dynamicParams = false;

export function generateStaticParams() {
  return getEvidenceIndex().artifacts
    .filter((artifact) => artifact.artifact_type === "comparison")
    .map((artifact) => ({ artifactId: artifact.artifact_id }));
}

export default async function FailureExplorerPage({ params }: { params: Promise<{ artifactId: string }> }) {
  const { artifactId } = await params;
  return <FailureExplorer bundle={getComparisonBundle(artifactId)} />;
}
```

- [ ] **Step 4: Implement accessible client-side filters and details**

Call `const transitionResult = buildFailureTransitions(bundle.baseline, bundle.candidate)` before deriving filter options. If `transitionResult.status === "UNAVAILABLE"`, render a surface with heading `Record-level comparison unavailable` and the exact explanation `This comparison does not provide enough compatible public evidence to infer record transitions.`; render no filters and no partial rows.

For `AVAILABLE`, render heading `Record change explorer`, summary text `Reference ? Candidate`, `${transitionResult.rows.length} matched records`, and direct links to both `bundle.baseline.artifact_id` and `bundle.candidate.artifact_id` run pages so reviewers can trace either operand. Controls must be labeled `Transition`, `Candidate category`, `Changed records only`, and `Search record ID`. Keep filtering local with React state; no URL state/API request is needed in Phase 4.

Render the explorer rows in a `.table-scroll` container using the existing `data-table` treatment so mobile overflow remains contained. Each visible row shows record ID, humanized transition, reference category, candidate category, and changed metrics. Use native `<details><summary>Inspect evidence</summary><div>approved evidence fields</div></details>` to reveal only contract-approved retrieved IDs, relevant IDs, per-record metrics, failure category, and failure class. Never render query text, raw corpus, response, prompt, or reasoning.

- [ ] **Step 5: Run component/type tests and verify GREEN**

Run: `cd apps/web && npm test -- components.test.tsx && npm run typecheck`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/components/failure-explorer.tsx \
  apps/web/src/app/comparisons/[artifactId]/failures/page.tsx \
  apps/web/tests/components.test.tsx
git commit -m "feat: add failure explorer"
```

---

### Task 8: Lock production behavior with E2E, visual regression, and CI path coverage

**Files:**
- Modify: `apps/web/tests/e2e/evidence-console.spec.ts:1-57`
- Add/update: `apps/web/tests/e2e/__screenshots__/*`
- Add/update: `docs/screenshots/evidence-console/*`
- Modify: `.github/workflows/web-ci.yml:1-45`
- Modify: `.github/workflows/pages.yml:1-86`

**Interfaces:**
- Production/static acceptance routes: `/`, `/comparisons/demo-retrieval-regression-v1/`, `/comparisons/demo-retrieval-regression-v1/failures/`, `/runs/demo-retrieval-reference-v1/`, `/runs/demo-retrieval-fixture-v1/`.
- Preserve current local-only network boundary and 390 px root-overflow guard.

- [ ] **Step 1: Add failing Playwright journeys for comparison and failure routes**

```ts
test("comparison route is accessible and evidence-safe", async ({ page }) => {
  await page.goto(`${appBasePath}/comparisons/demo-retrieval-regression-v1/`);
  await expect(page.getByRole("heading", { name: "Regression detected" })).toBeVisible();
  await expect(page.getByText("Population compatibility: MATCHED")).toBeVisible();
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});
```
```ts
test("failure explorer filters records and remains mobile-safe", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${appBasePath}/comparisons/demo-retrieval-regression-v1/failures/`);
  await expect(page.getByRole("heading", { name: "Record change explorer" })).toBeVisible();
  await page.getByRole("checkbox", { name: "Changed records only" }).check();
  await expect(page.getByText("THQA-004")).toBeVisible();
  await expect(page.getByText("THQA-005")).toBeVisible();
  const root = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(root.scrollWidth).toBeLessThanOrEqual(root.clientWidth);
  await page.evaluate(() => window.scrollTo(999, 0));
  expect(await page.evaluate(() => window.scrollX)).toBe(0);
  const scrollRegion = page.locator(".table-scroll").first();
  await expect(scrollRegion).toBeVisible();
  expect(await scrollRegion.evaluate((element) => element.scrollWidth > element.clientWidth)).toBe(true);
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});

test("reviewer can trace overview to comparison, failures, and both run operands", async ({ page }) => {
  await page.goto(homePath);
  await page.getByRole("link", { name: /demo-retrieval-regression-v1/ }).first().click();
  await expect(page).toHaveURL(/\/comparisons\/demo-retrieval-regression-v1\/$/);
  await page.getByRole("link", { name: /Explore record changes/ }).click();
  await expect(page).toHaveURL(/\/comparisons\/demo-retrieval-regression-v1\/failures\/$/);
  await page.getByRole("link", { name: /demo-retrieval-reference-v1/ }).first().click();
  await expect(page).toHaveURL(/\/runs\/demo-retrieval-reference-v1\/$/);
  await page.goBack();
  await page.getByRole("link", { name: /demo-retrieval-fixture-v1/ }).first().click();
  await expect(page).toHaveURL(/\/runs\/demo-retrieval-fixture-v1\/$/);
});
```

- [ ] **Step 2: Add visual baselines and local-only network assertions**

Capture and assert `comparison-desktop.png`, `comparison-mobile.png`, `failure-explorer-desktop.png`, and `failure-explorer-mobile.png`. For each new route collect requests and assert every URL starts with `http://127.0.0.1:${localPort}${appBasePath}/` or `data:`. Verify dark-theme toggle on at least the comparison page and keyboard focus can reach the overview/breadcrumb link and explorer controls.

- [ ] **Step 3: Run E2E before updating snapshots and verify RED**

Run: `cd apps/web && npm run build && npm run test:e2e`
Expected: new route tests fail or snapshot assertions fail until pages/components and baselines exist.

- [ ] **Step 4: Update only intentional visual baselines and rerun GREEN**

Run: `cd apps/web && npx playwright test --update-snapshots && npm run test:e2e`
Expected: PASS; inspect the generated desktop/mobile reviewer screenshots before staging them.
- [ ] **Step 5: Expand workflow path coverage and static output checks**

Add these path triggers to `web-ci.yml` and ensure `pages.yml` includes the same relevant sources:

```yaml
- "datasets/fixtures/retrieval-ground-truth.jsonl"
- "datasets/fixtures/retrieval-predictions.jsonl"
- "datasets/fixtures/retrieval-reference-predictions.jsonl"
- "src/evalops/evaluators/retrieval/**"
- "src/evalops/regression/**"
- "src/evalops/runners/retrieval.py"
```

Extend Pages static verification with:

```bash
test -f out/runs/demo-retrieval-reference-v1/index.html
test -f out/comparisons/demo-retrieval-regression-v1/index.html
test -f out/comparisons/demo-retrieval-regression-v1/failures/index.html
```

Keep the existing checks that `out/reports` and `out/datasets` do not exist.

- [ ] **Step 6: Verify Pages-mode locally**

Run: `cd apps/web && npm run build:pages && npm run test:e2e:pages`
Expected: PASS with `/evalops-lab` links/assets/routes and zero unexpected external requests.

- [ ] **Step 7: Commit**

```bash
git add apps/web/tests/e2e docs/screenshots/evidence-console \
  .github/workflows/web-ci.yml .github/workflows/pages.yml
git commit -m "test: cover comparison explorer production paths"
```

---
### Task 9: Run the complete pre-merge release gate and open the implementation PR

**Files:**
- Verify: entire repository and generated static output
- Do not modify: `README.md` or `DEPLOY.md` before production deployment is verified

**Interfaces:**
- The implementation PR contains code, tests, workflows, fixtures, generated public evidence, and intentional visual baselines only.
- Recruiter-facing README wording is a post-merge production-verification follow-up, not part of this PR.

- [ ] **Step 1: Run complete Python quality gates**

Run:

```bash
python -m pytest -q
ruff check .
ruff format --check .
mypy src
```

Expected: all tests PASS, no lint/format/type errors.

- [ ] **Step 2: Run complete frontend quality gates**

Run:

```bash
cd apps/web
npm run lint
npm run typecheck
npm test
npm run build
npm run test:e2e
npm run build:pages
npm run test:e2e:pages
```

Expected: all commands PASS.

- [ ] **Step 3: Re-run deterministic public bundle and security boundary checks**

Run from repository root:

```bash
python scripts/generate_public_demo_evidence.py
git diff --exit-code -- apps/web/public/evidence
rg -n "api_key|authorization|raw_response|raw_corpus|hidden_reasoning|prompt" apps/web/public/evidence
```

Expected: generator produces no diff; `rg` returns no matches in public evidence (exit code 1 is expected for no matches).

- [ ] **Step 4: Run repository hygiene checks**

Run:

```bash
git diff --check
git status --short
git log -8 --oneline
```

Expected: no whitespace errors; only intentional Phase 4 files are modified before the final commit; task commits are present and ordered. `README.md` and `DEPLOY.md` are unchanged.

- [ ] **Step 5: Push and open the implementation PR without merging**

```bash
git push -u origin feat/evidence-comparison-failure-explorer
gh pr create \
  --base main \
  --head feat/evidence-comparison-failure-explorer \
  --title "feat: add evidence-safe comparison and failure explorer" \
  --body "Closes #10\n\nImplements the approved Phase 4 comparison + Failure Explorer spec with deterministic synthetic evidence, strict population compatibility, fail-closed public contract validation, static GitHub Pages routes, accessibility/mobile/network checks, and no runtime inference."
```

Do not merge. Return the PR URL, head SHA, exact test counts/results, visual changes, generated artifact IDs, and any limitations/blockers.

---

## Execution order and review gates

Execute Tasks 1 through 9 in order. After each task, review the diff for scope and evidence correctness before proceeding. Do not parallelize Task 1/2 (contract and generator), Task 3/4 (schema and repository), or Task 6/7 (comparison and explorer UI) because each pair has a direct interface dependency.

The implementation is complete only after the PR is open, all local gates pass, and PR CI is green. Production completion is a separate post-merge verification step: after an independent review and merge, verify GitHub Pages deployment and the live routes defined in the spec before classifying Phase 4 as COMPLETE.


## Post-merge production verification (owner/reviewer step, not Codex implementation)

After independent PR review and merge to `main`, require successful EvalOps CI, Web Evidence Console CI, and GitHub Pages deployment. Verify HTTP 200 and fresh browser behavior for `/evalops-lab/`, the comparison route, Failure Explorer route, reference run, and candidate run; re-check theme, 390 px root overflow, internal table scrolling, axe, external-network boundary, claim labels, metric statuses, and record transitions.

Only after that production verification may a minimal README follow-up update the recruiter snapshot/public-dashboard boundary to mention the live same-population synthetic regression and failure-transition traceability. `DEPLOY.md` remains unchanged unless deployment mechanics actually change.
