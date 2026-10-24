import { z } from "zod";

export const SessionInfoSchema = z.object({
  authenticated: z.boolean(),
});
export type SessionInfo = z.infer<typeof SessionInfoSchema>;

export const WorkspaceSummarySchema = z.object({
  schema_version: z.string(),
  workspace_id: z.string(),
  display_name: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type WorkspaceSummary = z.infer<typeof WorkspaceSummarySchema>;

export const WorkspaceListResponseSchema = z.object({
  workspaces: z.array(WorkspaceSummarySchema),
});
export type WorkspaceListResponse = z.infer<typeof WorkspaceListResponseSchema>;

export const ErrorDetailSchema = z.object({
  code: z.string(),
  message: z.string(),
  field: z.string().nullable(),
  retryable: z.boolean(),
});

export const ErrorResponseSchema = z.object({
  error: ErrorDetailSchema,
});
export type ErrorDetail = z.infer<typeof ErrorDetailSchema>;

const InputKindSchema = z.enum(["retrieval_ground_truth", "retrieval_predictions"]);
export type InputKind = z.infer<typeof InputKindSchema>;

export const InputSummarySchema = z.object({
  input_id: z.string(),
  kind: InputKindSchema,
  source_mode: z.enum(["imported", "referenced"]),
  content_sha256: z.string(),
  record_count: z.number().int(),
  created_at: z.string(),
}).strict();
export type InputSummary = z.infer<typeof InputSummarySchema>;
export const InputListSchema = z.object({ inputs: z.array(InputSummarySchema) }).strict();

export const PairValidationSchema = z.object({
  ground_truth_records: z.number().int(),
  prediction_records: z.number().int(),
  matching_query_count: z.number().int(),
  missing_prediction_count: z.number().int(),
  extra_prediction_count: z.number().int(),
  blocking_codes: z.array(z.string()),
  warning_codes: z.array(z.string()),
}).strict();
export type PairValidation = z.infer<typeof PairValidationSchema>;

export const RunSummarySchema = z.object({
  run_id: z.string(),
  workspace_id: z.string(),
  run_name: z.string(),
  job_id: z.string().nullable().optional(),
  ground_truth_input_id: z.string(),
  predictions_input_id: z.string(),
  ground_truth_sha256: z.string(),
  predictions_sha256: z.string(),
  evaluator_versions: z.record(z.string(), z.string()),
  top_k: z.number().int(),
  system_name: z.string(),
  dataset_name: z.string(),
  dataset_version: z.string(),
  created_at: z.string(),
  metrics: z.record(z.string(), z.number()).nullable(),
  failure_counts: z.record(z.string(), z.number()).nullable(),
  result_sha256: z.string().nullable(),
  evalops_version: z.string().nullable(),
}).strict();
export type RunSummary = z.infer<typeof RunSummarySchema>;
export const RunListSchema = z.object({ runs: z.array(RunSummarySchema) }).strict();

export const JobSummarySchema = z.object({
  schema_version: z.string(),
  job_id: z.string(),
  workspace_id: z.string(),
  run_id: z.string(),
  state: z.enum([
    "QUEUED", "VALIDATING", "EVALUATING", "ANALYZING",
    "WRITING_ARTIFACT", "COMPLETE", "FAILED", "CANCELLED", "INTERRUPTED",
  ]),
  revision: z.number().int().nonnegative(),
  cancel_requested: z.boolean(),
  safe_error: z.object({ code: z.string(), message: z.string() }).strict().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
}).strict();
export type JobSummary = z.infer<typeof JobSummarySchema>;

export type RunRequest = {
  run_name: string;
  ground_truth_input_id: string;
  predictions_input_id: string;
  top_k: number;
  system_name: string;
  dataset_name: string;
  dataset_version: string;
};
// Phase 6.3 — private Workspace comparison contracts (not public evidence).
export const BaselinePointerSchema = z.object({
  run_id: z.string().regex(/^run-[0-9a-f]{32}$/),
  result_sha256: z.string().regex(/^[0-9a-f]{64}$/),
  pinned_at: z.string(),
}).strict();
export type BaselinePointer = z.infer<typeof BaselinePointerSchema>;
export const BaselineResponseSchema = z.object({
  baseline: BaselinePointerSchema.nullable(),
}).strict();

export const ComparisonModeSchema = z.enum(["CANONICAL", "EXPLORATORY_ONLY"]);
export type ComparisonMode = z.infer<typeof ComparisonModeSchema>;
export const ComparisonCompatibilitySchema = z.object({
  status: z.enum(["COMPARABLE", "NON_COMPARABLE"]),
  reasons: z.array(z.object({
    field: z.string(),
    baseline: z.string(),
    candidate: z.string(),
  }).strict()),
}).strict();
export type ComparisonCompatibility = z.infer<typeof ComparisonCompatibilitySchema>;
export const MetricComparisonSchema = z.object({
  metric_name: z.string(),
  direction: z.enum(["higher_is_better", "lower_is_better"]),
  baseline: z.number().nullable(),
  current: z.number().nullable(),
  delta: z.number().nullable(),
  status: z.enum(["PASS", "REGRESSION", "MISSING"]),
  reason: z.string(),
}).strict();
export const ComparisonRecordSchema = z.object({
  schema_version: z.literal("workspace-comparison-v1"),
  comparison_id: z.string().regex(/^comparison-[0-9a-f]{32}$/),
  workspace_id: z.string().regex(/^ws-[0-9a-f]{32}$/),
  mode: ComparisonModeSchema,
  compatibility: ComparisonCompatibilitySchema,
  baseline_run_id: z.string(),
  baseline_result_sha256: z.string(),
  candidate_run_id: z.string(),
  candidate_result_sha256: z.string(),
  policy_version: z.literal("workspace-retrieval-regression-v1"),
  regression_report: z.object({
    passed: z.boolean(),
    comparisons: z.array(MetricComparisonSchema),
  }).strict(),
  created_at: z.string(),
}).strict();
export type ComparisonRecord = z.infer<typeof ComparisonRecordSchema>;
export const ComparisonListResponseSchema = z.object({
  comparisons: z.array(ComparisonRecordSchema),
}).strict();
export const ComparisonConflictResponseSchema = z.object({
  error: ErrorDetailSchema,
  compatibility: ComparisonCompatibilitySchema,
}).strict();

export const FailureTransitionSchema = z.enum([
  "UNCHANGED_PASS",
  "REGRESSED",
  "IMPROVED",
  "PERSISTENT_FAILURE",
  "CHANGED_FAILURE",
]);
export type FailureTransition = z.infer<typeof FailureTransitionSchema>;
export const QueryFailureTransitionSchema = z.object({
  query_id: z.string(),
  transition: FailureTransitionSchema,
  baseline_category: z.string(),
  candidate_category: z.string(),
  baseline_metrics: z.record(z.string(), z.number()),
  candidate_metrics: z.record(z.string(), z.number()),
}).strict();
export const ComparisonFailuresResponseSchema = z.object({
  comparison_id: z.string(),
  total_count: z.number().int().nonnegative(),
  transitions: z.array(QueryFailureTransitionSchema),
}).strict();
export type ComparisonFailuresResponse = z.infer<typeof ComparisonFailuresResponseSchema>;
