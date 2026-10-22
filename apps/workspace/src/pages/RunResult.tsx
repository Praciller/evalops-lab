import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getRun } from "../api/client";
import { RunSummary } from "../api/schemas";

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
          <Link className="text-link" to={`/workspaces/${workspaceId}/runs`}>Back to runs</Link>
        </>
      )}
    </div>
  );
}
