import fs from "node:fs";
import path from "node:path";

import { describe, expect, it, vi } from "vitest";

import { getApprovedRunArtifacts, getEvidenceIndex, getRunArtifact } from "@/lib/evidence/repository";

describe("evidence repository", () => {
  it("loads only artifacts named by the explicit index", () => {
    const index = getEvidenceIndex();
    const artifacts = getApprovedRunArtifacts(index);
    expect(artifacts.map((artifact) => artifact.artifact_id)).toEqual([
      "demo-miracl-th-mini-v1",
      "demo-retrieval-fixture-v1",
    ]);
  });

  it("fails closed for unknown or unsafe artifact IDs", () => {
    expect(() => getRunArtifact("missing-artifact")).toThrow("Evidence unavailable");
    expect(() => getRunArtifact("../secrets")).toThrow("Evidence unavailable");
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
