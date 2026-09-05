import { describe, expect, it } from "vitest";

import { getRunArtifact } from "@/lib/evidence/repository";
import { buildFailureTransitions, hasRecordChange } from "@/lib/evidence/transitions";

function runPairWithCategories(baselineCategory: string, candidateCategory: string) {
  const baseline = structuredClone(getRunArtifact("demo-retrieval-reference-v1"));
  const candidate = structuredClone(getRunArtifact("demo-retrieval-fixture-v1"));
  baseline.evidence = [{
    ...baseline.evidence[0],
    record_ref: "case-1",
    failure_category: baselineCategory,
  }];
  candidate.evidence = [{
    ...candidate.evidence[0],
    record_ref: "case-1",
    failure_category: candidateCategory,
  }];
  return { baseline, candidate };
}

describe("public failure transitions", () => {
  it.each([
    ["PASS", "PASS", "STABLE_PASS"],
    ["PASS", "RETRIEVAL_MISS", "INTRODUCED_FAILURE"],
    ["RETRIEVAL_MISS", "PASS", "RESOLVED_FAILURE"],
    ["RETRIEVAL_MISS", "RETRIEVAL_MISS", "PERSISTENT_CATEGORY"],
    ["RETRIEVAL_MISS", "SHOULD_ABSTAIN", "CHANGED_FAILURE_CATEGORY"],
  ])("classifies %s -> %s as %s", (baselineCategory, candidateCategory, expected) => {
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

  it.each([
    ["PERSISTENT_CATEGORY", "RETRIEVAL_MISS", "RETRIEVAL_MISS", {}, false],
    ["PERSISTENT_CATEGORY with metric delta", "RETRIEVAL_MISS", "RETRIEVAL_MISS", { score: 0.5 }, true],
    ["STABLE_PASS", "PASS", "PASS", {}, false],
    ["STABLE_PASS with metric delta", "PASS", "PASS", { score: 0.5 }, true],
    ["INTRODUCED_FAILURE", "PASS", "RETRIEVAL_MISS", {}, true],
    ["RESOLVED_FAILURE", "RETRIEVAL_MISS", "PASS", {}, true],
    ["CHANGED_FAILURE_CATEGORY", "RETRIEVAL_MISS", "SHOULD_ABSTAIN", {}, true],
  ])("marks %s as changed=%s", (_label, baselineCategory, candidateCategory, candidateMetrics, expected) => {
    const baseline = structuredClone(getRunArtifact("demo-retrieval-reference-v1"));
    const candidate = structuredClone(getRunArtifact("demo-retrieval-fixture-v1"));
    baseline.evidence = [{
      ...baseline.evidence[0],
      record_ref: "case-1",
      failure_category: baselineCategory,
      metrics: { score: 1 },
    }];
    candidate.evidence = [{
      ...candidate.evidence[0],
      record_ref: "case-1",
      failure_category: candidateCategory,
      metrics: Object.keys(candidateMetrics).length ? candidateMetrics : { score: 1 },
    }];
    const result = buildFailureTransitions(baseline, candidate);
    expect(result.status).toBe("AVAILABLE");
    if (result.status === "AVAILABLE") expect(hasRecordChange(result.rows[0])).toBe(expected);
  });

  it("sorts rows by record_ref regardless of input evidence order", () => {
    const baseline = structuredClone(getRunArtifact("demo-retrieval-reference-v1"));
    const candidate = structuredClone(getRunArtifact("demo-retrieval-fixture-v1"));
    baseline.evidence.reverse();
    candidate.evidence.reverse();
    const result = buildFailureTransitions(baseline, candidate);
    expect(result.status).toBe("AVAILABLE");
    if (result.status === "AVAILABLE") {
      expect(result.rows.map((row) => row.recordRef)).toEqual([
        "THQA-001",
        "THQA-002",
        "THQA-003",
        "THQA-004",
        "THQA-005",
      ]);
    }
  });
});
