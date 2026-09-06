import { z } from "zod";

const SafeIdentifier = z.string().min(1).max(160).regex(/^[A-Za-z0-9][A-Za-z0-9._:-]*$/);
const SafeText = z.string().min(1).max(500);
const NullableText = z.string().max(500).nullable();
const Metrics = z.record(z.string().min(1), z.number().finite());

const RunMetadata = z
  .object({
    evaluation_type: SafeText,
    run_id: SafeIdentifier,
    dataset_name: SafeText,
    dataset_version: SafeText,
    dataset_revision: NullableText,
    system_name: SafeText,
    model: NullableText,
    model_provider: NullableText,
    benchmark: NullableText,
    language: NullableText,
    split: NullableText,
    retriever: NullableText,
    retriever_version: NullableText,
    tokenization_strategy: NullableText,
    top_k: z.number().int().positive(),
    evaluator_versions: z.record(z.string().min(1), SafeText),
    random_seed: z.number().int().nullable(),
    timestamp: z.string().datetime({ offset: true }),
    git_commit: z.string().regex(/^[A-Za-z0-9._:-]+$/).nullable(),
  })
  .strict();

const EvidenceRecord = z
  .object({
    record_ref: SafeIdentifier,
    metrics: Metrics,
    metrics_by_k: z.record(z.string().min(1), Metrics),
    failure_category: SafeIdentifier,
    retrieved_document_ids: z.array(SafeIdentifier),
    relevant_document_ids: z.array(SafeIdentifier),
    scores: z.array(z.number().finite()),
  })
  .strict();

const Failure = z
  .object({
    record_ref: SafeIdentifier,
    category: SafeIdentifier,
    failure_class: SafeIdentifier.nullable(),
  })
  .strict();

const VerificationStatus = z.enum(["VERIFIED", "PARTIAL", "UNVERIFIED", "NOT_RUN"]);
const DataKind = z.enum(["SYNTHETIC_FIXTURE", "CURATED_DATASET", "OFFICIAL_BENCHMARK"]);
const ClaimScope = z.enum(["INTEGRATION_ONLY", "PROTOCOL_SPECIFIC", "BENCHMARK_RESULT"]);
const MetricDirection = z.enum(["higher_is_better", "lower_is_better"]);
const RegressionStatus = z.enum(["PASS", "REGRESSION", "MISSING"]);
export const PopulationCompatibility = z.enum(["MATCHED", "UNVERIFIED", "INCOMPATIBLE"]);
export type PopulationCompatibility = z.infer<typeof PopulationCompatibility>;

const ClaimFields = {
  verification_status: VerificationStatus,
  data_kind: DataKind,
  claim_scope: ClaimScope,
  limitations: z.array(SafeText),
};

const SummaryClaimFields = {
  verification_status: VerificationStatus,
  data_kind: DataKind,
  claim_scope: ClaimScope,
};

type ClaimDimensions = {
  verification_status: z.infer<typeof VerificationStatus>;
  data_kind: z.infer<typeof DataKind>;
  claim_scope: z.infer<typeof ClaimScope>;
};

function validateClaimDimensions(value: ClaimDimensions, ctx: z.RefinementCtx) {
  if (value.verification_status === "NOT_RUN") {
    ctx.addIssue({
      code: "custom",
      path: ["verification_status"],
      message: "executed evidence cannot be NOT_RUN",
    });
  }
  if (value.data_kind === "SYNTHETIC_FIXTURE" && value.claim_scope !== "INTEGRATION_ONLY") {
    ctx.addIssue({
      code: "custom",
      path: ["claim_scope"],
      message: "synthetic fixtures require INTEGRATION_ONLY",
    });
  }
  if (value.claim_scope === "BENCHMARK_RESULT" && value.data_kind !== "OFFICIAL_BENCHMARK") {
    ctx.addIssue({
      code: "custom",
      path: ["data_kind"],
      message: "BENCHMARK_RESULT requires OFFICIAL_BENCHMARK",
    });
  }
}

export const PublicRunArtifactSchema = z
  .object({
    schema_version: z.literal("public-evidence-v1"),
    artifact_id: SafeIdentifier,
    artifact_type: z.literal("run"),
    ...ClaimFields,
    run: RunMetadata,
    metrics: Metrics,
    failures: z.array(Failure),
    evidence: z.array(EvidenceRecord),
  })
  .strict()
  .superRefine(validateClaimDimensions);

const PublicComparisonMetricSchema = z
  .object({
    metric_name: SafeIdentifier,
    direction: MetricDirection,
    baseline_value: z.number().finite().nullable(),
    candidate_value: z.number().finite().nullable(),
    delta: z.number().finite().nullable(),
    status: RegressionStatus,
    reason: SafeText,
  })
  .strict();

export const PublicComparisonArtifactSchema = z
  .object({
    schema_version: z.literal("public-evidence-v1"),
    artifact_id: SafeIdentifier,
    artifact_type: z.literal("comparison"),
    ...ClaimFields,
    baseline_artifact_id: SafeIdentifier,
    candidate_artifact_id: SafeIdentifier,
    baseline_run_id: SafeIdentifier.nullable(),
    candidate_run_id: SafeIdentifier.nullable(),
    passed: z.boolean(),
    comparisons: z.array(PublicComparisonMetricSchema),
    population_compatibility: PopulationCompatibility,
  })
  .strict()
  .superRefine((value, ctx) => {
    validateClaimDimensions(value, ctx);
    if (value.baseline_artifact_id === value.candidate_artifact_id) {
      ctx.addIssue({
        code: "custom",
        path: ["candidate_artifact_id"],
        message: "self comparison",
      });
    }
  });

