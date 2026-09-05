import fs from "node:fs";
import path from "node:path";

import {
  EvidenceContractError,
  parsePublicComparisonArtifact,
  parsePublicEvidenceIndex,
  parsePublicRunArtifact,
  type PublicComparisonArtifact,
  type PublicEvidenceIndex,
  type PublicRunArtifact,
} from "./schemas";

const EVIDENCE_ROOT = path.join(process.cwd(), "public", "evidence");
const ARTIFACT_ID_FOR_FILENAME = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;
const POPULATION_FIELDS = [
  "dataset_name",
  "dataset_version",
  "dataset_revision",
  "evaluation_type",
  "benchmark",
  "language",
  "split",
  "top_k",
] as const;
const VERIFICATION_STRENGTH = { UNVERIFIED: 0, PARTIAL: 1, VERIFIED: 2 } as const;

export type ComparisonBundle = {
  comparison: PublicComparisonArtifact;
  baseline: PublicRunArtifact;
  candidate: PublicRunArtifact;
};

function metricsMatch(
  left: Record<string, number>,
  right: Record<string, number>,
): boolean {
  const leftKeys = Object.keys(left).sort();
  const rightKeys = Object.keys(right).sort();
  return (
    leftKeys.length === rightKeys.length &&
    leftKeys.every(
      (key, index) => key === rightKeys[index] && Object.is(left[key], right[key]),
    )
  );
}

function stringMapMatch(left: Record<string, string>, right: Record<string, string>): boolean {
  const leftKeys = Object.keys(left).sort();
  const rightKeys = Object.keys(right).sort();
  return (
    leftKeys.length === rightKeys.length &&
    leftKeys.every((key, index) => key === rightKeys[index] && left[key] === right[key])
  );
}

function populationsMatch(baseline: PublicRunArtifact, candidate: PublicRunArtifact): boolean {
  return (
    POPULATION_FIELDS.every((field) => Object.is(baseline.run[field], candidate.run[field])) &&
    stringMapMatch(baseline.run.evaluator_versions, candidate.run.evaluator_versions)
  );
}

function verificationStrength(status: string): number {
  return VERIFICATION_STRENGTH[status as keyof typeof VERIFICATION_STRENGTH] ?? -1;
}

function comparisonValuesMatch(
  comparison: PublicComparisonArtifact,
  baseline: PublicRunArtifact,
  candidate: PublicRunArtifact,
): boolean {
  const metricNames = comparison.comparisons.map((row) => row.metric_name);
  if (new Set(metricNames).size !== metricNames.length) return false;
  const rowsMatch = comparison.comparisons.every((row) => {
    const baselineValue = baseline.metrics[row.metric_name];
    const candidateValue = candidate.metrics[row.metric_name];
    return (
      baselineValue !== undefined &&
      candidateValue !== undefined &&
      Object.is(row.baseline_value, baselineValue) &&
      Object.is(row.candidate_value, candidateValue) &&
      Object.is(row.delta, candidateValue - baselineValue)
    );
  });
  const expectedPassed = comparison.comparisons.every((row) => row.status === "PASS");
  return rowsMatch && comparison.passed === expectedPassed;
}

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
    artifact.claim_scope !== summary.claim_scope ||
    artifact.run.run_id !== summary.run_id ||
    artifact.run.dataset_name !== summary.dataset_name ||
    artifact.run.evaluation_type !== summary.evaluation_type ||
    !metricsMatch(artifact.metrics, summary.metrics)
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

export function getComparisonArtifact(artifactId: string): PublicComparisonArtifact {
  const index = getEvidenceIndex();
  const summary = index.artifacts.find(
    (artifact) => artifact.artifact_id === artifactId && artifact.artifact_type === "comparison",
  );
  if (!summary || !ARTIFACT_ID_FOR_FILENAME.test(artifactId)) {
    throw new EvidenceContractError("Evidence unavailable");
  }

  const artifact = parsePublicComparisonArtifact(
    readApprovedJson(`artifacts/${artifactId}.json`),
  );
  if (
    artifact.artifact_id !== summary.artifact_id ||
    artifact.artifact_type !== summary.artifact_type ||
    artifact.verification_status !== summary.verification_status ||
    artifact.data_kind !== summary.data_kind ||
    artifact.claim_scope !== summary.claim_scope ||
    artifact.baseline_artifact_id !== summary.baseline_artifact_id ||
    artifact.candidate_artifact_id !== summary.candidate_artifact_id ||
    artifact.candidate_run_id !== summary.run_id
  ) {
    throw new EvidenceContractError("Evidence unavailable");
  }
  return artifact;
}

export function getComparisonBundle(artifactId: string): ComparisonBundle {
  const comparison = getComparisonArtifact(artifactId);
  if (
    comparison.baseline_artifact_id === comparison.candidate_artifact_id ||
    comparison.population_compatibility !== "MATCHED"
  ) {
    throw new EvidenceContractError("Evidence unavailable");
  }

  const baseline = getRunArtifact(comparison.baseline_artifact_id);
  const candidate = getRunArtifact(comparison.candidate_artifact_id);
  if (
    comparison.baseline_run_id !== baseline.run.run_id ||
    comparison.candidate_run_id !== candidate.run.run_id ||
    comparison.data_kind !== baseline.data_kind ||
    comparison.data_kind !== candidate.data_kind ||
    comparison.claim_scope !== baseline.claim_scope ||
    comparison.claim_scope !== candidate.claim_scope ||
    comparison.data_kind !== "SYNTHETIC_FIXTURE" ||
    comparison.claim_scope !== "INTEGRATION_ONLY" ||
    verificationStrength(comparison.verification_status) >
      Math.min(
        verificationStrength(baseline.verification_status),
        verificationStrength(candidate.verification_status),
      ) ||
    !populationsMatch(baseline, candidate) ||
    !comparisonValuesMatch(comparison, baseline, candidate)
  ) {
    throw new EvidenceContractError("Evidence unavailable");
  }
  return { comparison, baseline, candidate };
}

export function getApprovedComparisonBundles(
  index = getEvidenceIndex(),
): ComparisonBundle[] {
  return index.artifacts
    .filter((artifact) => artifact.artifact_type === "comparison")
    .map((artifact) => getComparisonBundle(artifact.artifact_id));
}
