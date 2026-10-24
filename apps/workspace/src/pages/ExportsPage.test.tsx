import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import * as api from "../api/client";
import { ExportManifest, ExportPreview, RunSummary } from "../api/schemas";
import ExportsPage from "./ExportsPage";

vi.mock("../api/client", () => ({
  listRuns: vi.fn(),
  listComparisons: vi.fn(),
  listExports: vi.fn(),
  createExportPreview: vi.fn(),
  confirmExport: vi.fn(),
  WorkspaceApiError: class WorkspaceApiError extends Error {
    constructor(message: string, public code: string) { super(message); }
  },
}));

const WS = "ws-" + "1".repeat(32);
const RUN = "run-" + "a".repeat(32);
const SHA = "b".repeat(64);
const PREVIEW_ID = "preview-" + "c".repeat(32);
const complete: RunSummary = {
  run_id: RUN, workspace_id: WS, run_name: "Fixture run",
  ground_truth_input_id: "input-gt", predictions_input_id: "input-pred",
  ground_truth_sha256: SHA, predictions_sha256: SHA,
  evaluator_versions: { retrieval: "deterministic-v1" },
  top_k: 1, system_name: "local", dataset_name: "fixture",
  dataset_version: "v1", created_at: "2026-10-24T00:00:00Z",
  metrics: { mrr: 1 }, failure_counts: {},
  result_sha256: SHA, evalops_version: "0.1.0",
};
const preview: ExportPreview = {
  schema_version: "workspace-export-preview-v1",
  preview_id: PREVIEW_ID,
  source_type: "run",
  source_id: RUN,
  eligible: true,
  blocking_reasons: [],
  included: ["Public run metadata", "Aggregate evaluator metrics"],
  removed: ["Not in public contract: local paths and private logs"],
  transformed: ["Public model policy validated and canonically JSON serialized"],
  output_files: [{
    filename: "workspace-" + RUN + ".json",
    sha256: SHA,
    size_bytes: 128,
  }],
  classification: {
    verification_status: "UNVERIFIED", data_kind: "SYNTHETIC_FIXTURE",
    limitations: ["Local-only evidence; no independent benchmark verification"],
  },
  expires_at: "2026-10-24T00:15:00Z",
};
const manifest: ExportManifest = {
  schema_version: "workspace-export-manifest-v1",
  export_id: "export-" + "d".repeat(32),
  source_type: "run", source_id: RUN,
  destination: "C:\\selected\\workspace-" + RUN + ".json",
  files: preview.output_files,
  classification: preview.classification,
  created_at: "2026-10-24T00:10:00Z",
};

function mount() {
  return render(
    <MemoryRouter initialEntries={["/workspaces/" + WS + "/exports"]}>
      <Routes>
        <Route path="/workspaces/:workspaceId/exports" element={<ExportsPage />} />
      </Routes>
    </MemoryRouter>
  );
}

async function chooseRun() {
  await userEvent.selectOptions(await screen.findByLabelText("Source ID"), RUN);
}

beforeEach(() => {
  vi.mocked(api.listRuns).mockResolvedValue([complete]);
  vi.mocked(api.listComparisons).mockResolvedValue([]);
  vi.mocked(api.listExports).mockResolvedValue([]);
  vi.mocked(api.createExportPreview).mockResolvedValue(preview);
  vi.mocked(api.confirmExport).mockResolvedValue(manifest);
});
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

describe("explicit sanitized export UX", () => {
  it("hides all destination and write controls until policy preview is eligible", async () => {
    mount();
    expect(screen.queryByLabelText(/Destination directory/)).not.toBeInTheDocument();
    await chooseRun();
    await userEvent.click(screen.getByRole("button", { name: "Create sanitized preview" }));
    expect(await screen.findByRole("heading", { name: "Sanitized export preview" })).toBeInTheDocument();
    for (const heading of ["Included", "Removed", "Transformed", "Classification", "Output files"]) {
      expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
    }
    expect(screen.getByText("Public run metadata")).toBeInTheDocument();
    expect(screen.getByText(/local paths and private logs/)).toBeInTheDocument();
    expect(screen.getByText(/Public model policy validated/)).toBeInTheDocument();
    expect(screen.getByText(/SHA-256/)).toBeInTheDocument();

    const destination = screen.getByLabelText(/Destination directory/);
    expect(destination).toHaveValue("");
    const confirm = screen.getByRole("button", { name: /Confirm & write sanitized files/ });
    expect(confirm).toBeDisabled();
    await userEvent.type(destination, "C:\\selected");
    expect(confirm).toBeDisabled();
    await userEvent.click(screen.getByRole("checkbox"));
    expect(confirm).toBeEnabled();
    await userEvent.click(confirm);
    await waitFor(() => expect(api.confirmExport).toHaveBeenCalledWith(WS, PREVIEW_ID, "C:\\selected"));
    expect(screen.getByText("Local export completed")).toBeInTheDocument();
    expect(screen.getByText(/No GitHub Pages deployment occurred/)).toBeInTheDocument();
  });

  it("shows blocking reasons and never enables confirmation for exploratory evidence", async () => {
    vi.mocked(api.createExportPreview).mockResolvedValue({
      ...preview,
      eligible: false,
      blocking_reasons: ["NON_CANONICAL_COMPARISON"],
      included: [], transformed: [], output_files: [],
    });
    mount();
    await chooseRun();
    await userEvent.click(screen.getByRole("button", { name: "Create sanitized preview" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("NON_CANONICAL_COMPARISON");
    expect(screen.queryByLabelText(/Destination directory/)).not.toBeInTheDocument();
    expect(api.confirmExport).not.toHaveBeenCalled();
  });

  it("invalidates a prior preview whenever the owner changes classification", async () => {
    mount();
    await chooseRun();
    await userEvent.click(screen.getByRole("button", { name: "Create sanitized preview" }));
    expect(await screen.findByLabelText(/Destination directory/)).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Data kind"), "CURATED_DATASET");
    expect(screen.queryByLabelText(/Destination directory/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Create sanitized preview" }));
    await waitFor(() => expect(api.createExportPreview).toHaveBeenLastCalledWith(
      WS, expect.objectContaining({
        classification: expect.objectContaining({ data_kind: "CURATED_DATASET" }),
      })
    ));
  });

  it("failed server confirmation never presents false success", async () => {
    vi.mocked(api.confirmExport).mockRejectedValue(new api.WorkspaceApiError(
      "selected output already exists", "export_destination_exists", false
    ));
    mount();
    await chooseRun();
    await userEvent.click(screen.getByRole("button", { name: "Create sanitized preview" }));
    const directory = await screen.findByLabelText(/Destination directory/);
    await userEvent.type(directory, "/tmp/owner");
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: /Confirm & write sanitized files/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("selected output already exists");
    expect(screen.queryByText("Local export completed")).not.toBeInTheDocument();
  });
});
