import {
  ErrorResponseSchema,
  SessionInfo,
  SessionInfoSchema,
  WorkspaceListResponse,
  WorkspaceListResponseSchema,
  WorkspaceSummary,
  WorkspaceSummarySchema,
  InputListSchema,
  InputSummarySchema,
  InputSummary,
  InputKind,
  PairValidationSchema,
  PairValidation,
  RunListSchema,
  RunSummarySchema,
  RunSummary,
  RunRequest,
  JobSummarySchema,
  JobSummary,
  BaselinePointer,
  BaselineResponseSchema,
  ComparisonMode,
  ComparisonCompatibility,
  ComparisonRecord,
  ComparisonRecordSchema,
  ComparisonListResponseSchema,
  ComparisonConflictResponseSchema,
  ComparisonFailuresResponse,
  ComparisonFailuresResponseSchema,
  FailureTransition,
} from "./schemas";

export class WorkspaceApiError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly retryable: boolean
  ) {
    super(message);
    this.name = "WorkspaceApiError";
  }
}

async function parseError(response: Response): Promise<WorkspaceApiError> {
  let code = "api_error";
  let message = `HTTP ${response.status}`;
  try {
    const body = await response.json();
    const parsed = ErrorResponseSchema.safeParse(body);
    if (parsed.success) {
      code = parsed.data.error.code;
      message = parsed.data.error.message;
      return new WorkspaceApiError(message, code, parsed.data.error.retryable);
    }
  } catch {
    // Use defaults
  }
  return new WorkspaceApiError(message, code, false);
}

export async function bootstrapSession(nonce: string): Promise<SessionInfo> {
  const response = await fetch("/api/v1/session/bootstrap", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ nonce }),
  });
  if (!response.ok) throw await parseError(response);
  const data = await response.json();
  return SessionInfoSchema.parse(data);
}

export async function getSession(): Promise<SessionInfo> {
  const response = await fetch("/api/v1/session", {
    credentials: "same-origin",
  });
  if (!response.ok) throw await parseError(response);
  const data = await response.json();
  return SessionInfoSchema.parse(data);
}

export async function listWorkspaces(): Promise<WorkspaceListResponse> {
  const response = await fetch("/api/v1/workspaces", {
    credentials: "same-origin",
  });
  if (!response.ok) throw await parseError(response);
  const data = await response.json();
  return WorkspaceListResponseSchema.parse(data);
}

export async function createWorkspace(
  displayName: string
): Promise<WorkspaceSummary> {
  const response = await fetch("/api/v1/workspaces", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ display_name: displayName }),
  });
  if (!response.ok) throw await parseError(response);
  const data = await response.json();
  return WorkspaceSummarySchema.parse(data);
}

export async function renameWorkspace(
  workspaceId: string,
  displayName: string
): Promise<WorkspaceSummary> {
  const response = await fetch(`/api/v1/workspaces/${workspaceId}`, {
    method: "PATCH",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ display_name: displayName }),
  });
  if (!response.ok) throw await parseError(response);
  const data = await response.json();
  return WorkspaceSummarySchema.parse(data);
}

async function typedJson<T>(
  path: string,
  schema: { parse(data: unknown): T },
  init: RequestInit = {}
): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: "same-origin",
  });
  if (!response.ok) throw await parseError(response);
  return schema.parse(await response.json());
}

function sendJson(payload: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  };
}

export async function listInputs(workspaceId: string): Promise<InputSummary[]> {
  const response = await typedJson(
    `/api/v1/workspaces/${workspaceId}/inputs`,
    InputListSchema
  );
  return response.inputs;
}

export async function uploadInput(
  workspaceId: string,
  kind: InputKind,
  file: File
): Promise<InputSummary> {
  const form = new FormData();
  form.append("kind", kind);
  form.append("file", file);
  return typedJson(
    `/api/v1/workspaces/${workspaceId}/inputs/upload`,
    InputSummarySchema,
    { method: "POST", body: form }
  );
}

export async function referenceInput(
  workspaceId: string,
  kind: InputKind,
  path: string
): Promise<InputSummary> {
  return typedJson(
    `/api/v1/workspaces/${workspaceId}/inputs/reference`,
    InputSummarySchema,
    sendJson({ kind, path })
  );
}

export async function uploadCsv(
  workspaceId: string,
  kind: InputKind,
  file: File,
  mapping: {
    query_id_column: string;
    document_ids_column: string;
    document_ids_delimiter: string;
  }
): Promise<InputSummary> {
  const form = new FormData();
  form.append("kind", kind);
  form.append("file", file);
  Object.entries(mapping).forEach(([key, value]) => form.append(key, value));
  return typedJson(
    `/api/v1/workspaces/${workspaceId}/inputs/csv`,
    InputSummarySchema,
    { method: "POST", body: form }
  );
}

