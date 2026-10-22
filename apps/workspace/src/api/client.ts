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
