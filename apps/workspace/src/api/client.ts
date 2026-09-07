import {
  ErrorResponseSchema,
  SessionInfo,
  SessionInfoSchema,
  WorkspaceListResponse,
  WorkspaceListResponseSchema,
  WorkspaceSummary,
  WorkspaceSummarySchema,
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
