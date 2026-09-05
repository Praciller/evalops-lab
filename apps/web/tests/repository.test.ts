import { describe, expect, it } from "vitest";

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
});
