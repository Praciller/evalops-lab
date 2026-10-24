import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import * as api from "../api/client";
import { ComparisonRecord, RunSummary } from "../api/schemas";
import ComparisonsPage from "./ComparisonsPage";
import FailuresPage from "./FailuresPage";
import RunResult from "./RunResult";

vi.mock("../api/client", () => ({
  getBaseline: vi.fn(),
  setBaseline: vi.fn(),
  getRun: vi.fn(),
  listRuns: vi.fn(),
  listComparisons: vi.fn(),
  createComparison: vi.fn(),
  getComparison: vi.fn(),
  listComparisonFailures: vi.fn(),
  NonComparableError: class NonComparableError extends Error {
    constructor(public readonly compatibility: unknown) {
      super("not comparable");
    }
  },
}));

const WS = `ws-${"1".repeat(32)}`;
const BASE = `run-${"a".repeat(32)}`;
const CAND = `run-${"b".repeat(32)}`;
const ID = `comparison-${"c".repeat(32)}`;
const HASH = "d".repeat(64);
const baseline = {
  run_id: BASE, result_sha256: HASH, pinned_at: "2026-10-24T00:00:00Z",
};
const complete: RunSummary = {
  run_id: CAND, workspace_id: WS, run_name: "Candidate",
  job_id: null, ground_truth_input_id: "input-a", predictions_input_id: "input-b",
  ground_truth_sha256: HASH, predictions_sha256: HASH,
  evaluator_versions: { retrieval: "deterministic-v1" },
  top_k: 2, system_name: "fixture", dataset_name: "synthetic",
  dataset_version: "v1", created_at: "2026-10-24T00:00:00Z",
  metrics: { mrr: 0 }, failure_counts: {},
  result_sha256: HASH, evalops_version: "0.1.0",
};
const record: ComparisonRecord = {
  schema_version: "workspace-comparison-v1",
  comparison_id: ID, workspace_id: WS, mode: "CANONICAL",
  compatibility: { status: "COMPARABLE", reasons: [] },
  baseline_run_id: BASE, baseline_result_sha256: HASH,
  candidate_run_id: CAND, candidate_result_sha256: HASH,
  policy_version: "workspace-retrieval-regression-v1",
  regression_report: { passed: false, comparisons: [] },
  created_at: "2026-10-24T00:00:00Z",
};

function mount(path: string, component: React.ReactNode) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/workspaces/:workspaceId/comparisons" element={component} />
        <Route path="/workspaces/:workspaceId/comparisons/:comparisonId" element={<p>Comparison detail route</p>} />
        <Route path="/workspaces/:workspaceId/comparisons/:comparisonId/failures" element={component} />
        <Route path="/workspaces/:workspaceId/runs/:runId" element={component} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.mocked(api.getBaseline).mockResolvedValue(null);
  vi.mocked(api.listRuns).mockResolvedValue([]);
  vi.mocked(api.listComparisons).mockResolvedValue([]);
});
afterEach(() => { cleanup(); vi.resetAllMocks(); vi.unstubAllGlobals(); });

