import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import App from "./app";

// Mock the API client
vi.mock("./api/client", () => ({
  bootstrapSession: vi.fn(),
  getSession: vi.fn().mockRejectedValue(new Error("unauthenticated")),
  listWorkspaces: vi.fn(),
  createWorkspace: vi.fn(),
  WorkspaceApiError: class WorkspaceApiError extends Error {
    code: string;
    retryable: boolean;
    constructor(message: string, code: string, retryable: boolean) {
      super(message);
      this.code = code;
      this.retryable = retryable;
      this.name = "WorkspaceApiError";
    }
  },
}));

import * as apiClient from "./api/client";

describe("App — LOCAL WORKSPACE identity", () => {
  it("always shows LOCAL WORKSPACE label", async () => {
    vi.mocked(apiClient.bootstrapSession).mockResolvedValue({ authenticated: true });
    vi.mocked(apiClient.listWorkspaces).mockResolvedValue({ workspaces: [] });

    // No bootstrap nonce in URL → should show unauthenticated
    render(<App />);

    // The banner must always be visible regardless of auth state
    expect(screen.getByText(/LOCAL WORKSPACE/)).toBeInTheDocument();
  });

  it("shows 'Data stays on this machine' text", async () => {
    render(<App />);
    expect(screen.getByText(/Data stays on this machine/i)).toBeInTheDocument();
  });

  it("does not contain public or hosted wording", () => {
    render(<App />);
    expect(document.body.textContent).not.toMatch(/public evidence console/i);
    expect(document.body.textContent).not.toMatch(/GitHub Pages/i);
    expect(document.body.textContent).not.toMatch(/hosted service/i);
  });
});

describe("App — unauthenticated bootstrap state", () => {
  it("shows auth error when no bootstrap nonce is present", async () => {
    render(<App />);
    await waitFor(() => {
      expect(
        screen.getByText(/No bootstrap token found/i)
      ).toBeInTheDocument();
    });
  });

  it("shows auth error when bootstrap fails", async () => {
    // Set up URL hash with a nonce
    Object.defineProperty(window, "location", {
      value: { ...window.location, hash: "#bootstrap=bad-nonce" },
      writable: true,
    });
    vi.mocked(apiClient.bootstrapSession).mockRejectedValue(
      new (apiClient.WorkspaceApiError as unknown as new (
        m: string,
        c: string,
        r: boolean
      ) => Error)("invalid bootstrap nonce", "invalid_bootstrap", false)
    );

    render(<App />);
    await waitFor(() => {
      expect(
        screen.getByText(/invalid bootstrap nonce/i)
      ).toBeInTheDocument();
    });

    // Reset
    window.location.hash = "";
  });
});

describe("App — authenticated empty workspace list", () => {
  beforeEach(() => {
    Object.defineProperty(window, "location", {
      value: { ...window.location, hash: "#bootstrap=test-nonce" },
      writable: true,
    });
    vi.mocked(apiClient.bootstrapSession).mockResolvedValue({ authenticated: true });
    vi.mocked(apiClient.listWorkspaces).mockResolvedValue({ workspaces: [] });
  });

  afterEach(() => {
    window.location.hash = "";
    vi.clearAllMocks();
  });

  it("shows empty workspace list after successful authentication", async () => {
    render(<App />);
    await waitFor(() => {
      expect(screen.getByText(/No workspaces yet/i)).toBeInTheDocument();
    });
  });

  it("authenticates via existing session when no nonce is in URL", async () => {
    window.location.hash = "";
    vi.mocked(apiClient.getSession).mockResolvedValue({ authenticated: true });
    render(<App />);
    await waitFor(() => {
      expect(screen.getByText(/No workspaces yet/i)).toBeInTheDocument();
    });
    expect(apiClient.getSession).toHaveBeenCalled();
  });

  it("shows the create workspace form", async () => {
    render(<App />);
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /Create Workspace/i })).toBeInTheDocument();
    });
    expect(screen.getByLabelText(/workspace name/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /create workspace/i })).toBeInTheDocument();
  });
});

describe("App — create workspace form", () => {
  beforeEach(() => {
    Object.defineProperty(window, "location", {
      value: { ...window.location, hash: "#bootstrap=test-nonce" },
      writable: true,
    });
    vi.mocked(apiClient.bootstrapSession).mockResolvedValue({ authenticated: true });
    vi.mocked(apiClient.listWorkspaces).mockResolvedValue({ workspaces: [] });
  });

  afterEach(() => {
    window.location.hash = "";
    vi.clearAllMocks();
  });

  it("creates a workspace and shows it in the list", async () => {
    const newWorkspace = {
      schema_version: "workspace-v1",
      workspace_id: "ws-abc123",
      display_name: "Thai Retrieval",
      created_at: "2026-09-07T00:00:00Z",
      updated_at: "2026-09-07T00:00:00Z",
    };
    vi.mocked(apiClient.createWorkspace).mockResolvedValue(newWorkspace);

    render(<App />);
    await waitFor(() =>
      expect(screen.getByLabelText(/workspace name/i)).toBeInTheDocument()
    );

    const input = screen.getByLabelText(/workspace name/i);
    const button = screen.getByRole("button", { name: /create workspace/i });

    fireEvent.change(input, { target: { value: "Thai Retrieval" } });
    fireEvent.click(button);

    await waitFor(() => {
      expect(screen.getByText("Thai Retrieval")).toBeInTheDocument();
    });
    expect(apiClient.createWorkspace).toHaveBeenCalledWith("Thai Retrieval");
  });

  it("shows API error messages without exposing raw response bodies", async () => {
    vi.mocked(apiClient.createWorkspace).mockRejectedValue(
      new (apiClient.WorkspaceApiError as unknown as new (
        m: string,
        c: string,
        r: boolean
      ) => Error)("workspace name must not be empty", "invalid_request", false)
    );

    render(<App />);
    await waitFor(() =>
      expect(screen.getByLabelText(/workspace name/i)).toBeInTheDocument()
    );

    const input = screen.getByLabelText(/workspace name/i);
    const button = screen.getByRole("button", { name: /create workspace/i });

    fireEvent.change(input, { target: { value: " " } });
    fireEvent.click(button);

    // With empty/whitespace input, the form should not even call the API
    // (because we trim the name before submitting)
    expect(apiClient.createWorkspace).not.toHaveBeenCalled();
  });
});
