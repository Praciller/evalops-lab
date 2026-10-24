import { ExportPreview } from "../api/schemas";

type Props = { preview: ExportPreview };

function Disclosure({ title, items }: { title: string; items: string[] }) {
  return (
    <section className="export-disclosure">
      <h4>{title}</h4>
      {items.length ? (
        <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul>
      ) : (
        <p className="small-meta">Nothing in this category.</p>
      )}
    </section>
  );
}

export default function ExportPreviewPanel({ preview }: Props) {
  return (
    <section className="surface stack" aria-labelledby="export-preview-title">
      <div className="section-head">
        <h3 id="export-preview-title">Sanitized export preview</h3>
        <span className="local-evidence">PREVIEW ONLY — No files written</span>
      </div>
      <p className="small-meta">
        This preview expires at {new Date(preview.expires_at).toLocaleString()}.
      </p>
      <section aria-labelledby="export-classification-result">
        <h4 id="export-classification-result">Classification</h4>
        <p>
          {preview.classification.data_kind} · {preview.classification.verification_status}
        </p>
        <p className="small-meta">
          {preview.classification.data_kind === "SYNTHETIC_FIXTURE"
            ? "Integration-only claim"
            : "Protocol-specific claim"}
        </p>
        {preview.classification.limitations.length > 0 && (
          <ul>{preview.classification.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
        )}
      </section>
      {preview.blocking_reasons.length > 0 && (
        <p className="error-message" role="alert">
          Export is not eligible: {preview.blocking_reasons.join(", ")}.
        </p>
      )}
      <div className="export-disclosure-grid">
        <Disclosure title="Included" items={preview.included} />
        <Disclosure title="Removed" items={preview.removed} />
        <Disclosure title="Transformed" items={preview.transformed} />
      </div>
      <section aria-labelledby="export-preview-files">
        <h4 id="export-preview-files">Output files</h4>
        {preview.output_files.length === 0 ? (
          <p className="empty-state">No eligible files to export.</p>
        ) : (
          <ul className="export-file-list">
            {preview.output_files.map((file) => (
              <li key={file.filename}>
                <strong>{file.filename}</strong>
                <span>{file.size_bytes.toLocaleString()} bytes</span>
                <code>SHA-256 {file.sha256}</code>
              </li>
            ))}
          </ul>
        )}
      </section>
      <p className="warning-message">
        Creating sanitized export does not publish to GitHub Pages.
      </p>
    </section>
  );
}
