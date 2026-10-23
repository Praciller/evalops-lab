import { FormEvent, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  listInputs, referenceInput, uploadCsv, uploadInput,
} from "../api/client";
import { InputKind, InputSummary } from "../api/schemas";

type SourceMode = "jsonl" | "reference" | "csv";

function shortHash(hash: string): string {
  return `${hash.slice(0, 12)}…${hash.slice(-6)}`;
}

export default function WorkspaceInputs() {
  const { workspaceId = "" } = useParams();
  const [inputs, setInputs] = useState<InputSummary[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [mode, setMode] = useState<SourceMode>("jsonl");
  const [kind, setKind] = useState<InputKind>("retrieval_ground_truth");
  const [file, setFile] = useState<File | null>(null);
  const [path, setPath] = useState("");
  const [queryColumn, setQueryColumn] = useState("query_id");
  const [docsColumn, setDocsColumn] = useState("document_ids");
  const [delimiter, setDelimiter] = useState("|");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let mounted = true;
    listInputs(workspaceId).then((data) => {
      if (mounted) { setInputs(data); setStatus("ready"); }
    }).catch(() => {
      if (mounted) { setError("Could not load registered inputs."); setStatus("error"); }
    });
    return () => { mounted = false; };
  }, [workspaceId]);

  async function register(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSuccess(null);
    if (mode !== "reference" && !file) {
      setError("Select a source file first.");
      return;
    }
    if (mode === "reference" && !path.trim()) {
      setError("Enter an explicit local file path.");
      return;
    }
    setSaving(true);
    try {
      const created = mode === "jsonl"
        ? await uploadInput(workspaceId, kind, file!)
        : mode === "reference"
          ? await referenceInput(workspaceId, kind, path.trim())
          : await uploadCsv(workspaceId, kind, file!, {
              query_id_column: queryColumn.trim(),
              document_ids_column: docsColumn.trim(),
              document_ids_delimiter: delimiter,
            });
      setInputs(await listInputs(workspaceId));
      setSuccess(`Registered ${created.record_count} validated record(s). Content SHA-256: ${created.content_sha256}`);
      setFile(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Input registration failed.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="stack">
      <header className="page-heading">
        <p className="eyebrow">STEP 01 · INPUTS</p>
        <h2>Register retrieval inputs</h2>
        <p>Use validated JSONL, explicit local paths or a guided CSV mapping. Files never leave this machine.</p>
      </header>

      <section className="surface" aria-labelledby="register-heading">
        <h3 id="register-heading">Add an input</h3>
        <form onSubmit={(event) => void register(event)} className="stack">
          <fieldset className="source-mode">
            <legend>Source type</legend>
            {([
              ["jsonl", "JSONL file"],
              ["reference", "Local path"],
              ["csv", "CSV mapping"],
            ] as const).map(([value, title]) => (
              <label key={value} className="choice">
                <input
                  type="radio" name="source-mode" checked={mode === value}
                  onChange={() => { setMode(value); setFile(null); setError(null); }}
                />
                {title}
              </label>
            ))}
          </fieldset>
          <div className="field">
            <label htmlFor="input-kind">Input role</label>
            <select id="input-kind" value={kind} onChange={(event) => setKind(event.target.value as InputKind)}>
              <option value="retrieval_ground_truth">Ground truth · Relevant document IDs</option>
              <option value="retrieval_predictions">Predictions · Retrieved document IDs</option>
            </select>
          </div>
          {mode === "reference" ? (
            <div className="field" key="reference-mode">
              <label htmlFor="reference-path">Absolute local JSONL path</label>
              <input
                id="reference-path" type="text" value={path}
                onChange={(event) => setPath(event.target.value)}
                placeholder="C:\\data\\retrieval\\predictions.jsonl" autoComplete="off"
              />
              <p className="field-hint">The file is not copied. Its checksum is checked again before evaluation.</p>
            </div>
          ) : (
            <div className="field" key="file-mode">
              <label htmlFor="input-file">{mode === "csv" ? "CSV file" : "JSONL file"}</label>
              <input
                id="input-file" type="file" accept={mode === "csv" ? ".csv" : ".jsonl"}
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                aria-required="true"
              />
              <p className="field-hint">Maximum 10 MiB. Validation must pass before registration.</p>
            </div>
          )}
          {mode === "csv" && (
            <fieldset className="mapping-fields">
              <legend>CSV column mapping</legend>
              <div className="form-grid">
                <div className="field">
                  <label htmlFor="query-column">Query ID column</label>
                  <input id="query-column" type="text" value={queryColumn} onChange={(event) => setQueryColumn(event.target.value)} required />
                </div>
                <div className="field">
                  <label htmlFor="docs-column">Document IDs column</label>
                  <input id="docs-column" type="text" value={docsColumn} onChange={(event) => setDocsColumn(event.target.value)} required />
                </div>
                <div className="field">
                  <label htmlFor="delimiter">Document IDs delimiter</label>
                  <input id="delimiter" type="text" maxLength={1} value={delimiter} onChange={(event) => setDelimiter(event.target.value)} required />
                </div>
              </div>
              <p className="field-hint">Canonical JSONL is created and validated; original CSV is not stored.</p>
            </fieldset>
          )}
          {error && <p className="error-message" role="alert">{error}</p>}
          {success && <p className="success-message" role="status">{success}</p>}
          <div className="action-row">
            <button type="submit" disabled={saving}>{saving ? "Validating…" : "Validate & register"}</button>
            <Link className="text-link" to={`/workspaces/${workspaceId}/runs`}>Continue to Runs</Link>
          </div>
        </form>
      </section>

      <section className="surface" aria-labelledby="registered-inputs">
        <div className="section-head">
          <h3 id="registered-inputs">Registered inputs</h3>
          <span className="small-meta">{inputs.length} input(s)</span>
        </div>
        {status === "loading" && <p role="status">Loading registered inputs…</p>}
        {status === "error" && <p className="error-message" role="alert">Could not load registered inputs.</p>}
        {status === "ready" && inputs.length === 0 && <p className="empty-state">No inputs registered yet.</p>}
        {inputs.length > 0 && (
          <ul className="input-list">
            {inputs.map((item) => (
              <li key={item.input_id}>
                <div>
                  <strong>{item.kind === "retrieval_ground_truth" ? "Ground truth" : "Predictions"}</strong>
                  <p className="small-meta">{item.source_mode} · {item.record_count} record(s)</p>
                </div>
                <code title={item.content_sha256}>SHA-256 {shortHash(item.content_sha256)}</code>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