export const PublicArtifactSummarySchema = z
  .object({
    artifact_id: SafeIdentifier,
    artifact_type: z.enum(["run", "comparison"]),
    run_id: SafeIdentifier.nullable(),
    dataset_name: NullableText,
    evaluation_type: NullableText,
    ...SummaryClaimFields,
    metrics: Metrics,
    baseline_artifact_id: SafeIdentifier.nullable(),
    candidate_artifact_id: SafeIdentifier.nullable(),
  })
  .strict()
  .superRefine(validateClaimDimensions);

type ParsedArtifactSummary = z.infer<typeof PublicArtifactSummarySchema>;

function validateIndexIntegrity(
  value: { artifacts: ParsedArtifactSummary[] },
  ctx: z.RefinementCtx,
) {
  const artifactIndexes = new Map<string, number>();
  value.artifacts.forEach((artifact, index) => {
    const previousIndex = artifactIndexes.get(artifact.artifact_id);
    if (previousIndex !== undefined) {
      ctx.addIssue({
        code: "custom",
        path: ["artifacts", index, "artifact_id"],
        message: `duplicate artifact_id also appears at index ${previousIndex}`,
      });
    } else {
      artifactIndexes.set(artifact.artifact_id, index);
    }
  });

  value.artifacts.forEach((artifact, index) => {
    if (artifact.artifact_type === "run") {
      if (artifact.baseline_artifact_id !== null || artifact.candidate_artifact_id !== null) {
        ctx.addIssue({
          code: "custom",
          path: ["artifacts", index],
          message: "run summaries cannot include comparison references",
        });
      }
      return;
    }

    if (artifact.baseline_artifact_id === null) {
      ctx.addIssue({
        code: "custom",
        path: ["artifacts", index, "baseline_artifact_id"],
        message: "comparison summaries require a baseline artifact",
      });
    }
    if (artifact.candidate_artifact_id === null) {
      ctx.addIssue({
        code: "custom",
        path: ["artifacts", index, "candidate_artifact_id"],
        message: "comparison summaries require a candidate artifact",
      });
    }
    if (
      artifact.baseline_artifact_id !== null &&
      artifact.baseline_artifact_id === artifact.candidate_artifact_id
    ) {
      ctx.addIssue({
        code: "custom",
        path: ["artifacts", index],
        message: "comparisons cannot compare an artifact with itself",
      });
    }
    for (const [field, referenceId] of [
      ["baseline_artifact_id", artifact.baseline_artifact_id],
      ["candidate_artifact_id", artifact.candidate_artifact_id],
    ] as const) {
      if (referenceId === null) continue;
      const referencedIndex = artifactIndexes.get(referenceId);
      const referenced = referencedIndex === undefined ? undefined : value.artifacts[referencedIndex];
      if (!referenced || referenced.artifact_type !== "run") {
        ctx.addIssue({
          code: "custom",
          path: ["artifacts", index, field],
          message: "comparison references must target a run in the same index",
        });
      }
    }
  });
}

export const PublicEvidenceIndexSchema = z
  .object({
    schema_version: z.literal("public-evidence-v1"),
    artifact_id: z.literal("public-evidence-index-v1"),
    artifact_type: z.literal("index"),
    catalog_status: z.literal("EXPLICIT_ALLOWLIST"),
    artifacts: z.array(PublicArtifactSummarySchema),
  })
  .strict()
  .superRefine(validateIndexIntegrity);

export type PublicRunArtifact = z.infer<typeof PublicRunArtifactSchema>;
export type PublicComparisonArtifact = z.infer<typeof PublicComparisonArtifactSchema>;
export type PublicArtifactSummary = z.infer<typeof PublicArtifactSummarySchema>;
export type PublicEvidenceIndex = z.infer<typeof PublicEvidenceIndexSchema>;

export type PublicClaimArtifact = PublicRunArtifact | PublicComparisonArtifact | PublicArtifactSummary;

export class EvidenceContractError extends Error {
  constructor(message = "Evidence unavailable") {
    super(message);
    this.name = "EvidenceContractError";
  }
}

export function parsePublicEvidenceIndex(value: unknown): PublicEvidenceIndex {
  const result = PublicEvidenceIndexSchema.safeParse(value);
  if (!result.success) throw new EvidenceContractError("Evidence unavailable");
  return result.data;
}

export function parsePublicRunArtifact(value: unknown): PublicRunArtifact {
  const result = PublicRunArtifactSchema.safeParse(value);
  if (!result.success) throw new EvidenceContractError("Evidence unavailable");
  return result.data;
}

export function parsePublicComparisonArtifact(value: unknown): PublicComparisonArtifact {
  const result = PublicComparisonArtifactSchema.safeParse(value);
  if (!result.success) throw new EvidenceContractError("Evidence unavailable");
  return result.data;
}
