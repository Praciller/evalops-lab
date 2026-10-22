import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import * as api from "../api/client";
import WorkspaceInputs from "./WorkspaceInputs";
import WorkspaceRuns from "./WorkspaceRuns";
import RunResult from "./RunResult";

vi.mock("../api/client", () => ({
  listInputs: vi.fn(),
  uploadInput: vi.fn(),
  referenceInput: vi.fn(),
  uploadCsv: vi.fn(),
  listRuns: vi.fn(),
  validatePair: vi.fn(),
  createRun: vi.fn(),
  getRun: vi.fn(),
}));

const ground = {
  input_id: "input-a",
  kind: "retrieval_ground_truth" as const,
  source_mode: "imported" as const,
  content_sha256: "a".repeat(64),
  record_count: 2,
  created_at: "2026-10-01T00:00:00Z",
};
const prediction = {
  ...ground,
  input_id: "input-b",
  kind: "retrieval_predictions" as const,
  content_sha256: "b".repeat(64),
};

function mount(path: string, element: React.ReactNode) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/workspaces/:workspaceId/inputs" element={element} />
        <Route path="/workspaces/:workspaceId/runs" element={element} />
        <Route path="/workspaces/:workspaceId/runs/:runId" element={element} />
        <Route path="/jobs/:jobId" element={<p>Arrived at job</p>} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.mocked(api.listInputs).mockResolvedValue([]);
  vi.mocked(api.listRuns).mockResolvedValue([]);
});
afterEach(() => vi.resetAllMocks());

describe("Guided input registration", () => {
  it("registers an explicit JSONL upload and shows validated SHA-256", async () => {
    vi.mocked(api.uploadInput).mockResolvedValue(ground);
    mount("/workspaces/ws-demo/inputs", <WorkspaceInputs />);
    await waitFor(() => expect(screen.getByText(/No inputs registered yet/i)).toBeInTheDocument());
    const file = new File(['{"query_id":"q1"}\n'], "truth.jsonl", { type: "application/json" });
    await userEvent.upload(screen.getByLabelText("JSONL file", { selector: 'input[type="file"]' }), file);
    fireEvent.click(screen.getByRole("button", { name: /Validate & register/i }));
    await waitFor(() => expect(api.uploadInput).toHaveBeenCalledWith(
      "ws-demo", "retrieval_ground_truth", file
    ));
    expect(await screen.findByText(/Registered 2 validated record/i)).toBeInTheDocument();
  });

  it("exposes only explicit local path entry; no directory browser", async () => {
    vi.mocked(api.referenceInput).mockResolvedValue(prediction);
    mount("/workspaces/ws-demo/inputs", <WorkspaceInputs />);
    fireEvent.click(screen.getByRole("radio", { name: /Local path/i }));
    fireEvent.change(screen.getByLabelText(/Absolute local JSONL path/i), {
      target: { value: "C:\\private\\reference.jsonl" },
    });
    fireEvent.change(screen.getByLabelText("Input role"), {
      target: { value: "retrieval_predictions" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Validate & register/i }));
    await waitFor(() => expect(api.referenceInput).toHaveBeenCalledWith(
      "ws-demo", "retrieval_predictions", "C:\\private\\reference.jsonl"
    ));
    expect(screen.queryByRole("button", { name: /Browse directory/i })).not.toBeInTheDocument();
  });

  it("asks only three mapping fields for CSV and sends the chosen columns", async () => {
    vi.mocked(api.uploadCsv).mockResolvedValue(ground);
    mount("/workspaces/ws-demo/inputs", <WorkspaceInputs />);
    fireEvent.click(screen.getByRole("radio", { name: /CSV mapping/i }));
    const file = new File(["query,docs\nq1,d1\n"], "truth.csv", { type: "text/csv" });
    await userEvent.upload(screen.getByLabelText("CSV file"), file);
    fireEvent.change(screen.getByLabelText("Query ID column"), {
      target: { value: "query" },
    });
    fireEvent.change(screen.getByLabelText("Document IDs column"), {
      target: { value: "docs" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Validate & register/i }));
    await waitFor(() => expect(api.uploadCsv).toHaveBeenCalledWith(
      "ws-demo", "retrieval_ground_truth", file, {
        query_id_column: "query",
        document_ids_column: "docs",
        document_ids_delimiter: "|",
      }
    ));
  });
});

