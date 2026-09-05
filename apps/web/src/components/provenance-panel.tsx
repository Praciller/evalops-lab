import type { PublicRunArtifact } from "@/lib/evidence/schemas";
import { formatTimestamp, humanizeLabel } from "@/lib/evidence/format";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";

export function ProvenancePanel({ artifact }: { artifact: PublicRunArtifact }) {
  const run = artifact.run;
  const fields = [
    ["Dataset", `${run.dataset_name} · ${run.dataset_version}`],
    ["System", run.system_name],
    ["Evaluation", humanizeLabel(run.evaluation_type)],
    ["Recorded", formatTimestamp(run.timestamp)],
    ["Top-k", String(run.top_k)],
    ["Evaluator", Object.entries(run.evaluator_versions).map(([key, value]) => `${key}: ${value}`).join(" · ")],
  ];
  if (run.benchmark) fields.splice(2, 0, ["Benchmark context", `${run.benchmark} · ${run.language ?? "language not specified"} · ${run.split ?? "split not specified"}`]);
  if (run.retriever) fields.push(["Retriever", `${run.retriever} · ${run.retriever_version ?? "version not specified"}`]);

  return (
    <Card className="p-5">
      <CardHeader><CardTitle>Provenance</CardTitle></CardHeader>
      <dl className="grid gap-4 sm:grid-cols-2">
        {fields.map(([label, value]) => (
          <div key={label}>
            <dt className="text-xs font-semibold uppercase tracking-[0.1em] text-muted">{label}</dt>
            <dd className="mt-1 break-words text-sm text-ink">{value}</dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}

export function LimitationsPanel({ limitations }: { limitations: string[] }) {
  return (
    <Card className="border-caution/40 bg-caution-surface p-5">
      <CardHeader><CardTitle>Limitations</CardTitle></CardHeader>
      <ul className="space-y-2 text-sm leading-6 text-ink">
        {limitations.map((limitation) => <li key={limitation}>• {limitation}</li>)}
      </ul>
    </Card>
  );
}
