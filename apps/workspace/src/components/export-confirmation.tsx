import { FormEvent, useState } from "react";

type Props = {
  onConfirm: (directory: string) => Promise<void>;
  saving: boolean;
};

export default function ExportConfirmation({ onConfirm, saving }: Props) {
  const [directory, setDirectory] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving || !directory.trim() || !acknowledged) return;
    await onConfirm(directory.trim());
  }

  return (
    <section className="surface stack" aria-labelledby="export-confirm-title">
      <h3 id="export-confirm-title">Confirm local export</h3>
      <p>
        The preview above is eligible. This is a separate write action.
        No directory is selected automatically.
      </p>
      <form onSubmit={(event) => void submit(event)} className="stack">
        <div className="field">
          <label htmlFor="export-destination">Destination directory — absolute local path</label>
          <input
            id="export-destination"
            type="text"
            value={directory}
            onChange={(event) => {
              setDirectory(event.target.value);
              setAcknowledged(false);
            }}
            placeholder="Enter a directory you have created"
            autoComplete="off"
            required
          />
          <p className="field-hint">
            Existing files and comparison folders will never be overwritten.
            The directory must already exist on this computer.
          </p>
        </div>
        <label className="choice">
          <input
            type="checkbox"
            checked={acknowledged}
            onChange={(event) => setAcknowledged(event.target.checked)}
          />
          I reviewed the included, removed and transformed fields, and want to write
          these sanitized files locally. This does not publish to GitHub Pages.
        </label>
        <button
          type="submit"
          disabled={saving || !directory.trim() || !acknowledged}
        >
          {saving ? "Writing local export…" : "Confirm & write sanitized files"}
        </button>
      </form>
    </section>
  );
}
