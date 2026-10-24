import { ReactNode } from "react";
import { Link, NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { WorkspaceSummary } from "./api/schemas";
import ComparisonDetail from "./pages/ComparisonDetail";
import ComparisonsPage from "./pages/ComparisonsPage";
import FailuresPage from "./pages/FailuresPage";
import JobProgress from "./pages/JobProgress";
import RunResult from "./pages/RunResult";
import WorkspaceInputs from "./pages/WorkspaceInputs";
import WorkspaceRuns from "./pages/WorkspaceRuns";

function PlannedSection({ title }: { title: string }) {
  return (
    <section className="surface">
      <p className="eyebrow">NOT AVAILABLE IN PHASE 6.3</p>
      <h2>{title}</h2>
      <p>This section is planned for Phase 6.4. No public evidence export is available here.</p>
      <Link className="text-link" to="/">Return to overview</Link>
    </section>
  );
}

type Props = { overview: ReactNode; workspaces: WorkspaceSummary[] };

export function WorkspaceRoutes({ overview, workspaces }: Props) {
  const location = useLocation();
  const activeWorkspace = location.pathname.match(/^\/workspaces\/([^/]+)\//)?.[1];
  const selectedWorkspace = activeWorkspace ?? workspaces[0]?.workspace_id;
  return (
    <>
      <nav className="workspace-nav" aria-label="Workspace navigation">
        <NavLink end to="/" className={({ isActive }) => isActive ? "active" : ""}>Overview</NavLink>
        {selectedWorkspace ? (
          <>
            <NavLink to={`/workspaces/${selectedWorkspace}/inputs`} className={({ isActive }) => isActive ? "active" : ""}>Inputs</NavLink>
            <NavLink end to={`/workspaces/${selectedWorkspace}/runs`} className={({ isActive }) => isActive ? "active" : ""}>Runs</NavLink>
            <NavLink to={`/workspaces/${selectedWorkspace}/comparisons`} className={({ isActive }) => isActive ? "active" : ""}>Comparisons</NavLink>
            <NavLink to={`/workspaces/${selectedWorkspace}/failures`} className={({ isActive }) => isActive ? "active" : ""}>Failures</NavLink>
          </>
        ) : (
          <>
            {(["Inputs", "Runs", "Comparisons", "Failures"] as const).map((title) => (
              <span key={title} aria-disabled="true">{title}</span>
            ))}
          </>
        )}
        <span aria-disabled="true" title="Evidence export is planned for Phase 6.4">Exports</span>
      </nav>
      <Routes>
        <Route path="/" element={overview} />
        <Route path="/workspaces/:workspaceId/inputs" element={<WorkspaceInputs />} />
        <Route path="/workspaces/:workspaceId/runs" element={<WorkspaceRuns />} />
        <Route path="/jobs/:jobId" element={<JobProgress />} />
        <Route path="/workspaces/:workspaceId/runs/:runId" element={<RunResult />} />
        <Route path="/workspaces/:workspaceId/comparisons" element={<ComparisonsPage />} />
        <Route path="/workspaces/:workspaceId/comparisons/:comparisonId" element={<ComparisonDetail />} />
        <Route path="/workspaces/:workspaceId/comparisons/:comparisonId/failures" element={<FailuresPage />} />
        <Route path="/workspaces/:workspaceId/failures" element={<FailuresPage />} />
        <Route path="/comparisons" element={selectedWorkspace ? (
          <Navigate to={`/workspaces/${selectedWorkspace}/comparisons`} replace />
        ) : <PlannedSection title="Comparisons" />} />
        <Route path="/failures" element={selectedWorkspace ? (
          <Navigate to={`/workspaces/${selectedWorkspace}/failures`} replace />
        ) : <PlannedSection title="Failures" />} />
        <Route path="/exports" element={<PlannedSection title="Exports" />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
}
