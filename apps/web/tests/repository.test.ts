import fs from "node:fs";
import path from "node:path";

import { describe, expect, it, vi } from "vitest";

import {
  getApprovedComparisonBundles,
  getApprovedRunArtifacts,
  getComparisonArtifact,
  getComparisonBundle,
  getEvidenceIndex,
  getRunArtifact,
} from "@/lib/evidence/repository";

function withArtifactMutation(
  artifactId: string,
  mutate: (artifact: Record<string, unknown>) => void,
  assertion: () => void,
) {
  const artifactPath = path.join(
    process.cwd(),
    "public/evidence/artifacts",
    `${artifactId}.json`,
  );
  const originalReadFileSync = fs.readFileSync;
  const readFileSyncSpy = vi.spyOn(fs, "readFileSync").mockImplementation((file, options) => {
    const content = originalReadFileSync(file, options);
    if (String(file) !== artifactPath || typeof content !== "string") return content;
    const artifact = JSON.parse(content) as Record<string, unknown>;
    mutate(artifact);
    return JSON.stringify(artifact);
  });

  try {
    assertion();
  } finally {
    readFileSyncSpy.mockRestore();
  }
}

function withIndexMutation(
  mutate: (index: Record<string, unknown>) => void,
  assertion: () => void,
) {
  const indexPath = path.join(process.cwd(), "public/evidence/index.json");
  const originalReadFileSync = fs.readFileSync;
  const readFileSyncSpy = vi.spyOn(fs, "readFileSync").mockImplementation((file, options) => {
    const content = originalReadFileSync(file, options);
    if (String(file) !== indexPath || typeof content !== "string") return content;
    const index = JSON.parse(content) as Record<string, unknown>;
    mutate(index);
    return JSON.stringify(index);
  });

  try {
    assertion();
  } finally {
    readFileSyncSpy.mockRestore();
  }
}

function withEvidenceMutations(
  mutateArtifacts: (artifactId: string, artifact: Record<string, unknown>) => void,
  mutateIndex: (index: Record<string, unknown>) => void,
  assertion: () => void,
) {
  const artifactRoot = path.join(process.cwd(), "public/evidence/artifacts");
  const indexPath = path.join(process.cwd(), "public/evidence/index.json");
  const originalReadFileSync = fs.readFileSync;
  const readFileSyncSpy = vi.spyOn(fs, "readFileSync").mockImplementation((file, options) => {
    const content = originalReadFileSync(file, options);
    if (typeof content !== "string") return content;
    if (String(file) === indexPath) {
      const index = JSON.parse(content) as Record<string, unknown>;
      mutateIndex(index);
      return JSON.stringify(index);
    }
    if (String(file).startsWith(`${artifactRoot}${path.sep}`)) {
      const artifactId = path.basename(String(file), ".json");
      const artifact = JSON.parse(content) as Record<string, unknown>;
      mutateArtifacts(artifactId, artifact);
      return JSON.stringify(artifact);
    }
    return content;
  });

  try {
    assertion();
  } finally {
    readFileSyncSpy.mockRestore();
  }
}