describe("Constrained run review", () => {
  it("reopens persisted Job progress from the saved Runs list", async () => {
    vi.mocked(api.listRuns).mockResolvedValue([{
      run_id: "run-one", workspace_id: "ws-demo", run_name: "Pending evaluation",
      job_id: "job-one", ground_truth_input_id: ground.input_id,
      predictions_input_id: prediction.input_id,
      ground_truth_sha256: ground.content_sha256,
      predictions_sha256: prediction.content_sha256,
      evaluator_versions: { retrieval: "deterministic-v1" },
      top_k: 2, system_name: "local", dataset_name: "synthetic",
      dataset_version: "v1", created_at: "2026-10-01T00:00:00Z",
      metrics: null, failure_counts: null, result_sha256: null, evalops_version: null,
    }]);
    mount("/workspaces/ws-demo/runs", <WorkspaceRuns />);
    const link = await screen.findByRole("link", { name: "Job status" });
    expect(link).toHaveAttribute("href", "/jobs/job-one");
    fireEvent.click(link);
    expect(screen.getByText("Arrived at job")).toBeInTheDocument();
  });


  it("validates a real pair and reviews input digests before submitting", async () => {
    vi.mocked(api.listInputs).mockResolvedValue([ground, prediction]);
    vi.mocked(api.validatePair).mockResolvedValue({
      ground_truth_records: 2, prediction_records: 2, matching_query_count: 1,
      missing_prediction_count: 1, extra_prediction_count: 1,
      blocking_codes: [], warning_codes: ["MISSING_PREDICTIONS", "EXTRA_PREDICTIONS"],
    });
    vi.mocked(api.createRun).mockResolvedValue({
      run_id: "run-one", workspace_id: "ws-demo", run_name: "Retrieval evaluation",
      job_id: "job-one", ground_truth_input_id: ground.input_id,
      predictions_input_id: prediction.input_id,
      ground_truth_sha256: ground.content_sha256,
      predictions_sha256: prediction.content_sha256,
      evaluator_versions: { retrieval: "deterministic-v1" },
      top_k: 5, system_name: "local-retriever", dataset_name: "local-dataset",
      dataset_version: "v1", created_at: "2026-10-01T00:00:00Z",
      metrics: null, failure_counts: null, result_sha256: null, evalops_version: null,
    });
    mount("/workspaces/ws-demo/runs", <WorkspaceRuns />);
    await waitFor(() => expect(screen.getByText(/Evaluator contract/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Validate & review/i }));
    expect(await screen.findByText(/Warnings: MISSING_PREDICTIONS/i)).toBeInTheDocument();
    expect(screen.getByText(ground.content_sha256)).toBeInTheDocument();
    expect(screen.getByText(prediction.content_sha256)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Run Evaluation" }));
    expect(await screen.findByText("Arrived at job")).toBeInTheDocument();
    expect(api.createRun).toHaveBeenCalled();
  });

  it("does not permit execution when pair validation contains blockers", async () => {
    vi.mocked(api.listInputs).mockResolvedValue([ground, prediction]);
    vi.mocked(api.validatePair).mockResolvedValue({
      ground_truth_records: 0, prediction_records: 0, matching_query_count: 0,
      missing_prediction_count: 0, extra_prediction_count: 0,
      blocking_codes: ["INVALID_INPUT"], warning_codes: [],
    });
    mount("/workspaces/ws-demo/runs", <WorkspaceRuns />);
    await waitFor(() => expect(screen.getByRole("button", { name: /Validate & review/i })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /Validate & review/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("INVALID_INPUT");
    expect(screen.queryByRole("button", { name: "Run Evaluation" })).not.toBeInTheDocument();
  });
});

describe("Persisted result interpretation", () => {
  it("renders only actual metrics, counts and hashes with local evidence label", async () => {
    vi.mocked(api.getRun).mockResolvedValue({
      run_id: "run-one", workspace_id: "ws-demo", run_name: "Fixture eval",
      job_id: "job-one", ground_truth_input_id: ground.input_id,
      predictions_input_id: prediction.input_id,
      ground_truth_sha256: ground.content_sha256,
      predictions_sha256: prediction.content_sha256,
      evaluator_versions: { retrieval: "deterministic-v1" },
      top_k: 2, system_name: "BM25", dataset_name: "synthetic-local",
      dataset_version: "v1", created_at: "2026-10-01T00:00:00Z",
      metrics: { precision_at_2: 0.75, recall_at_2: 1, hit_rate_at_2: 1, mrr: 1, ndcg_at_2: 1 },
      failure_counts: { RETRIEVAL_MISS: 1 }, result_sha256: "c".repeat(64),
      evalops_version: "0.1.0",
    });
    mount("/workspaces/ws-demo/runs/run-one", <RunResult />);
    expect(await screen.findByText("Fixture eval")).toBeInTheDocument();
    expect(screen.getByText("LOCAL EVIDENCE — Not published")).toBeInTheDocument();
    expect(screen.getByText("Precision @2")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View job status" })).toHaveAttribute("href", "/jobs/job-one");
    expect(screen.getByText("RETRIEVAL_MISS")).toBeInTheDocument();
    expect(screen.getByText("c".repeat(64))).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/verified benchmark/i);
  });
});
