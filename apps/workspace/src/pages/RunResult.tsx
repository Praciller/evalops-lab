import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getBaseline, getRun, setBaseline } from "../api/client";
import { BaselinePointer, RunSummary } from "../api/schemas";

const LABELS: Record<string, string> = {
  mrr: "Mean reciprocal rank",
};

function labelMetric(key: string): string {
  if (LABELS[key]) return LABELS[key];
  if (key.startsWith("precision_at_")) return `Precision @${key.replace("precision_at_", "")}`;
  if (key.startsWith("recall_at_")) return `Recall @${key.replace("recall_at_", "")}`;
  if (key.startsWith("hit_rate_at_")) return `Hit rate @${key.replace("hit_rate_at_", "")}`;
  if (key.startsWith("ndcg_at_")) return `nDCG @${key.replace("ndcg_at_", "")}`;
  return key.replaceAll("_", " ");
}

function formatNumber(value: number): string {
  return value.toFixed(4);
}

export default function RunResult() {
  const { workspaceId = "", runId = "" } = useParams();
  const [run, setRun] = useState<RunSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [baseline, setPinnedBaseline] = useState<BaselinePointer | null>(null);
  const [baselineLoaded, setBaselineLoaded] = useState(false);
  const [pinning, setPinning] = useState(false);
  const [pinError, setPinError] = useState<string | null>(null);
  const [pinSuccess, setPinSuccess] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    getRun(workspaceId, runId).then((value) => {
      if (live) { setRun(value); setLoading(false); }
    }).catch((reason) => {
      if (live) {
        setError(reason instanceof Error ? reason.message : "Could not read run.");
        setLoading(false);
      }
    });
    return () => { live = false; };
  }, [workspaceId, runId]);

  useEffect(() => {
    let live = true;
    setBaselineLoaded(false);
    getBaseline(workspaceId).then((pointer) => {
      if (live) { setPinnedBaseline(pointer); setBaselineLoaded(true); }
    }).catch(() => {
      if (live) { setPinError("Could not verify pinned baseline."); setBaselineLoaded(false); }
    });
    return () => { live = false; };
  }, [workspaceId]);

  async function pinRun() {
    if (!run?.result_sha256 || !baselineLoaded || pinning) return;
    const replacing = baseline !== null && baseline.run_id !== run.run_id;
    if (replacing && !window.confirm(
      `Replace the workspace baseline?\nCurrent run: ${baseline.run_id}\nCurrent SHA-256: ${baseline.result_sha256}\nNew run: ${run.run_id}\nNew SHA-256: ${run.result_sha256}\nHistorical comparison records will not change.`
    )) return;
    setPinning(true);
    setPinError(null);
    setPinSuccess(null);
    try {
      const pointer = await setBaseline(workspaceId, run.run_id, replacing);
      setPinnedBaseline(pointer);
      setPinSuccess("Baseline pinned and verified. Existing comparisons remain immutable.");
    } catch (reason) {
      setPinError(reason instanceof Error ? reason.message : "Could not pin baseline.");
    } finally {
      setPinning(false);
    }
  }

  return (
    <div className="stack">
      <header className="page-heading">
        <p className="eyebrow">STEP 05 · LOCAL RESULT</p>
        <h2>Evaluation result</h2>
        <p>Private reproducible local evaluation. A completed job is not a published benchmark.</p>
      </header>
      {loading && <p role="status">Loading persisted run…</p>}
      {error && <p className="error-message" role="alert">{error}</p>}
      {run && (
        <>
          <section className="surface">
            <div className="section-head">
              <h3>{run.run_name}</h3>
              <span className="local-evidence">LOCAL EVIDENCE — Not published</span>
            </div>
            <dl className="hash-summary">
              <dt>System</dt><dd>{run.system_name}</dd>
              <dt>Dataset</dt><dd>{run.dataset_name} · {run.dataset_version}</dd>
              <dt>Top K</dt><dd>{run.top_k}</dd>
              <dt>Evaluator</dt><dd>{run.evaluator_versions.retrieval ?? "Unknown"}</dd>
            </dl>
          </section>
          <section className="surface">
            <h3>Macro metrics</h3>
            {run.metrics ? (
              <div className="metric-grid">
                {Object.entries(run.metrics).map(([key, value]) => (
                  <div className="metric-item" key={key}>
                    <span>{labelMetric(key)}</span>
                    <strong>{formatNumber(value)}</strong>
                  </div>
                ))}
              </div>
            ) : (
              <p className="empty-state">This run has no completed result yet. Inspect the associated job for its status.</p>
            )}
          </section>
          <section className="surface">
            <h3>Failure categories</h3>
            {run.failure_counts && Object.keys(run.failure_counts).length > 0 ? (
              <dl className="hash-summary">
                {Object.entries(run.failure_counts).map(([category, count]) => (
                  <div className="result-pair" key={category}>
                    <dt>{category}</dt><dd>{count}</dd>
                  </div>
                ))}
              </dl>
            ) : <p className="empty-state">No persisted failure categories to display.</p>}
            <p className="field-hint">Category counts only. Raw responses, query records and evaluator details are not exposed in this view.</p>
          </section>
          <section className="surface">
            <h3>Local provenance</h3>
            <dl className="hash-summary">
              <dt>Ground truth SHA-256</dt><dd><code>{run.ground_truth_sha256}</code></dd>
              <dt>Predictions SHA-256</dt><dd><code>{run.predictions_sha256}</code></dd>
              <dt>Result SHA-256</dt><dd><code>{run.result_sha256 ?? "Pending completion"}</code></dd>
              <dt>EvalOps version</dt><dd>{run.evalops_version ?? "Pending completion"}</dd>
            </dl>
          </section>
          <section className="surface" aria-labelledby="run-baseline-heading">
            <h3 id="run-baseline-heading">Workspace baseline</h3>
            {pinError && <p role="alert" className="error-message">{pinError}</p>}
            {pinSuccess && <p role="status" className="success-message">{pinSuccess}</p>}
            {!baselineLoaded && !pinError && <p className="field-hint">Checking current pinned baseline…</p>}
            {baselineLoaded && baseline?.run_id === run.run_id && (
              <p role="status">This completed run is the pinned workspace baseline.</p>
            )}
            {run.result_sha256 && baselineLoaded && baseline?.run_id !== run.run_id && (
              <button type="button" disabled={pinning} onClick={() => void pinRun()}>
                {pinning ? "Pinning…" : baseline ? "Replace baseline with this run" : "Set as workspace baseline"}
              </button>
            )}
            {!run.result_sha256 && (
              <p className="empty-state">Only a completed run with verified result provenance can be pinned.</p>
            )}
            <p className="field-hint">Pinning is explicit. Existing comparisons keep their original baseline and result hashes.</p>
          </section>
          <div className="action-row">
            {run.job_id && (
              <Link className="text-link" to={`/jobs/${run.job_id}`}>View job status</Link>
            )}
            <Link className="text-link" to={`/workspaces/${workspaceId}/runs`}>Back to runs</Link>
          </div>
        </>
      )}
    </div>
  );
}
