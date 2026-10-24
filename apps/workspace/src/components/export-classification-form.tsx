import { ExportClassification } from "../api/schemas";

type Props = {
  value: ExportClassification;
  onChange: (value: ExportClassification) => void;
  disabled?: boolean;
};

export default function ExportClassificationForm({ value, onChange, disabled = false }: Props) {
  return (
    <fieldset className="stack">
      <legend>Evidence classification — owner supplied</legend>
      <p className="field-hint">
        Local completion does not prove external verification. This classification
        describes the evidence, not a benchmark endorsement.
      </p>
      <div className="form-grid">
        <div className="field">
          <label htmlFor="export-kind">Data kind</label>
          <select
            id="export-kind"
            value={value.data_kind}
            disabled={disabled}
            onChange={(event) => onChange({
              ...value,
              data_kind: event.target.value as ExportClassification["data_kind"],
            })}
          >
            <option value="SYNTHETIC_FIXTURE">Synthetic fixture — integration only</option>
            <option value="CURATED_DATASET">Curated dataset — protocol specific</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="export-verification">Verification status</label>
          <select
            id="export-verification"
            value={value.verification_status}
            disabled={disabled}
            onChange={(event) => onChange({
              ...value,
              verification_status: event.target.value as ExportClassification["verification_status"],
            })}
          >
            <option value="UNVERIFIED">Unverified</option>
            <option value="PARTIAL">Partially verified</option>
            <option value="VERIFIED">Verified — explicit owner assertion</option>
          </select>
        </div>
      </div>
      <div className="field">
        <label htmlFor="export-limitations">Limitations (one per line)</label>
        <textarea
          id="export-limitations"
          rows={3}
          value={value.limitations.join("\n")}
          disabled={disabled}
          onChange={(event) => onChange({
            ...value,
            limitations: event.target.value.split("\n").map((text) => text.trim()).filter(Boolean),
          })}
        />
        <p className="field-hint">Do not enter secret keys, local paths, private prompts or personal data.</p>
      </div>
    </fieldset>
  );
}