describe("evidence repository", () => {
  it("loads only artifacts named by the explicit index", () => {
    const index = getEvidenceIndex();
    const artifacts = getApprovedRunArtifacts(index);
    expect(artifacts.map((artifact) => artifact.artifact_id)).toEqual([
      "demo-miracl-th-mini-v1",
      "demo-retrieval-fixture-v1",
      "demo-retrieval-reference-v1",
    ]);
  });

  it("loads the matched comparison bundle", () => {
    const bundle = getComparisonBundle("demo-retrieval-regression-v1");
    expect(bundle.baseline.artifact_id).toBe("demo-retrieval-reference-v1");
    expect(bundle.candidate.artifact_id).toBe("demo-retrieval-fixture-v1");
    expect(bundle.comparison.population_compatibility).toBe("MATCHED");
    expect(bundle.comparison.data_kind).toBe("SYNTHETIC_FIXTURE");
    expect(bundle.comparison.claim_scope).toBe("INTEGRATION_ONLY");
    expect(getApprovedComparisonBundles()).toHaveLength(1);
  });

  it("fails closed for unknown or unsafe artifact IDs", () => {
    expect(() => getRunArtifact("missing-artifact")).toThrow("Evidence unavailable");
    expect(() => getRunArtifact("../secrets")).toThrow("Evidence unavailable");
    expect(() => getComparisonArtifact("missing-comparison")).toThrow("Evidence unavailable");
    expect(() => getComparisonArtifact("../secrets")).toThrow("Evidence unavailable");
  });

  it.each([
    ["missing baseline", (index: Record<string, unknown>) => {
      const artifacts = index.artifacts as Array<Record<string, unknown>>;
      artifacts.find((item) => item.artifact_id === "demo-retrieval-regression-v1")!.baseline_artifact_id = null;
    }],
    ["missing candidate", (index: Record<string, unknown>) => {
      const artifacts = index.artifacts as Array<Record<string, unknown>>;
      artifacts.find((item) => item.artifact_id === "demo-retrieval-regression-v1")!.candidate_artifact_id = null;
    }],
  ])("rejects %s comparison summary", (_label, mutate) => {
    withIndexMutation(mutate, () => {
      expect(() => getComparisonArtifact("demo-retrieval-regression-v1")).toThrow("Evidence unavailable");
    });
  });

  it.each([
    ["baseline run id", (artifact: Record<string, unknown>) => { artifact.baseline_run_id = "edited-run"; }],
    ["candidate reference", (artifact: Record<string, unknown>) => { artifact.candidate_artifact_id = "demo-miracl-th-mini-v1"; }],
    ["candidate run id", (artifact: Record<string, unknown>) => { artifact.candidate_run_id = "edited-run"; }],
    ["comparison delta", (artifact: Record<string, unknown>) => { (artifact.comparisons as Array<Record<string, unknown>>)[0].delta = 0.123; }],
    ["population flag", (artifact: Record<string, unknown>) => { artifact.population_compatibility = "UNVERIFIED"; }],
  ])("rejects comparison %s tampering", (_label, mutate) => {
    withArtifactMutation("demo-retrieval-regression-v1", mutate, () => {
      expect(() => getComparisonBundle("demo-retrieval-regression-v1")).toThrow("Evidence unavailable");
    });
  });

  it("rejects comparison data_kind mismatch at the repository boundary", () => {
    withEvidenceMutations(
      (artifactId, artifact) => {
        if (artifactId === "demo-retrieval-regression-v1") artifact.data_kind = "OFFICIAL_BENCHMARK";
      },
      (index) => {
        const summary = (index.artifacts as Array<Record<string, unknown>>).find(
          (item) => item.artifact_id === "demo-retrieval-regression-v1",
        )!;
        summary.data_kind = "OFFICIAL_BENCHMARK";
      },
      () => expect(() => getComparisonBundle("demo-retrieval-regression-v1")).toThrow("Evidence unavailable"),
    );
  });

  it("rejects schema-valid comparison claim_scope mismatch at the repository boundary", () => {
    withEvidenceMutations(
      (artifactId, artifact) => {
        if (artifactId === "demo-retrieval-regression-v1") {
          artifact.data_kind = "CURATED_DATASET";
          artifact.claim_scope = "PROTOCOL_SPECIFIC";
        }
        if (artifactId === "demo-retrieval-reference-v1" || artifactId === "demo-retrieval-fixture-v1") {
          artifact.data_kind = "CURATED_DATASET";
        }
      },
      (index) => {
        for (const summary of index.artifacts as Array<Record<string, unknown>>) {
          if (summary.artifact_id === "demo-retrieval-regression-v1") {
            summary.data_kind = "CURATED_DATASET";
            summary.claim_scope = "PROTOCOL_SPECIFIC";
          } else if (
            summary.artifact_id === "demo-retrieval-reference-v1" ||
            summary.artifact_id === "demo-retrieval-fixture-v1"
          ) {
            summary.data_kind = "CURATED_DATASET";
          }
        }
      },
      () => expect(() => getComparisonBundle("demo-retrieval-regression-v1")).toThrow("Evidence unavailable"),
    );
  });

  it("rejects comparison verification stronger than the weakest operand", () => {
    withEvidenceMutations(
      (artifactId, artifact) => {
        if (artifactId === "demo-retrieval-fixture-v1") artifact.verification_status = "PARTIAL";
      },
      (index) => {
        const summary = (index.artifacts as Array<Record<string, unknown>>).find(
          (item) => item.artifact_id === "demo-retrieval-fixture-v1",
        )!;
        summary.verification_status = "PARTIAL";
      },
      () => expect(() => getComparisonBundle("demo-retrieval-regression-v1")).toThrow("Evidence unavailable"),
    );
  });

  it("rejects dangling and comparison-to-comparison references", () => {
    withArtifactMutation("demo-retrieval-regression-v1", (artifact) => {
      artifact.baseline_artifact_id = "missing-run";
    }, () => {
      expect(() => getComparisonBundle("demo-retrieval-regression-v1")).toThrow("Evidence unavailable");
    });
    withArtifactMutation("demo-retrieval-regression-v1", (artifact) => {
      artifact.baseline_artifact_id = "demo-retrieval-regression-v1";
    }, () => {
      expect(() => getComparisonBundle("demo-retrieval-regression-v1")).toThrow("Evidence unavailable");
    });
  });

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

  it.each([
    ["run_id", { run_id: "edited-run" }],
    ["dataset_name", { dataset_name: "edited-dataset" }],
    ["evaluation_type", { evaluation_type: "edited-evaluation" }],
    ["metrics", { metrics: { hit_rate_at_5: 0.99 } }],
  ])("rejects index %s mismatch", (_field, runOverrides) => {
    const artifactPath = path.join(
      process.cwd(),
      "public/evidence/artifacts/demo-retrieval-fixture-v1.json",
    );
    const originalReadFileSync = fs.readFileSync;
    const readFileSyncSpy = vi.spyOn(fs, "readFileSync").mockImplementation((file, options) => {
      const content = originalReadFileSync(file, options);
      if (String(file) !== artifactPath || typeof content !== "string") return content;
      const artifact = JSON.parse(content) as Record<string, unknown>;
      if ("metrics" in runOverrides) {
        artifact.metrics = runOverrides.metrics;
      } else {
        artifact.run = { ...(artifact.run as Record<string, unknown>), ...runOverrides };
      }
      return JSON.stringify(artifact);
    });

    try {
      expect(() => getRunArtifact("demo-retrieval-fixture-v1")).toThrow("Evidence unavailable");
    } finally {
      readFileSyncSpy.mockRestore();
    }
  });
});
