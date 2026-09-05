import type { PublicRunArtifact } from "./schemas";

type PublicEvidenceRecord = PublicRunArtifact["evidence"][number];

export type FailureTransitionKind =
  | "STABLE_PASS"
  | "INTRODUCED_FAILURE"
  | "RESOLVED_FAILURE"
  | "PERSISTENT_CATEGORY"
  | "CHANGED_FAILURE_CATEGORY";

export type MetricDelta = {
  metricName: string;
  baselineValue: number | null;
  candidateValue: number | null;
  delta: number | null;
};

export type FailureTransitionRow = {
  recordRef: string;
  kind: FailureTransitionKind;
  baselineCategory: string;
  candidateCategory: string;
  metricDeltas: MetricDelta[];
  baselineRecord: PublicEvidenceRecord;
  candidateRecord: PublicEvidenceRecord;
};

export type FailureTransitionResult =
  | { status: "AVAILABLE"; rows: FailureTransitionRow[] }
  | { status: "UNAVAILABLE"; reason: "RECORD_SET_MISMATCH" };

export function hasRecordChange(row: FailureTransitionRow): boolean {
  return (
    row.metricDeltas.length > 0 ||
    row.kind === "INTRODUCED_FAILURE" ||
    row.kind === "RESOLVED_FAILURE" ||
    row.kind === "CHANGED_FAILURE_CATEGORY"
  );
}

function classifyTransition(baseline: string, candidate: string): FailureTransitionKind {
  if (baseline === "PASS" && candidate === "PASS") return "STABLE_PASS";
  if (baseline === "PASS") return "INTRODUCED_FAILURE";
  if (candidate === "PASS") return "RESOLVED_FAILURE";
  return baseline === candidate ? "PERSISTENT_CATEGORY" : "CHANGED_FAILURE_CATEGORY";
}

function metricDeltas(
  baseline: PublicEvidenceRecord,
  candidate: PublicEvidenceRecord,
): MetricDelta[] {
  const names = [
    ...new Set([...Object.keys(baseline.metrics), ...Object.keys(candidate.metrics)]),
  ].sort();
  return names.flatMap((metricName) => {
    const baselineValue = baseline.metrics[metricName] ?? null;
    const candidateValue = candidate.metrics[metricName] ?? null;
    if (baselineValue !== null && candidateValue !== null && Object.is(baselineValue, candidateValue)) {
      return [];
    }
    return [{
      metricName,
      baselineValue,
      candidateValue,
      delta: baselineValue === null || candidateValue === null
        ? null
        : candidateValue - baselineValue,
    }];
  });
}

function buildTransitionRow(
  recordRef: string,
  baseline: PublicEvidenceRecord,
  candidate: PublicEvidenceRecord,
): FailureTransitionRow {
  return {
    recordRef,
    kind: classifyTransition(baseline.failure_category, candidate.failure_category),
    baselineCategory: baseline.failure_category,
    candidateCategory: candidate.failure_category,
    metricDeltas: metricDeltas(baseline, candidate),
    baselineRecord: baseline,
    candidateRecord: candidate,
  };
}

export function buildFailureTransitions(
  baseline: PublicRunArtifact,
  candidate: PublicRunArtifact,
): FailureTransitionResult {
  const baselineById = new Map(baseline.evidence.map((record) => [record.record_ref, record]));
  const candidateById = new Map(candidate.evidence.map((record) => [record.record_ref, record]));
  if (
    baselineById.size !== baseline.evidence.length ||
    candidateById.size !== candidate.evidence.length
  ) {
    return { status: "UNAVAILABLE", reason: "RECORD_SET_MISMATCH" };
  }
  const baselineIds = [...baselineById.keys()].sort();
  const candidateIds = [...candidateById.keys()].sort();
  if (
    baselineIds.length !== candidateIds.length ||
    baselineIds.some((id, index) => id !== candidateIds[index])
  ) {
    return { status: "UNAVAILABLE", reason: "RECORD_SET_MISMATCH" };
  }
  return {
    status: "AVAILABLE",
    rows: baselineIds.map((recordRef) => buildTransitionRow(
      recordRef,
      baselineById.get(recordRef)!,
      candidateById.get(recordRef)!,
    )),
  };
}