export async function validatePair(
  workspaceId: string,
  groundTruthId: string,
  predictionsId: string
): Promise<PairValidation> {
  return typedJson(
    `/api/v1/workspaces/${workspaceId}/runs/validate`,
    PairValidationSchema,
    sendJson({
      ground_truth_input_id: groundTruthId,
      predictions_input_id: predictionsId,
    })
  );
}

export async function listRuns(workspaceId: string): Promise<RunSummary[]> {
  const data = await typedJson(
    `/api/v1/workspaces/${workspaceId}/runs`, RunListSchema
  );
  return data.runs;
}

export async function getRun(workspaceId: string, runId: string): Promise<RunSummary> {
  return typedJson(
    `/api/v1/workspaces/${workspaceId}/runs/${runId}`, RunSummarySchema
  );
}

export async function createRun(
  workspaceId: string,
  request: RunRequest
): Promise<RunSummary> {
  return typedJson(
    `/api/v1/workspaces/${workspaceId}/runs`,
    RunSummarySchema, sendJson(request)
  );
}

export async function getJob(jobId: string): Promise<JobSummary> {
  return typedJson(`/api/v1/jobs/${jobId}`, JobSummarySchema);
}

export async function cancelJob(jobId: string): Promise<JobSummary> {
  return typedJson(
    `/api/v1/jobs/${jobId}/cancel`, JobSummarySchema, { method: "POST" }
  );
}

export async function retryJob(jobId: string): Promise<JobSummary> {
  return typedJson(
    `/api/v1/jobs/${jobId}/retry`, JobSummarySchema, { method: "POST" }
  );
}


export class NonComparableError extends WorkspaceApiError {
  constructor(public readonly compatibility: ComparisonCompatibility) {
    super(
      "Canonical comparison requires compatible evaluation populations.",
      "non_comparable",
      false
    );
  }
}

export async function getBaseline(workspaceId: string): Promise<BaselinePointer | null> {
  const data = await typedJson(
    `/api/v1/workspaces/${workspaceId}/baseline`,
    BaselineResponseSchema
  );
  return data.baseline;
}

export async function setBaseline(
  workspaceId: string, runId: string, confirmReplace = false
): Promise<BaselinePointer | null> {
  const data = await typedJson(
    `/api/v1/workspaces/${workspaceId}/baseline`,
    BaselineResponseSchema,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id: runId, confirm_replace: confirmReplace }),
    }
  );
  return data.baseline;
}

export async function listComparisons(workspaceId: string): Promise<ComparisonRecord[]> {
  const data = await typedJson(
    `/api/v1/workspaces/${workspaceId}/comparisons`,
    ComparisonListResponseSchema
  );
  return data.comparisons;
}

export async function createComparison(
  workspaceId: string,
  candidateRunId: string,
  mode: ComparisonMode = "CANONICAL"
): Promise<ComparisonRecord> {
  const response = await fetch(`/api/v1/workspaces/${workspaceId}/comparisons`, {
    ...sendJson({ candidate_run_id: candidateRunId, mode }),
    credentials: "same-origin",
  });
  if (!response.ok) {
    if (response.status === 409) {
      const detail = ComparisonConflictResponseSchema.safeParse(
        await response.clone().json().catch(() => null)
      );
      if (detail.success && detail.data.error.code === "non_comparable") {
        throw new NonComparableError(detail.data.compatibility);
      }
    }
    throw await parseError(response);
  }
  return ComparisonRecordSchema.parse(await response.json());
}

export async function getComparison(
  workspaceId: string, comparisonId: string
): Promise<ComparisonRecord> {
  return typedJson(
    `/api/v1/workspaces/${workspaceId}/comparisons/${comparisonId}`,
    ComparisonRecordSchema
  );
}

export type FailureFilters = {
  transition?: FailureTransition;
  category?: string;
  queryId?: string;
  exact?: boolean;
};

export async function listComparisonFailures(
  workspaceId: string,
  comparisonId: string,
  filters: FailureFilters = {}
): Promise<ComparisonFailuresResponse> {
  const params = new URLSearchParams();
  if (filters.transition) params.set("transition", filters.transition);
  if (filters.category) params.set("category", filters.category);
  if (filters.queryId) {
    params.set("query_id", filters.queryId);
    params.set("exact", String(filters.exact ?? true));
  }
  const query = params.toString();
  return typedJson(
    `/api/v1/workspaces/${workspaceId}/comparisons/${comparisonId}/failures${query ? `?${query}` : ""}`,
    ComparisonFailuresResponseSchema
  );
}
