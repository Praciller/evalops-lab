import {
  getApprovedComparisonBundles,
  getEvidenceIndex,
  type ComparisonBundle,
} from "@/lib/evidence/repository";
import type { PublicArtifactSummary } from "@/lib/evidence/schemas";

export type RunCatalogItem = {
  artifact_id: string;
  run_id: string | null;
  dataset_name: string | null;
  evaluation_type: string | null;
  verification_status: PublicArtifactSummary["verification_status"];
  data_kind: PublicArtifactSummary["data_kind"];
  claim_scope: PublicArtifactSummary["claim_scope"];
  metrics: Record<string, number>;
};

export type ComparisonResultFilter = "PASS" | "REGRESSION";

export type ComparisonCatalogItem = {
  artifact_id: string;
  baseline_artifact_id: string;
  candidate_artifact_id: string;
  verification_status: PublicArtifactSummary["verification_status"];
  data_kind: PublicArtifactSummary["data_kind"];
  claim_scope: PublicArtifactSummary["claim_scope"];
  population_compatibility: "MATCHED" | "UNVERIFIED" | "INCOMPATIBLE";
  result: ComparisonResultFilter | null;
  regression_count: number;
};

export function deriveComparisonResult(bundle: ComparisonBundle): ComparisonResultFilter | null {
  if (bundle.comparison.passed) return "PASS";
  return bundle.comparison.comparisons.some((row) => row.status === "REGRESSION")
    ? "REGRESSION"
    : null;
}

export function getRunCatalogItems(): RunCatalogItem[] {
  return getEvidenceIndex().artifacts
    .filter((artifact) => artifact.artifact_type === "run")
    .map((artifact) => ({
      artifact_id: artifact.artifact_id,
      run_id: artifact.run_id,
      dataset_name: artifact.dataset_name,
      evaluation_type: artifact.evaluation_type,
      verification_status: artifact.verification_status,
      data_kind: artifact.data_kind,
      claim_scope: artifact.claim_scope,
      metrics: artifact.metrics,
    }));
}

function projectComparison(bundle: ComparisonBundle): ComparisonCatalogItem {
  return {
    artifact_id: bundle.comparison.artifact_id,
    baseline_artifact_id: bundle.comparison.baseline_artifact_id,
    candidate_artifact_id: bundle.comparison.candidate_artifact_id,
    verification_status: bundle.comparison.verification_status,
    data_kind: bundle.comparison.data_kind,
    claim_scope: bundle.comparison.claim_scope,
    population_compatibility: bundle.comparison.population_compatibility,
    result: deriveComparisonResult(bundle),
    regression_count: bundle.comparison.comparisons.filter((row) => row.status === "REGRESSION").length,
  };
}

export function getComparisonCatalogItems(): ComparisonCatalogItem[] {
  return getApprovedComparisonBundles(getEvidenceIndex()).map(projectComparison);
}
