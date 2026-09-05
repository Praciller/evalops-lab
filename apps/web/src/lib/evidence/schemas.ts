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

const ClaimFields = {
  verification_status: z.enum(["VERIFIED", "PARTIAL", "UNVERIFIED", "NOT_RUN"]),
  data_kind: z.enum(["SYNTHETIC_FIXTURE", "CURATED_DATASET", "OFFICIAL_BENCHMARK"]),
  claim_scope: z.enum(["INTEGRATION_ONLY", "PROTOCOL_SPECIFIC", "BENCHMARK_RESULT"]),
  limitations: z.array(SafeText),
};

const SummaryClaimFields = {
  verification_status: ClaimFields.verification_status,
  data_kind: ClaimFields.data_kind,
  claim_scope: ClaimFields.claim_scope,
};

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
  .strict();

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
  .strict();

export const PublicEvidenceIndexSchema = z
  .object({
    schema_version: z.literal("public-evidence-v1"),
    artifact_id: z.literal("public-evidence-index-v1"),
    artifact_type: z.literal("index"),
    catalog_status: z.literal("EXPLICIT_ALLOWLIST"),
    artifacts: z.array(PublicArtifactSummarySchema),
  })
  .strict();

export type PublicRunArtifact = z.infer<typeof PublicRunArtifactSchema>;
export type PublicArtifactSummary = z.infer<typeof PublicArtifactSummarySchema>;
export type PublicEvidenceIndex = z.infer<typeof PublicEvidenceIndexSchema>;

export type PublicClaimArtifact = PublicRunArtifact | PublicArtifactSummary;

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
