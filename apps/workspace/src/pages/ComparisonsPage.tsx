import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  createComparison, getBaseline, getRun, listComparisons, listRuns, NonComparableError,
} from "../api/client";
import { BaselinePointer, ComparisonCompatibility, ComparisonRecord, RunSummary } from "../api/schemas";

export default function ComparisonsPage() {
  const { workspaceId = "" } = useParams();
  const navigate = useNavigate();
  const [baseline, setBaseline] = useState<BaselinePointer | null>(null);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [records, setRecords] = useState<ComparisonRecord[]>([]);
  const [candidateRunId, setCandidateRunId] = useState("");
  const [blocked, setBlocked] = useState<ComparisonCompatibility | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    Promise.all([getBaseline(workspaceId), listRuns(workspaceId), listComparisons(workspaceId)])
      .then(async ([pointer, snapshots, history]) => {
        const complete = await Promise.all(snapshots.map(async (run) => {
          try {
            const detail = await getRun(workspaceId, run.run_id);
            return detail.result_sha256 ? detail : null;
          } catch {
            return null; // Incomplete or corrupted local evidence is never selectable.
          }
        }));
        if (!active) return;
        setBaseline(pointer);
        setRuns(complete.filter((run): run is RunSummary => run !== null));
        setRecords(history);
        setLoading(false);
      })
      .catch(() => {
        if (!active) return;
        setError("Could not load verified local comparison metadata.");
        setLoading(false);
      });
    return () => { active = false; };
  }, [workspaceId]);

  async function create(mode: "CANONICAL" | "EXPLORATORY_ONLY") {
    if (!baseline || !candidateRunId || candidateRunId === baseline.run_id) return;
    if (mode === "EXPLORATORY_ONLY" && !window.confirm(
      "This exploratory comparison is permanently ineligible for a public regression claim. Continue?"
    )) return;
    setSaving(true);
    setError(null);
    if (mode === "CANONICAL") setBlocked(null);
    try {
      const result = await createComparison(workspaceId, candidateRunId, mode);
      navigate(`/workspaces/${workspaceId}/comparisons/${result.comparison_id}`);
    } catch (reason) {
      if (reason instanceof NonComparableError) {
        setBlocked(reason.compatibility);
        setError("Canonical comparison blocked: evaluation populations are incompatible.");
      } else {
        setError(reason instanceof Error ? reason.message : "Could not create a comparison.");
      }
    } finally {
      setSaving(false);
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void create("CANONICAL");
  }

  return (
    <div className="stack">
      <header className="page-heading">
        <p className="eyebrow">PHASE 6.3 · PRIVATE REGRESSION</p>
        <h2>Compare retrieval runs</h2>
        <p>Choose an explicit pinned baseline. Compatibility is checked before regression metrics.</p>
      </header>
      {loading && <p role="status">Loading verified local runs and comparisons…</p>}
      {error && <p className="error-message" role="alert">{error}</p>}

      {!loading && (
        <>
          <section className="surface" aria-labelledby="baseline-heading">
            <div className="section-head">
              <h3 id="baseline-heading">Pinned workspace baseline</h3>
              <span className="local-evidence">LOCAL EVIDENCE — Not published</span>
            </div>
            {baseline ? (
              <dl className="hash-summary">
                <dt>Run</dt>
                <dd><Link to={`/workspaces/${workspaceId}/runs/${baseline.run_id}`}>{baseline.run_id}</Link></dd>
                <dt>Result SHA-256</dt><dd><code>{baseline.result_sha256}</code></dd>
                <dt>Pinned</dt><dd>{new Date(baseline.pinned_at).toLocaleString()}</dd>
              </dl>
            ) : <p className="empty-state">
              No baseline is pinned. Open a completed <Link to={`/workspaces/${workspaceId}/runs`}>run</Link> and select “Set as baseline”.
            </p>}
            <p className="field-hint">Changing the pinned baseline never changes existing comparison records.</p>
          </section>

          <section className="surface" aria-labelledby="create-comparison-heading">
            <h3 id="create-comparison-heading">Create comparison</h3>
            <form className="stack" onSubmit={submit}>
              <div className="field">
                <label htmlFor="comparison-candidate">Completed candidate run</label>
                <select id="comparison-candidate" value={candidateRunId}
                  onChange={(event) => { setCandidateRunId(event.target.value); setBlocked(null); setError(null); }}
                  disabled={!baseline || saving}>
                  <option value="">Select a completed run</option>
                  {runs.filter((run) => run.run_id !== baseline?.run_id).map((run) => (
                    <option value={run.run_id} key={run.run_id}>
                      {run.run_name} · K={run.top_k} · {run.run_id.slice(0, 16)}
                    </option>
                  ))}
                </select>
                <p className="field-hint">Only completed, verified run evidence can be selected.</p>
              </div>
              <div className="readonly-contract">
                <strong>Fixed policy: workspace-retrieval-regression-v1</strong>
                <p>Five retrieval metrics · higher is better · no unacknowledged degradation · server-owned rules</p>
              </div>
              <div className="action-row">
                <button type="submit" disabled={!baseline || !candidateRunId || saving}>
                  {saving ? "Checking compatibility…" : "Check & create canonical comparison"}
                </button>
              </div>
            </form>
            {blocked && (
              <div className="compatibility-panel" role="status">
                <h4>Not comparable — canonical regression blocked</h4>
                <ul>{blocked.reasons.map((reason) => (
                  <li key={reason.field}>
                    <strong>{reason.field}</strong>: baseline {reason.baseline}, candidate {reason.candidate}
                  </li>
                ))}</ul>
                <p className="field-hint">This block cannot be dismissed. Exploratory results cannot become public regression evidence.</p>
                <button type="button" className="secondary-button"
                  disabled={saving} onClick={() => void create("EXPLORATORY_ONLY")}>
                  {saving ? "Creating…" : "Create separate exploratory comparison"}
                </button>
              </div>
            )}
          </section>

          <section className="surface" aria-labelledby="comparison-history-heading">
            <h3 id="comparison-history-heading">Saved comparisons</h3>
            {records.length === 0 ? (
              <p className="empty-state">No persisted comparisons yet.</p>
            ) : (
              <ul className="input-list">
                {records.map((record) => (
                  <li key={record.comparison_id}>
                    <div>
                      <strong>{record.mode === "CANONICAL" ? "Canonical" : "EXPLORATORY_ONLY — Not publishable"}</strong>
                      <p className="small-meta">{record.compatibility.status} · {record.created_at.slice(0, 10)}</p>
                      <p className="small-meta">Baseline {record.baseline_run_id.slice(0, 16)} · Candidate {record.candidate_run_id.slice(0, 16)}</p>
                    </div>
                    <Link to={`/workspaces/${workspaceId}/comparisons/${record.comparison_id}`}>Inspect comparison</Link>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  );
}
