import { FormEvent, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  getComparison, listComparisonFailures, listComparisons, type FailureFilters,
} from "../api/client";
import {
  ComparisonFailuresResponse, ComparisonRecord, FailureTransition,
} from "../api/schemas";

const TRANSITIONS = [
  "UNCHANGED_PASS", "REGRESSED", "IMPROVED", "PERSISTENT_FAILURE", "CHANGED_FAILURE",
] as const;
const CATEGORIES = [
  "PASS", "RETRIEVAL_MISS", "SHOULD_ABSTAIN", "WRONG_ANSWER", "HALLUCINATION",
  "UNSUPPORTED_CLAIM", "WRONG_CITATION", "INCOMPLETE_ANSWER", "CONTEXT_CONFLICT",
  "DATASET_AMBIGUOUS", "GROUND_TRUTH_ERROR", "EVALUATOR_UNCERTAIN",
] as const;

function number(value: number | undefined): string {
  return value === undefined ? "—" : value.toFixed(4);
}

export default function FailuresPage() {
  const { workspaceId = "", comparisonId } = useParams();
  const [comparisons, setComparisons] = useState<ComparisonRecord[]>([]);
  const [record, setRecord] = useState<ComparisonRecord | null>(null);
  const [report, setReport] = useState<ComparisonFailuresResponse | null>(null);
  const [transition, setTransition] = useState<FailureTransition | "">("");
  const [category, setCategory] = useState("");
  const [query, setQuery] = useState("");
  const [exact, setExact] = useState(true);
  const [applied, setApplied] = useState<FailureFilters>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setLoading(true);
    setError(null);
    if (!comparisonId) {
      listComparisons(workspaceId).then((items) => {
        if (live) { setComparisons(items); setLoading(false); }
      }).catch(() => {
        if (live) { setError("Could not load local comparisons."); setLoading(false); }
      });
    } else {
      Promise.all([
        getComparison(workspaceId, comparisonId),
        listComparisonFailures(workspaceId, comparisonId, applied),
      ]).then(([item, data]) => {
        if (live) { setRecord(item); setReport(data); setLoading(false); }
      }).catch((reason) => {
        if (live) {
          setReport(null);
          setError(reason instanceof Error ? reason.message : "Failure transitions are unavailable.");
          setLoading(false);
        }
      });
    }
    return () => { live = false; };
  }, [workspaceId, comparisonId, applied]);

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setApplied({
      transition: transition || undefined,
      category: category || undefined,
      queryId: query.trim() || undefined,
      exact,
    });
  }

  return (
    <div className="stack">
      <header className="page-heading">
        <p className="eyebrow">PRIVATE FAILURE EXPLORER</p>
        <h2>Query-level transitions</h2>
        <p>Only evaluator-persisted categories and metrics are displayed. No corpus or prompts are published.</p>
      </header>
      {loading && <p role="status">Loading private query evidence…</p>}
      {error && <p role="alert" className="error-message">{error}</p>}
      {!comparisonId && !loading && (
        <section className="surface">
          <h3>Choose a saved comparison</h3>
          {comparisons.length === 0 ? <p className="empty-state">No comparisons exist yet.</p> : (
            <ul className="input-list">{comparisons.map((item) => (
              <li key={item.comparison_id}>
                <div>
                  <strong>{item.mode}</strong>
                  <p className="small-meta">{item.compatibility.status} · {item.comparison_id.slice(0, 22)}</p>
                </div>
                <Link to={`/workspaces/${workspaceId}/comparisons/${item.comparison_id}/failures`}>View transitions</Link>
              </li>
            ))}</ul>
          )}
        </section>
      )}
      {comparisonId && (
        <>
          {record && (
            <section className="surface">
              <div className="section-head">
                <h3>Comparison: {record.mode}</h3>
                <span className="local-evidence">LOCAL EVIDENCE — Not published</span>
              </div>
              <p>Baseline {record.baseline_run_id.slice(0, 16)} · Candidate {record.candidate_run_id.slice(0, 16)}</p>
              {record.mode === "EXPLORATORY_ONLY" && (
                <p className="warning-message">EXPLORATORY_ONLY — Not eligible for public regression claim.</p>
              )}
              <Link className="text-link" to={`/workspaces/${workspaceId}/comparisons/${comparisonId}`}>View comparison context</Link>
            </section>
          )}
          <section className="surface" aria-labelledby="failure-filters-heading">
            <h3 id="failure-filters-heading">Filter persisted transitions</h3>
            <form className="stack" onSubmit={applyFilters}>
              <div className="form-grid">
                <div className="field">
                  <label htmlFor="failure-transition">Transition</label>
                  <select id="failure-transition" value={transition} onChange={(event) => setTransition(event.target.value as FailureTransition | "")}>
                    <option value="">All transitions</option>
                    {TRANSITIONS.map((value) => <option value={value} key={value}>{value}</option>)}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="failure-category">Failure category</label>
                  <select id="failure-category" value={category} onChange={(event) => setCategory(event.target.value)}>
                    <option value="">Any category</option>
                    {CATEGORIES.map((value) => <option value={value} key={value}>{value}</option>)}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="failure-query">Query ID</label>
                  <input id="failure-query" type="text" maxLength={200} value={query} onChange={(event) => setQuery(event.target.value)} />
                </div>
                <div className="field">
                  <label htmlFor="failure-match">Query ID match</label>
                  <select id="failure-match" value={exact ? "exact" : "contains"} onChange={(event) => setExact(event.target.value === "exact")}>
                    <option value="exact">Exact</option>
                    <option value="contains">Contains</option>
                  </select>
                </div>
              </div>
              <div className="action-row"><button type="submit">Apply filters</button></div>
            </form>
          </section>
          {!loading && report && (
            <section className="surface" aria-labelledby="failure-results-heading">
              <div className="section-head">
                <h3 id="failure-results-heading">Persisted query transitions</h3>
                <span className="small-meta">{report.total_count} matching query(s)</span>
              </div>
              {report.transitions.length === 0 ? <p className="empty-state">No transitions match these filters.</p> : (
                <div className="comparison-table-scroll" role="region" aria-label="Failure transition results" tabIndex={0}>
                  <table className="comparison-table">
                    <thead><tr><th scope="col">Query ID</th><th scope="col">Transition</th><th scope="col">Baseline category</th><th scope="col">Candidate category</th><th scope="col">Metric detail</th></tr></thead>
                    <tbody>{report.transitions.map((item) => (
                      <tr key={item.query_id}>
                        <th scope="row"><code>{item.query_id}</code></th>
                        <td>{item.transition}</td>
                        <td>{item.baseline_category}</td>
                        <td>{item.candidate_category}</td>
                        <td>
                          <details>
                            <summary>View metrics</summary>
                            <dl className="query-metrics">
                              {Object.keys(item.baseline_metrics).sort().map((metric) => (
                                <div key={metric}>
                                  <dt>{metric}</dt>
                                  <dd>{number(item.baseline_metrics[metric])} → {number(item.candidate_metrics[metric])}</dd>
                                </div>
                              ))}
                            </dl>
                          </details>
                        </td>
                      </tr>
                    ))}</tbody>
                  </table>
                </div>
              )}
            </section>
          )}
          <Link className="text-link" to={`/workspaces/${workspaceId}/failures`}>Back to failure comparisons</Link>
        </>
      )}
    </div>
  );
}
