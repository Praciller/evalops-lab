import { ReactNode } from "react";
import { Link, NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { WorkspaceSummary } from "./api/schemas";
import JobProgress from "./pages/JobProgress";
import RunResult from "./pages/RunResult";
import WorkspaceInputs from "./pages/WorkspaceInputs";
import WorkspaceRuns from "./pages/WorkspaceRuns";

function PlannedSection({ title }: { title: string }) {
  return (
    <section className="surface">
      <p className="eyebrow">NOT AVAILABLE IN PHASE 6.2</p>
      <h2>{title}</h2>
      <p>This section is planned for a later phase. There are no fabricated results or actions here.</p>
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
          </>
        ) : (
          <><span aria-disabled="true">Inputs</span><span aria-disabled="true">Runs</span></>
        )}
        {(["Comparisons", "Failures", "Exports"] as const).map((title) => (
          <span key={title} aria-disabled="true" title="Not available in Phase 6.2">{title}</span>
        ))}
      </nav>
      <Routes>
        <Route path="/" element={overview} />
        <Route path="/workspaces/:workspaceId/inputs" element={<WorkspaceInputs />} />
        <Route path="/workspaces/:workspaceId/runs" element={<WorkspaceRuns />} />
        <Route path="/jobs/:jobId" element={<JobProgress />} />
        <Route path="/workspaces/:workspaceId/runs/:runId" element={<RunResult />} />
        <Route path="/comparisons" element={<PlannedSection title="Comparisons" />} />
        <Route path="/failures" element={<PlannedSection title="Failures" />} />
        <Route path="/exports" element={<PlannedSection title="Exports" />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
}
