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
});
