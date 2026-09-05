import Link from "next/link";

import { ArtifactBadges } from "@/components/status-badges";
import { EvidenceLayout } from "@/components/evidence-layout";
import { EvidenceTable, FailureSummary } from "@/components/evidence-table";
import { LimitationsPanel, ProvenancePanel } from "@/components/provenance-panel";
import { MetricCard } from "@/components/metric-card";
import { formatMetricValue, humanizeLabel, humanizeMetricName } from "@/lib/evidence/format";
import type { PublicRunArtifact } from "@/lib/evidence/schemas";

export function RunDetail({ artifact }: { artifact: PublicRunArtifact }) {
  return (
    <EvidenceLayout>
      <div className="space-y-8">
        <nav aria-label="Breadcrumb" className="text-sm"><Link className="focus-ring rounded text-accent underline underline-offset-4 hover:no-underline" href="/">Evidence Console</Link><span className="mx-2 text-muted" aria-hidden="true">/</span><span className="font-mono text-xs text-muted">{artifact.artifact_id}</span></nav>
        <section aria-labelledby="run-title" className="grid gap-6 lg:grid-cols-[1fr_300px] lg:items-end">
          <div><p className="eyebrow">Run artifact · {humanizeLabel(artifact.run.evaluation_type)}</p><h1 id="run-title" className="mt-3 break-words text-3xl font-semibold tracking-tight text-ink sm:text-4xl">{artifact.run.dataset_name}</h1><p className="mt-3 max-w-3xl text-sm leading-6 text-muted">System <span className="font-semibold text-ink">{artifact.run.system_name}</span> evaluated against <span className="font-semibold text-ink">{artifact.run.dataset_version}</span>. This page presents only approved public evidence.</p><div className="mt-5"><ArtifactBadges artifact={artifact} /></div></div>
          <div className="surface p-4"><p className="text-xs font-semibold uppercase tracking-[0.1em] text-muted">Artifact ID</p><p className="mt-2 break-all font-mono text-xs font-semibold text-ink">{artifact.artifact_id}</p><p className="mt-4 text-xs leading-5 text-muted">Claim scope: {humanizeLabel(artifact.claim_scope)}.</p></div>
        </section>

        <section aria-labelledby="metrics-title"><div className="mb-4"><p className="eyebrow">Aggregate values</p><h2 id="metrics-title" className="section-title">Metrics</h2></div><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{Object.entries(artifact.metrics).map(([name, value]) => <MetricCard key={name} name={name} value={value} context={`k preserved in metric name · ${artifact.run.run_id}`} />)}</div></section>

        <section className="grid gap-6 lg:grid-cols-[1fr_360px]" aria-label="Failure and provenance evidence"><FailureSummary failures={artifact.failures} evidenceCount={artifact.evidence.length} /><ProvenancePanel artifact={artifact} /></section>
        <EvidenceTable evidence={artifact.evidence} />
        <LimitationsPanel limitations={artifact.limitations} />
        <section className="surface p-5" aria-labelledby="contract-title"><h2 id="contract-title" className="text-base font-semibold text-ink">Contract notes</h2><p className="mt-2 text-sm leading-6 text-muted">Metric names and denominators are inherited from the deterministic evaluator output. No combined quality score, missing denominator, raw response, prompt, corpus text, or hidden reasoning is inferred here.</p><div className="mt-4 text-xs text-muted">Schema <span className="font-mono">{artifact.schema_version}</span> · Verification text remains visible alongside color.</div></section>
      </div>
    </EvidenceLayout>
  );
}

export function MetricTable({ artifact }: { artifact: PublicRunArtifact }) {
  return <div className="overflow-x-auto"><table className="data-table"><caption className="sr-only">Exact aggregate metric values</caption><thead><tr><th scope="col">Metric</th><th scope="col">Value</th></tr></thead><tbody>{Object.entries(artifact.metrics).map(([name, value]) => <tr key={name}><th scope="row">{humanizeMetricName(name)}</th><td className="font-mono">{formatMetricValue(value)}</td></tr>)}</tbody></table></div>;
}
