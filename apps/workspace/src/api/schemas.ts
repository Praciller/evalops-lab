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
