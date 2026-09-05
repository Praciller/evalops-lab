import fs from "node:fs";
import path from "node:path";

import {
  EvidenceContractError,
  parsePublicEvidenceIndex,
  parsePublicRunArtifact,
  type PublicEvidenceIndex,
  type PublicRunArtifact,
} from "./schemas";

const EVIDENCE_ROOT = path.join(process.cwd(), "public", "evidence");
const ARTIFACT_ID_FOR_FILENAME = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;

function readApprovedJson(relativePath: "index.json" | `artifacts/${string}.json`): unknown {
  try {
    const absolutePath = path.join(EVIDENCE_ROOT, relativePath);
    return JSON.parse(fs.readFileSync(absolutePath, "utf8")) as unknown;
  } catch {
    throw new EvidenceContractError("Evidence unavailable");
  }
}

export function getEvidenceIndex(): PublicEvidenceIndex {
  return parsePublicEvidenceIndex(readApprovedJson("index.json"));
}

export function getRunArtifact(artifactId: string): PublicRunArtifact {
  const index = getEvidenceIndex();
  const summary = index.artifacts.find(
    (artifact) => artifact.artifact_id === artifactId && artifact.artifact_type === "run",
  );
  if (!summary || !ARTIFACT_ID_FOR_FILENAME.test(artifactId)) {
    throw new EvidenceContractError("Evidence unavailable");
  }

  const artifact = parsePublicRunArtifact(
    readApprovedJson(`artifacts/${artifactId}.json`),
  );
  if (
    artifact.artifact_id !== summary.artifact_id ||
    artifact.artifact_type !== summary.artifact_type ||
    artifact.verification_status !== summary.verification_status ||
    artifact.data_kind !== summary.data_kind ||
    artifact.claim_scope !== summary.claim_scope
  ) {
    throw new EvidenceContractError("Evidence unavailable");
  }
  return artifact;
}

export function getApprovedRunArtifacts(index = getEvidenceIndex()): PublicRunArtifact[] {
  return index.artifacts
    .filter((artifact) => artifact.artifact_type === "run")
    .map((artifact) => getRunArtifact(artifact.artifact_id));
}
