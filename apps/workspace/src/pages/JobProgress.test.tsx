import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import * as api from "../api/client";
import JobProgress from "./JobProgress";

vi.mock("../api/client", () => ({
  getJob: vi.fn(),
  cancelJob: vi.fn(),
  retryJob: vi.fn(),
}));

const baseJob = {
  schema_version: "workspace-job-v1" as const,
  job_id: "job-synthetic",
  workspace_id: "ws-fixture",
  run_id: "run-synthetic",
  state: "COMPLETE" as const,
  revision: 5,
  cancel_requested: false,
  safe_error: null,
  created_at: "2026-10-01T00:00:00Z",
  updated_at: "2026-10-01T00:00:01Z",
};

class FakeEvents {
  static opened: FakeEvents[] = [];
  private listeners: Record<string, (event: MessageEvent) => void> = {};
  onerror: (() => void) | null = null;
  closed = false;
  constructor(public url: string) {
    FakeEvents.opened.push(this);
  }
  addEventListener(name: string, callback: EventListenerOrEventListenerObject) {
    this.listeners[name] = callback as (event: MessageEvent) => void;
  }
  emit(name: string, payload: object) {
    this.listeners[name]?.({ data: JSON.stringify(payload) } as MessageEvent);
  }
  close() { this.closed = true; }
}

function showJob() {
  return render(
    <MemoryRouter initialEntries={["/jobs/job-synthetic"]}>
      <Routes>
        <Route path="/jobs/:jobId" element={<JobProgress />} />
        <Route path="/workspaces/:workspaceId/runs/:runId" element={<p>Result route</p>} />
        <Route path="/" element={<p>Overview</p>} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.stubGlobal("EventSource", FakeEvents);
  FakeEvents.opened = [];
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.resetAllMocks();
});

describe("Job progress via persisted state and SSE", () => {
  it("does not overwrite a newer SSE revision with a delayed older REST response", async () => {
    let resolveGet!: (job: Awaited<ReturnType<typeof api.getJob>>) => void;
    vi.mocked(api.getJob).mockImplementationOnce(() => new Promise((resolve) => {
      resolveGet = resolve;
    }));
    showJob();
    await waitFor(() => expect(FakeEvents.opened).toHaveLength(1));
    const source = FakeEvents.opened[0];
    act(() => source.emit("job", { ...baseJob, state: "EVALUATING", revision: 3 }));
    expect(await screen.findByText("EVALUATING", { selector: ".status-text" })).toBeInTheDocument();
    await act(async () => { resolveGet({ ...baseJob, state: "QUEUED", revision: 0 }); });
    expect(screen.getByText("EVALUATING", { selector: ".status-text" })).toBeInTheDocument();
    act(() => source.emit("job", { ...baseJob, state: "VALIDATING", revision: 1 }));
    expect(screen.getByText("EVALUATING", { selector: ".status-text" })).toBeInTheDocument();
    act(() => source.emit("job", baseJob));
    expect(await screen.findByText("COMPLETE", { selector: ".status-text" })).toBeInTheDocument();
  });

  it("loads saved COMPLETE state and links only to local run result", async () => {
    vi.mocked(api.getJob).mockResolvedValue(baseJob);
    showJob();
    expect(await screen.findByText("COMPLETE", { selector: ".status-text" })).toBeInTheDocument();
    expect(screen.getByText(/LOCAL EVIDENCE — Not published/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("link", { name: "View evaluation result" }));
    expect(screen.getByText("Result route")).toBeInTheDocument();
    expect(api.getJob).toHaveBeenCalledWith("job-synthetic");
  });

  it("updates progress from safe SSE revision and closes on terminal", async () => {
    vi.mocked(api.getJob).mockResolvedValue({ ...baseJob, state: "QUEUED", revision: 0 });
    showJob();
    expect(await screen.findByText("QUEUED", { selector: ".status-text" })).toBeInTheDocument();
    expect(FakeEvents.opened).toHaveLength(1);
    act(() => FakeEvents.opened[0].emit("job", { ...baseJob, state: "EVALUATING", revision: 2 }));
    expect(await screen.findByText("EVALUATING", { selector: ".status-text" })).toBeInTheDocument();
    act(() => FakeEvents.opened[0].emit("job", baseJob));
    expect(await screen.findByText("COMPLETE", { selector: ".status-text" })).toBeInTheDocument();
    expect(FakeEvents.opened[0].closed).toBe(true);
  });

  it("requests persisted cooperative cancellation and shows safe feedback", async () => {
    const active = { ...baseJob, state: "EVALUATING" as const, revision: 2 };
    vi.mocked(api.getJob).mockResolvedValue(active);
    vi.mocked(api.cancelJob).mockResolvedValue({
      ...active, cancel_requested: true, revision: 3,
    });
    showJob();
    fireEvent.click(await screen.findByRole("button", { name: /Cancel run/i }));
    await waitFor(() => expect(api.cancelJob).toHaveBeenCalledWith("job-synthetic"));
    expect(await screen.findByText(/Cancellation requested/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel run" })).not.toBeInTheDocument();
  });

  it("allows failed jobs to retry with a new immutable job ID", async () => {
    vi.mocked(api.getJob).mockImplementation(async (id) => id === "job-retry" ? {
      ...baseJob, job_id: "job-retry", state: "QUEUED", revision: 0,
    } : {
      ...baseJob,
      state: "FAILED", revision: 3,
      safe_error: { code: "WORKER_ERROR", message: "job execution failed" },
    });
    vi.mocked(api.retryJob).mockResolvedValue({
      ...baseJob, job_id: "job-retry", state: "QUEUED", revision: 0,
    });
    showJob();
    expect(await screen.findByRole("alert")).toHaveTextContent("WORKER_ERROR");
    fireEvent.click(screen.getByRole("button", { name: /Retry as new job/i }));
    await waitFor(() => expect(api.retryJob).toHaveBeenCalledWith("job-synthetic"));
    expect(await screen.findByText("QUEUED", { selector: ".status-text" })).toBeInTheDocument();
  });
});
