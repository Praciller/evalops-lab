import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { cancelJob, getJob, retryJob } from "../api/client";
import { JobSummary, JobSummarySchema } from "../api/schemas";

const TERMINAL = new Set(["COMPLETE", "FAILED", "INTERRUPTED", "CANCELLED"]);
const PHASES = ["QUEUED", "VALIDATING", "EVALUATING", "ANALYZING", "WRITING_ARTIFACT", "COMPLETE"];

export default function JobProgress() {
  const { jobId = "" } = useParams();
  const navigate = useNavigate();
  const [job, setJob] = useState<JobSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const latest = await getJob(jobId);
      setJob((old) => old?.job_id === latest.job_id && old.revision > latest.revision ? old : latest);
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load job state.");
    }
  }, [jobId]);

  useEffect(() => {
    let live = true;
    void refresh();
    const stream = new EventSource(`/api/v1/jobs/${jobId}/events`, { withCredentials: true });
    stream.addEventListener("job", (event) => {
      if (!live) return;
      try {
        const parsed = JobSummarySchema.parse(JSON.parse((event as MessageEvent).data));
        setJob((old) => old?.job_id === parsed.job_id && old.revision > parsed.revision ? old : parsed);
        if (TERMINAL.has(parsed.state)) stream.close();
      } catch {
        setError("Job event validation failed. Refresh to reload persisted state.");
      }
    });
    stream.onerror = () => { if (live) void refresh(); };
    return () => { live = false; stream.close(); };
  }, [jobId, refresh]);

  async function cancel() {
    setBusy(true); setError(null);
    try {
      const updated = await cancelJob(jobId);
      setJob((old) => old?.job_id === updated.job_id && old.revision > updated.revision ? old : updated);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Cancellation failed.");
    } finally { setBusy(false); }
  }

  async function retry() {
    setBusy(true); setError(null);
    try {
      const newJob = await retryJob(jobId);
      navigate(`/jobs/${newJob.job_id}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Retry was rejected.");
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      <header className="page-heading">
        <p className="eyebrow">STEP 04 · JOB STATUS</p>
        <h2>Evaluation progress</h2>
        <p>Live updates from persisted local job revisions. Refreshing the page keeps your progress.</p>
      </header>
      <section className="surface">
        {!job && !error && <p role="status">Loading job status…</p>}
        {error && <p className="error-message" role="alert">{error}</p>}
        {job && (
          <>
            <div className="section-head">
              <div><strong>Job {job.job_id.slice(0, 18)}</strong><p className="small-meta">Revision {job.revision}</p></div>
              <strong aria-live="polite" className="status-text">{job.state}</strong>
            </div>
            <ol className="job-steps" aria-label="Evaluation phases">
              {PHASES.map((phase) => (
                <li key={phase} data-active={job.state === phase ? "true" : undefined}>
                  {phase.replaceAll("_", " ")}
                </li>
              ))}
            </ol>
            {job.cancel_requested && job.state !== "CANCELLED" && (
              <p className="warning-message" role="status">Cancellation requested. The worker will stop at the next safe boundary.</p>
            )}
            {job.safe_error && (
              <p className="error-message" role="alert">
                {job.safe_error.code}: {job.safe_error.message}
              </p>
            )}
            {job.state === "INTERRUPTED" && <p className="field-hint">The process restarted while work was active. Evaluation was not resumed automatically.</p>}
            {job.state === "COMPLETE" && (
              <div className="success-message" role="status">
                Evaluation complete · <strong>LOCAL EVIDENCE — Not published</strong>
              </div>
            )}
            <div className="action-row">
              {!TERMINAL.has(job.state) && (
                <button type="button" disabled={busy || job.cancel_requested} onClick={() => void cancel()}>
                  {job.cancel_requested ? "Cancel requested" : "Cancel run"}
                </button>
              )}
              {["FAILED", "INTERRUPTED", "CANCELLED"].includes(job.state) && (
                <button type="button" disabled={busy} onClick={() => void retry()}>Retry as new job</button>
              )}
              {job.state === "COMPLETE" && (
                <Link className="button-link" to={`/workspaces/${job.workspace_id}/runs/${job.run_id}`}>View evaluation result</Link>
              )}
              <button type="button" className="secondary-button" onClick={() => void refresh()}>Refresh status</button>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
