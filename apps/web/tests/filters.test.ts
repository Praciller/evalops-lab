import { describe, expect, it } from "vitest";

import {
  matchesComparisonFilters,
  matchesRunFilters,
  parseComparisonFilters,
  parseRunFilters,
  withFilter,
} from "@/lib/evidence/filters";
import {
  deriveComparisonResult,
  getComparisonCatalogItems,
  getRunCatalogItems,
} from "@/lib/evidence/catalog";
import { getComparisonBundle } from "@/lib/evidence/repository";

describe("evidence catalog filters", () => {
  it("parses only supported single-select run filters", () => {
    expect(parseRunFilters(new URLSearchParams("verification=VERIFIED&data=SYNTHETIC_FIXTURE"))).toEqual({
      verification: "VERIFIED",
      data: "SYNTHETIC_FIXTURE",
    });
    expect(parseRunFilters(new URLSearchParams("verification=SUPER_VERIFIED"))).toEqual({});
    expect(parseRunFilters(new URLSearchParams("verification=VERIFIED&verification=PARTIAL"))).toEqual({});
  });

  it("parses comparison population and result filters safely", () => {
    expect(parseComparisonFilters(new URLSearchParams("population=MATCHED&result=REGRESSION"))).toEqual({
      population: "MATCHED",
      result: "REGRESSION",
    });
    expect(parseComparisonFilters(new URLSearchParams("population=UNKNOWN&result=MISSING"))).toEqual({});
  });

  it("matches each filter dimension with AND semantics", () => {
    const run = getRunCatalogItems().find((item) => item.artifact_id === "demo-retrieval-fixture-v1");
    const comparison = getComparisonCatalogItems()[0];

    expect(run).toBeDefined();
    expect(comparison).toBeDefined();
    expect(matchesRunFilters(run!, { verification: "VERIFIED", data: "SYNTHETIC_FIXTURE" })).toBe(true);
    expect(matchesRunFilters(run!, { verification: "VERIFIED", data: "CURATED_DATASET" })).toBe(false);
    expect(matchesComparisonFilters(comparison!, { population: "MATCHED", result: "REGRESSION" })).toBe(true);
    expect(matchesComparisonFilters(comparison!, { population: "MATCHED", result: "PASS" })).toBe(false);
  });

  it("serializes one filter change without losing unrelated query state", () => {
    const params = new URLSearchParams("page=2&verification=PARTIAL&scope=INTEGRATION_ONLY");

    expect(withFilter(params, "verification", "VERIFIED")).toBe(
      "page=2&scope=INTEGRATION_ONLY&verification=VERIFIED",
    );
    expect(withFilter(params, "verification", null)).toBe("page=2&scope=INTEGRATION_ONLY");
    expect(withFilter(new URLSearchParams("verification=VERIFIED&data=SYNTHETIC_FIXTURE"), "verification", null)).toBe(
      "data=SYNTHETIC_FIXTURE",
    );
  });

  it("projects run catalog items without full evidence fields", () => {
    const item = getRunCatalogItems()[0];

    expect(item).toMatchObject({
      artifact_id: "demo-miracl-th-mini-v1",
      run_id: "demo-miracl-th-mini-v1",
      dataset_name: "miracl-th-mini",
      evaluation_type: "miracl_retrieval",
      verification_status: "VERIFIED",
      data_kind: "SYNTHETIC_FIXTURE",
      claim_scope: "INTEGRATION_ONLY",
    });
    for (const forbidden of ["evidence", "failures", "retrieved_document_ids", "relevant_document_ids", "scores", "raw_response"]) {
      expect(item).not.toHaveProperty(forbidden);
    }
  });

  it("projects comparisons with safe aggregate result and regression count", () => {
    const item = getComparisonCatalogItems()[0];

    expect(item).toMatchObject({
      artifact_id: "demo-retrieval-regression-v1",
      baseline_artifact_id: "demo-retrieval-reference-v1",
      candidate_artifact_id: "demo-retrieval-fixture-v1",
      population_compatibility: "MATCHED",
      result: "REGRESSION",
      regression_count: 4,
    });
    for (const forbidden of ["comparisons", "evidence", "failures", "baseline", "candidate", "raw_response"]) {
      expect(item).not.toHaveProperty(forbidden);
    }
  });

  it("does not label a missing-only comparison as a regression", () => {
    const bundle = structuredClone(getComparisonBundle("demo-retrieval-regression-v1"));
    bundle.comparison.passed = false;
    bundle.comparison.comparisons = bundle.comparison.comparisons.map((row) => ({
      ...row,
      status: "MISSING" as const,
    }));

    expect(deriveComparisonResult(bundle)).toBeNull();
  });

  it("labels passed comparisons as PASS before inspecting regression rows", () => {
    const bundle = structuredClone(getComparisonBundle("demo-retrieval-regression-v1"));
    bundle.comparison.passed = true;

    expect(deriveComparisonResult(bundle)).toBe("PASS");
  });
});
