import type { PublicRunArtifact } from "@/lib/evidence/schemas";
import { formatMetricValue, humanizeMetricName } from "@/lib/evidence/format";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";

function ids(values: string[]) {
  return values.length ? values.join(", ") : "Not included";
}

function recordMetrics(record: PublicRunArtifact["evidence"][number]) {
  const groups = Object.entries(record.metrics_by_k);
  if (!groups.length) return Object.entries(record.metrics).map(([key, value]) => `${humanizeMetricName(key)} ${formatMetricValue(value)}`).join(" · ") || "No per-record metrics";
  return groups.map(([k, metrics]) => `k=${k}: ${Object.entries(metrics).slice(0, 2).map(([key, value]) => `${humanizeMetricName(key)} ${formatMetricValue(value)}`).join(" · ")}`).join("; ");
}

export function EvidenceTable({ evidence }: { evidence: PublicRunArtifact["evidence"] }) {
  return (
    <Card className="p-5">
      <CardHeader>
        <CardTitle>Record-level evidence</CardTitle>
        <span className="text-xs text-muted">{evidence.length} approved records</span>
      </CardHeader>
      {evidence.length ? (
        <div className="overflow-x-auto">
          <table className="data-table">
            <caption className="sr-only">Approved record-level retrieval evidence</caption>
            <thead><tr><th scope="col">Record</th><th scope="col">Status</th><th scope="col">Metrics</th><th scope="col">Retrieved IDs</th><th scope="col">Relevant IDs</th></tr></thead>
            <tbody>
              {evidence.map((record) => (
                <tr key={record.record_ref}>
                  <th className="font-mono text-xs" scope="row">{record.record_ref}</th>
                  <td><span className={record.failure_category === "PASS" ? "text-success" : "text-danger"}>{record.failure_category === "PASS" ? "Pass" : record.failure_category}</span></td>
                  <td className="min-w-48 text-xs">{recordMetrics(record)}</td>
                  <td className="min-w-48 font-mono text-xs text-muted">{ids(record.retrieved_document_ids)}</td>
                  <td className="min-w-48 font-mono text-xs text-muted">{ids(record.relevant_document_ids)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="empty-state">This artifact publishes aggregate metrics only; no per-record evidence is included.</p>
      )}
    </Card>
  );
}

export function FailureSummary({ failures, evidenceCount }: { failures: PublicRunArtifact["failures"]; evidenceCount: number }) {
  return (
    <Card className="p-5">
      <CardHeader><CardTitle>Failure summary</CardTitle><span className="text-xs text-muted">{failures.length} labeled failures</span></CardHeader>
      {failures.length ? (
        <ul className="grid gap-3 sm:grid-cols-2">
          {failures.map((failure) => <li className="rounded-md border border-danger/30 bg-danger-surface p-3 text-sm" key={`${failure.record_ref}-${failure.category}`}><span className="font-mono text-xs">{failure.record_ref}</span><span className="ml-2 font-semibold">{failure.category}</span>{failure.failure_class ? <span className="mt-1 block text-xs text-muted">Class: {failure.failure_class}</span> : null}</li>)}
        </ul>
      ) : (
        <p className="empty-state">No public failure records are included for this artifact. This is not proof of perfect model performance{evidenceCount ? " on every possible input" : ""}.</p>
      )}
    </Card>
  );
}
