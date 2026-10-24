import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getComparison } from "../api/client";
import { ComparisonRecord } from "../api/schemas";

function score(value: number | null): string {
  return value === null ? "—" : value.toFixed(4);
}

export default function ComparisonDetail() {
  const { workspaceId = "", comparisonId = "" } = useParams();
  const [record, setRecord] = useState<ComparisonRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let live = true;
    getComparison(workspaceId, comparisonId).then((data) => {
      if (live) { setRecord(data); setLoading(false); }
    }).catch((reason) => {
      if (live) {
        setError(reason instanceof Error ? reason.message : "Could not load comparison.");
        setLoading(false);
      }
    });
    return () => { live = false; };
  }, [workspaceId, comparisonId]);

  return (
    <div className="stack">
      <header className="page-heading">
        <p className="eyebrow">PRIVATE COMPARISON · IMMUTABLE ARTIFACT</p>
        <h2>Comparison detail</h2>
        <p>Compatibility and pinned run provenance must be understood before metric deltas.</p>
      </header>
      {loading && <p role="status">Loading private comparison…</p>}
      {error && <p role="alert" className="error-message">{error}</p>}
      {record && (
        <>
          <section className="surface" aria-labelledby="comparison-identity-heading">
            <div className="section-head">
              <h3 id="comparison-identity-heading">Pinned operands</h3>
              <span className="local-evidence">LOCAL EVIDENCE — Not published</span>
            </div>
            <dl className="hash-summary">
              <dt>Baseline run</dt><dd><Link to={`/workspaces/${workspaceId}/runs/${record.baseline_run_id}`}>{record.baseline_run_id}</Link></dd>
              <dt>Baseline SHA-256</dt><dd><code>{record.baseline_result_sha256}</code></dd>
              <dt>Candidate run</dt><dd><Link to={`/workspaces/${workspaceId}/runs/${record.candidate_run_id}`}>{record.candidate_run_id}</Link></dd>
              <dt>Candidate SHA-256</dt><dd><code>{record.candidate_result_sha256}</code></dd>
              <dt>Policy</dt><dd>{record.policy_version}</dd>
              <dt>Mode</dt><dd><strong>{record.mode}</strong></dd>
            </dl>
          </section>

          <section className="surface" aria-labelledby="compatibility-heading">
            <h3 id="compatibility-heading">Population compatibility — {record.compatibility.status}</h3>
            {record.compatibility.reasons.length > 0 ? (
              <ul className="compatibility-reasons">
                {record.compatibility.reasons.map((reason) => (
                  <li key={reason.field}><strong>{reason.field}:</strong> baseline {reason.baseline}; candidate {reason.candidate}</li>
                ))}
              </ul>
            ) : <p>Verified evaluation population and required configuration match.</p>}
            {record.mode === "EXPLORATORY_ONLY" && (
              <p className="warning-message" role="status">
                EXPLORATORY_ONLY — Not eligible for public regression claim. This status is permanent.
              </p>
            )}
          </section>

          <section className="surface" aria-labelledby="regression-results-heading">
            <div className="section-head">
              <h3 id="regression-results-heading">Fixed-policy metric comparison</h3>
              <strong>{record.regression_report.passed ? "All metric checks pass" : "Regression or missing evidence"}</strong>
            </div>
            <p className="field-hint">The authoritative EvalOps comparator supplied all PASS, REGRESSION and MISSING decisions.</p>
            <div className="comparison-table-scroll" role="region" aria-label="Retrieval regression metric table" tabIndex={0}>
              <table className="comparison-table">
                <thead><tr><th scope="col">Metric</th><th scope="col">Baseline</th><th scope="col">Candidate</th><th scope="col">Delta</th><th scope="col">Decision</th></tr></thead>
                <tbody>{record.regression_report.comparisons.map((metric) => (
                  <tr key={metric.metric_name}>
                    <th scope="row">{metric.metric_name}</th>
                    <td>{score(metric.baseline)}</td>
                    <td>{score(metric.current)}</td>
                    <td>{score(metric.delta)}</td>
                    <td><span className="status-text" title={metric.reason}>{metric.status}</span></td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          </section>
          <div className="action-row">
            <Link className="text-link" to={`/workspaces/${workspaceId}/comparisons/${record.comparison_id}/failures`}>Inspect query-level failure transitions</Link>
            <Link className="text-link" to={`/workspaces/${workspaceId}/comparisons`}>Back to comparisons</Link>
          </div>
        </>
      )}
    </div>
  );
}