describe("comparison UX is compatibility-first", () => {
  it("keeps canonical creation blocked and requires a distinct explicit exploratory action", async () => {
    const compatibility = {
      status: "NON_COMPARABLE" as const,
      reasons: [{ field: "top_k", baseline: "1", candidate: "2" }],
    };
    vi.mocked(api.getBaseline).mockResolvedValue(baseline);
    vi.mocked(api.listRuns).mockResolvedValue([complete]);
    vi.mocked(api.getRun).mockResolvedValue(complete);
    vi.mocked(api.createComparison)
      .mockRejectedValueOnce(new api.NonComparableError(compatibility))
      .mockResolvedValueOnce({ ...record, mode: "EXPLORATORY_ONLY", compatibility });
    vi.stubGlobal("confirm", vi.fn(() => true));

    mount(`/workspaces/${WS}/comparisons`, <ComparisonsPage />);
    const picker = await screen.findByLabelText("Completed candidate run");
    await userEvent.selectOptions(picker, CAND);
    await userEvent.click(screen.getByRole("button", { name: /Check & create canonical comparison/i }));
    expect(await screen.findByText(/Not comparable — canonical regression blocked/)).toBeInTheDocument();
    expect(screen.getByText(/top_k/)).toBeInTheDocument();
    expect(api.createComparison).toHaveBeenCalledWith(WS, CAND, "CANONICAL");
    expect(api.createComparison).toHaveBeenCalledTimes(1);

    await userEvent.click(screen.getByRole("button", { name: /Create separate exploratory comparison/ }));
    await waitFor(() => expect(api.createComparison).toHaveBeenCalledWith(
      WS, CAND, "EXPLORATORY_ONLY"
    ));
    expect(window.confirm).toHaveBeenCalled();
  });

  it("requires explicit confirmation before repinning and leaves historical comparisons untouched", async () => {
    vi.mocked(api.getRun).mockResolvedValue(complete);
    vi.mocked(api.getBaseline).mockResolvedValue(baseline);
    vi.mocked(api.setBaseline).mockResolvedValue({
      run_id: CAND, result_sha256: HASH, pinned_at: "2026-10-24T01:00:00Z",
    });
    const confirm = vi.fn(() => false);
    vi.stubGlobal("confirm", confirm);
    mount(`/workspaces/${WS}/runs/${CAND}`, <RunResult />);
    const action = await screen.findByRole("button", { name: "Replace baseline with this run" });
    await userEvent.click(action);
    expect(api.setBaseline).not.toHaveBeenCalled();
    confirm.mockReturnValue(true);
    await userEvent.click(action);
    await waitFor(() => expect(api.setBaseline).toHaveBeenCalledWith(WS, CAND, true));
    expect(await screen.findByText(/Existing comparisons remain immutable/)).toBeInTheDocument();
  });
});

describe("private Failure Explorer", () => {
  it("queries only allowlisted transitions and shows evaluator-produced query evidence", async () => {
    vi.mocked(api.getComparison).mockResolvedValue(record);
    vi.mocked(api.listComparisonFailures).mockResolvedValue({
      comparison_id: ID, total_count: 1,
      transitions: [{
        query_id: "q1", transition: "REGRESSED",
        baseline_category: "PASS", candidate_category: "RETRIEVAL_MISS",
        baseline_metrics: { mrr: 1 }, candidate_metrics: { mrr: 0 },
      }],
    });
    mount(`/workspaces/${WS}/comparisons/${ID}/failures`, <FailuresPage />);
    expect(await screen.findByText("q1")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Transition"), "REGRESSED");
    fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));
    await waitFor(() => expect(api.listComparisonFailures).toHaveBeenLastCalledWith(
      WS, ID, expect.objectContaining({ transition: "REGRESSED" })
    ));
    expect(screen.getByRole("cell", { name: "RETRIEVAL_MISS" })).toBeInTheDocument();
    expect(screen.queryByText("Public verified evidence")).not.toBeInTheDocument();
  });

  it("never represents unavailable per-query transitions as an empty result", async () => {
    vi.mocked(api.getComparison).mockResolvedValue({
      ...record, mode: "EXPLORATORY_ONLY",
      compatibility: { status: "NON_COMPARABLE", reasons: [] },
    });
    vi.mocked(api.listComparisonFailures).mockRejectedValue(
      new Error("per-query comparison transitions are unavailable for these operands")
    );
    mount(`/workspaces/${WS}/comparisons/${ID}/failures`, <FailuresPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("unavailable");
    expect(screen.getByText(/EXPLORATORY_ONLY — Not eligible for public regression claim/)).toBeInTheDocument();
    expect(screen.queryByText(/No transitions match these filters/)).not.toBeInTheDocument();
  });
});
