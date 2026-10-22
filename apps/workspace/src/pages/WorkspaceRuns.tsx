import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { createRun, listInputs, listRuns, validatePair } from "../api/client";
import { InputSummary, PairValidation, RunRequest, RunSummary } from "../api/schemas";

const DEFAULT_CONFIG: Omit<RunRequest, "ground_truth_input_id" | "predictions_input_id"> = {
  run_name: "Retrieval evaluation",
  top_k: 5,
  system_name: "local-retriever",
  dataset_name: "local-dataset",
  dataset_version: "v1",
};

export default function WorkspaceRuns() {
  const { workspaceId = "" } = useParams();
  const navigate = useNavigate();
  const [inputs, setInputs] = useState<InputSummary[]>([]);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [truth, setTruth] = useState("");
  const [prediction, setPrediction] = useState("");
  const [config, setConfig] = useState(DEFAULT_CONFIG);
  const [review, setReview] = useState<PairValidation | null>(null);
  const [phase, setPhase] = useState<"loading" | "ready" | "validating" | "submitting">("loading");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    Promise.all([listInputs(workspaceId), listRuns(workspaceId)]).then(([allInputs, allRuns]) => {
      if (!mounted) return;
      setInputs(allInputs);
      setRuns(allRuns);
      setTruth(allInputs.find((input) => input.kind === "retrieval_ground_truth")?.input_id ?? "");
      setPrediction(allInputs.find((input) => input.kind === "retrieval_predictions")?.input_id ?? "");
      setPhase("ready");
    }).catch(() => {
      if (mounted) { setError("Could not load retrieval runs."); setPhase("ready"); }
    });
    return () => { mounted = false; };
  }, [workspaceId]);

  const selectedTruth = useMemo(() => inputs.find((item) => item.input_id === truth), [inputs, truth]);
  const selectedPrediction = useMemo(() => inputs.find((item) => item.input_id === prediction), [inputs, prediction]);

  function changeConfig<Key extends keyof typeof config>(key: Key, value: typeof config[Key]) {
    setConfig((before) => ({ ...before, [key]: value }));
  }

  async function validate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setReview(null);
    setPhase("validating");
    try {
      setReview(await validatePair(workspaceId, truth, prediction));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Pair validation failed.");
    } finally {
      setPhase("ready");
    }
  }

  async function startEvaluation() {
    if (!review || review.blocking_codes.length || !truth || !prediction) return;
    setError(null);
    setPhase("submitting");
    try {
      const run = await createRun(workspaceId, {
        ...config,
        ground_truth_input_id: truth,
        predictions_input_id: prediction,
      });
      if (!run.job_id) throw new Error("Job identity was not returned.");
      navigate(`/jobs/${run.job_id}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not start evaluation.");
      setPhase("ready");
    }
  }

  return (
    <div className="stack">
      <header className="page-heading">
        <p className="eyebrow">STEP 02 · RETRIEVAL EVALUATION</p>
        <h2>Configure & review a run</h2>
        <p>Use the pinned deterministic retrieval evaluator. Results and evidence stay local.</p>
      </header>
      <section className="surface" aria-labelledby="run-config-heading">
        <h3 id="run-config-heading">Input pair & configuration</h3>
        {phase === "loading" && <p aria-live="polite">Loading available inputs…</p>}
        {phase !== "loading" && (
          <form onSubmit={(event) => void validate(event)} className="stack">
            <div className="form-grid">
              <div className="field">
                <label htmlFor="truth-select">Ground truth input</label>
                <select id="truth-select" value={truth} onChange={(e) => { setTruth(e.target.value); setReview(null); }}>
                  <option value="">Select ground truth</option>
                  {inputs.filter((x) => x.kind === "retrieval_ground_truth").map((x) => (
                    <option key={x.input_id} value={x.input_id}>{x.input_id.slice(0, 19)} · {x.record_count} records</option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="prediction-select">Prediction input</label>
                <select id="prediction-select" value={prediction} onChange={(e) => { setPrediction(e.target.value); setReview(null); }}>
                  <option value="">Select predictions</option>
                  {inputs.filter((x) => x.kind === "retrieval_predictions").map((x) => (
                    <option key={x.input_id} value={x.input_id}>{x.input_id.slice(0, 19)} · {x.record_count} records</option>
                  ))}
                </select>
              </div>
              {([
                ["run_name", "Run name"],
                ["system_name", "System label"],
                ["dataset_name", "Dataset name"],
                ["dataset_version", "Dataset version"],
              ] as const).map(([key, label]) => (
                <div className="field" key={key}>
                  <label htmlFor={key}>{label}</label>
                  <input id={key} type="text" value={config[key]} onChange={(event) => changeConfig(key, event.target.value)} minLength={1} maxLength={200} required />
                </div>
              ))}
              <div className="field">
                <label htmlFor="top-k">Top K</label>
                <input id="top-k" type="number" min={1} step={1} value={config.top_k} onChange={(event) => changeConfig("top_k", Number(event.target.value))} required />
              </div>
            </div>
            <div className="readonly-contract">
              <strong>Evaluator contract (read-only)</strong>
              <p>retrieval: deterministic-v1 · precision@k · recall@k · hit rate@k · MRR · nDCG@k</p>
            </div>
            {inputs.length === 0 && (
              <p className="empty-state">No inputs available. <Link to={`/workspaces/${workspaceId}/inputs`}>Register JSONL or CSV first</Link>.</p>
            )}
            {error && <p className="error-message" role="alert">{error}</p>}
            <button type="submit" disabled={!truth || !prediction || phase !== "ready" || !Number.isInteger(config.top_k) || config.top_k < 1}>
              {phase === "validating" ? "Validating pair…" : "Validate & review"}
            </button>
          </form>
        )}
      </section>
      {review && (
        <section className="surface" aria-labelledby="review-heading">
          <p className="eyebrow">STEP 03 · REVIEW</p>
          <h3 id="review-heading">Review before evaluation</h3>
          <div className="summary-grid">
            <div><strong>{review.ground_truth_records}</strong><span>Ground truth queries</span></div>
            <div><strong>{review.prediction_records}</strong><span>Predicted queries</span></div>
            <div><strong>{review.matching_query_count}</strong><span>Matching queries</span></div>
          </div>
          <dl className="hash-summary">
            <dt>Ground truth SHA-256</dt><dd><code>{selectedTruth?.content_sha256}</code></dd>
            <dt>Predictions SHA-256</dt><dd><code>{selectedPrediction?.content_sha256}</code></dd>
          </dl>
          {review.warning_codes.length > 0 && (
            <p className="warning-message" role="status">
              Warnings: {review.warning_codes.join(", ")} · Missing {review.missing_prediction_count}, extra {review.extra_prediction_count} queries.
            </p>
          )}
          {review.blocking_codes.length > 0 && (
            <p className="error-message" role="alert">Blocking errors: {review.blocking_codes.join(", ")}. Correct your inputs before running.</p>
          )}
          {review.blocking_codes.length === 0 && (
            <div className="action-row">
              <button onClick={() => void startEvaluation()} disabled={phase === "submitting"}>
                {phase === "submitting" ? "Starting…" : "Run Evaluation"}
              </button>
              <span className="small-meta">LOCAL EVIDENCE — Not published</span>
            </div>
          )}
        </section>
      )}
      <section className="surface" aria-labelledby="previous-runs">
        <h3 id="previous-runs">Saved runs</h3>
        {runs.length === 0 ? <p className="empty-state">No runs in this workspace yet.</p> : (
          <ul className="input-list">{runs.map((run) => (
            <li key={run.run_id}>
              <div><strong>{run.run_name}</strong><p className="small-meta">K = {run.top_k} · {run.created_at.slice(0, 10)}</p></div>
              <div className="action-row">
                {run.job_id && <Link to={`/jobs/${run.job_id}`}>Job status</Link>}
                <Link to={`/workspaces/${workspaceId}/runs/${run.run_id}`}>View run</Link>
              </div>
            </li>
          ))}</ul>
        )}
      </section>
    </div>
  );
}
