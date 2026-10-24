import { FormEvent, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import {
  WorkspaceApiError,
  confirmExport,
  createExportPreview,
  listComparisons,
  listExports,
  listRuns,
} from "../api/client";
import {
  ComparisonRecord,
  ExportClassification,
  ExportManifest,
  ExportPreview,
  RunSummary,
} from "../api/schemas";
import ExportClassificationForm from "../components/export-classification-form";
import ExportConfirmation from "../components/export-confirmation";
import ExportPreviewPanel from "../components/export-preview";

const DEFAULT_CLASSIFICATION: ExportClassification = {
  verification_status: "UNVERIFIED",
  data_kind: "SYNTHETIC_FIXTURE",
  limitations: ["Local-only evidence; no independent benchmark verification"],
};

type SourceType = "run" | "comparison";

function safeError(error: unknown, fallback: string): string {
  return error instanceof WorkspaceApiError ? error.message : fallback;
}

export default function ExportsPage() {
  const { workspaceId = "" } = useParams();
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [comparisons, setComparisons] = useState<ComparisonRecord[]>([]);
  const [history, setHistory] = useState<ExportManifest[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [sourceType, setSourceType] = useState<SourceType>("run");
  const [sourceId, setSourceId] = useState("");
  const [classification, setClassification] = useState(DEFAULT_CLASSIFICATION);
  const [preview, setPreview] = useState<ExportPreview | null>(null);
  const [manifest, setManifest] = useState<ExportManifest | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setLoaded(false);
    setPreview(null);
    setManifest(null);
    setSourceId("");
    setError(null);
    Promise.all([listRuns(workspaceId), listComparisons(workspaceId), listExports(workspaceId)])
      .then(([nextRuns, nextComparisons, nextHistory]) => {
        if (!live) return;
        setRuns(nextRuns);
        setComparisons(nextComparisons);
        setHistory(nextHistory);
        setLoaded(true);
      })
      .catch(() => {
        if (live) {
          setError("Could not load private Workspace export candidates.");
          setLoaded(true);
        }
      });
    return () => { live = false; };
  }, [workspaceId]);

  function resetPending() {
    setPreview(null);
    setManifest(null);
    setError(null);
  }

  async function makePreview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!sourceId || previewing || saving) return;
    setPreviewing(true);
    resetPending();
    try {
      const created = await createExportPreview(workspaceId, {
        source_type: sourceType,
        source_id: sourceId,
        classification,
      });
      setPreview(created);
    } catch (reason) {
      setError(safeError(reason, "Sanitized preview could not be created."));
    } finally {
      setPreviewing(false);
    }
  }

  async function confirm(directory: string): Promise<void> {
    if (!preview?.eligible || saving) return;
    setSaving(true);
    setError(null);
    try {
      const completed = await confirmExport(workspaceId, preview.preview_id, directory);
      setManifest(completed);
      setHistory(await listExports(workspaceId));
    } catch (reason) {
      setError(safeError(reason, "Local export could not be confirmed."));
      if (
        reason instanceof WorkspaceApiError
        && ["export_source_changed", "export_preview_expired"].includes(reason.code)
      ) {
        setPreview(null);
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="stack">
      <header className="page-heading">
        <p className="eyebrow">STEP 06 · EXPLICIT LOCAL EXPORT</p>
        <h2>Sanitized evidence export</h2>
        <p>
          Select completed local evidence, inspect exactly what would be included,
          removed and transformed, then optionally confirm a local write.
        </p>
        <p><strong>Creating sanitized export does not publish to GitHub Pages.</strong></p>
      </header>

      <section className="surface stack" aria-labelledby="export-source-title">
        <h3 id="export-source-title">Choose local evidence</h3>
        {!loaded && <p role="status">Loading owned evidence…</p>}
        <form className="stack" onSubmit={(event) => void makePreview(event)}>
          <div className="form-grid">
            <div className="field">
              <label htmlFor="export-source-type">Evidence type</label>
              <select
                id="export-source-type"
                value={sourceType}
                disabled={!loaded || previewing || saving}
                onChange={(event) => {
                  setSourceType(event.target.value as SourceType);
                  setSourceId("");
                  resetPending();
                }}
              >
                <option value="run">Completed run</option>
                <option value="comparison">Comparison record</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="export-source-id">Source ID</label>
              <select
                id="export-source-id"
                value={sourceId}
                disabled={!loaded || previewing || saving}
                onChange={(event) => { setSourceId(event.target.value); resetPending(); }}
              >
                <option value="">Choose evidence</option>
                {sourceType === "run"
                  ? runs.filter((run) => run.result_sha256).map((run) => (
                    <option key={run.run_id} value={run.run_id}>{run.run_name} · {run.run_id}</option>
                  ))
                  : comparisons.map((item) => (
                    <option key={item.comparison_id} value={item.comparison_id}>
                      {item.comparison_id} · {item.mode}
                    </option>
                  ))}
              </select>
            </div>
          </div>
          <ExportClassificationForm
            value={classification}
            disabled={!loaded || previewing || saving}
            onChange={(next) => { setClassification(next); resetPending(); }}
          />
          <button type="submit" disabled={!sourceId || previewing || saving}>
            {previewing ? "Checking public-evidence policy…" : "Create sanitized preview"}
          </button>
        </form>
      </section>

      {error && <p className="error-message" role="alert">{error}</p>}

      {preview && <ExportPreviewPanel preview={preview} />}

      {preview?.eligible && !manifest && (
        <ExportConfirmation
          key={preview.preview_id}
          saving={saving}
          onConfirm={confirm}
        />
      )}

      {manifest && (
        <section className="surface stack" aria-labelledby="export-success-title">
          <h3 id="export-success-title">Local export completed</h3>
          <p role="status">
            Sanitized files were written to the selected local directory.
            No GitHub Pages deployment occurred.
          </p>
          <dl className="hash-summary">
            <dt>Private export ID</dt><dd><code>{manifest.export_id}</code></dd>
            <dt>Destination</dt><dd><code>{manifest.destination}</code></dd>
          </dl>
          <ul className="export-file-list">
            {manifest.files.map((file) => (
              <li key={file.filename}>
                <strong>{file.filename}</strong>
                <code>SHA-256 {file.sha256}</code>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="surface stack" aria-labelledby="export-history-title">
        <h3 id="export-history-title">Private export history</h3>
        {loaded && history.length === 0 && (
          <p className="empty-state">No confirmed local exports in this workspace.</p>
        )}
        <ul className="export-file-list">
          {history.map((entry) => (
            <li key={entry.export_id}>
              <strong>{entry.source_type} · {entry.export_id}</strong>
              <code>{entry.destination}</code>
              <span className="small-meta">{entry.files.length} file(s) · Not published</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
