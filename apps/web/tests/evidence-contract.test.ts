import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import {
  parsePublicEvidenceIndex,
  parsePublicRunArtifact,
} from "@/lib/evidence/schemas";

const evidenceRoot = path.resolve(process.cwd(), "public/evidence");

function readJson(file: string) {
  return JSON.parse(fs.readFileSync(path.join(evidenceRoot, file), "utf8")) as unknown;
}

function readRunArtifact() {
  return readJson("artifacts/demo-retrieval-fixture-v1.json") as Record<string, unknown>;
}

function readIndex() {
  return readJson("index.json") as {
    artifacts: Array<Record<string, unknown>>;
    [key: string]: unknown;
  };
}

function comparisonSummary(overrides: Record<string, unknown> = {}) {
  return {
    artifact_id: "comparison-v1",
    artifact_type: "comparison",
    run_id: null,
    dataset_name: null,
    evaluation_type: null,
    verification_status: "VERIFIED",
    data_kind: "SYNTHETIC_FIXTURE",
    claim_scope: "INTEGRATION_ONLY",
    metrics: {},
    baseline_artifact_id: "demo-retrieval-fixture-v1",
    candidate_artifact_id: "demo-miracl-th-mini-v1",
    ...overrides,
  };
}

function withArtifacts(artifacts: Array<Record<string, unknown>>) {
  return { ...readIndex(), artifacts };
}

describe("Public Evidence Contract V1 mirror", () => {
  it("parses the checked-in explicit index and both run artifacts", () => {
    const index = parsePublicEvidenceIndex(readJson("index.json"));
    expect(index.catalog_status).toBe("EXPLICIT_ALLOWLIST");
    expect(index.artifacts).toHaveLength(2);

    for (const summary of index.artifacts) {
      expect(parsePublicRunArtifact(readJson(`artifacts/${summary.artifact_id}.json`)).artifact_id).toBe(summary.artifact_id);
    }
  });

  it("rejects unsupported schemas and arbitrary internal details", () => {
    const artifact = readJson("artifacts/demo-retrieval-fixture-v1.json") as Record<string, unknown>;
    expect(() => parsePublicRunArtifact({ ...artifact, schema_version: "public-evidence-v2" })).toThrow("Evidence unavailable");
    expect(() => parsePublicRunArtifact({ ...artifact, details: { raw_response: "hidden" } })).toThrow("Evidence unavailable");
  });

  it.each([
    ["synthetic benchmark claim", { data_kind: "SYNTHETIC_FIXTURE", claim_scope: "BENCHMARK_RESULT" }],
    ["synthetic protocol claim", { data_kind: "SYNTHETIC_FIXTURE", claim_scope: "PROTOCOL_SPECIFIC" }],
    ["curated benchmark claim", { data_kind: "CURATED_DATASET", claim_scope: "BENCHMARK_RESULT" }],
    ["not-run artifact", { verification_status: "NOT_RUN" }],
  ])("rejects %s", (_label, overrides) => {
    expect(() => parsePublicRunArtifact({ ...readRunArtifact(), ...overrides })).toThrow("Evidence unavailable");
  });

  it("accepts an official benchmark claim", () => {
    expect(parsePublicRunArtifact({
      ...readRunArtifact(),
      data_kind: "OFFICIAL_BENCHMARK",
      claim_scope: "BENCHMARK_RESULT",
    }).claim_scope).toBe("BENCHMARK_RESULT");
  });

  it("accepts an official benchmark comparison summary", () => {
    expect(parsePublicEvidenceIndex(withArtifacts([
      ...readIndex().artifacts,
      comparisonSummary({
        data_kind: "OFFICIAL_BENCHMARK",
        claim_scope: "BENCHMARK_RESULT",
      }),
    ])).artifacts.at(-1)?.claim_scope).toBe("BENCHMARK_RESULT");
  });

  it("accepts comparison references to runs listed later in the index", () => {
    expect(parsePublicEvidenceIndex(withArtifacts([
      comparisonSummary(),
      ...readIndex().artifacts,
    ])).artifacts[0].artifact_type).toBe("comparison");
  });

  it.each([
    ["comparison synthetic benchmark", { data_kind: "SYNTHETIC_FIXTURE", claim_scope: "BENCHMARK_RESULT" }],
    ["comparison synthetic protocol", { data_kind: "SYNTHETIC_FIXTURE", claim_scope: "PROTOCOL_SPECIFIC" }],
    ["comparison curated benchmark", { data_kind: "CURATED_DATASET", claim_scope: "BENCHMARK_RESULT" }],
    ["comparison not-run", { verification_status: "NOT_RUN" }],
  ])("rejects %s", (_label, overrides) => {
    expect(() => parsePublicEvidenceIndex(withArtifacts([
      ...readIndex().artifacts,
      comparisonSummary(overrides),
    ]))).toThrow("Evidence unavailable");
  });

  it.each([
    ["duplicate artifact IDs", withArtifacts([readIndex().artifacts[0], { ...readIndex().artifacts[1], artifact_id: readIndex().artifacts[0].artifact_id }])],
    ["missing baseline", withArtifacts([...readIndex().artifacts, comparisonSummary({ baseline_artifact_id: null })])],
    ["missing candidate", withArtifacts([...readIndex().artifacts, comparisonSummary({ candidate_artifact_id: null })])],
    ["dangling baseline", withArtifacts([...readIndex().artifacts, comparisonSummary({ baseline_artifact_id: "missing-run" })])],
    ["dangling candidate", withArtifacts([...readIndex().artifacts, comparisonSummary({ candidate_artifact_id: "missing-run" })])],
    ["comparison reference", withArtifacts([...readIndex().artifacts, comparisonSummary({ baseline_artifact_id: "comparison-v1" })])],
    ["self comparison", withArtifacts([...readIndex().artifacts, comparisonSummary({ candidate_artifact_id: "demo-retrieval-fixture-v1" })])],
    ["run comparison references", withArtifacts([{ ...readIndex().artifacts[0], baseline_artifact_id: "demo-miracl-th-mini-v1" }, readIndex().artifacts[1]])],
    ["not-run summary", withArtifacts([{ ...readIndex().artifacts[0], verification_status: "NOT_RUN" }, readIndex().artifacts[1]])],
  ])("rejects index %s", (_label, payload) => {
    expect(() => parsePublicEvidenceIndex(payload)).toThrow("Evidence unavailable");
  });

  it.each([
    ["raw_response", { raw_response: "secret" }],
    ["raw_corpus", { raw_corpus: "secret" }],
    ["hidden_reasoning", { hidden_reasoning: "secret" }],
    ["api_key", { api_key: "secret" }],
    ["authorization", { authorization: "Bearer secret" }],
  ])("rejects arbitrary %s fields", (_label, extra) => {
    expect(() => parsePublicRunArtifact({ ...readRunArtifact(), ...extra })).toThrow("Evidence unavailable");
  });
});
