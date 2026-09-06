import Link from "next/link";

import { ArtifactBadges } from "@/components/evidence/evidence-badges";
import { EvidenceLayout } from "@/components/evidence-layout";
import { MetricStat } from "@/components/evidence/metric-stat";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatMetricValue, humanizeLabel, humanizeMetricName } from "@/lib/evidence/format";
import { getApprovedComparisonBundles, getApprovedRunArtifacts, getEvidenceIndex } from "@/lib/evidence/repository";

export function Overview() {
  const index = getEvidenceIndex();
  const runs = getApprovedRunArtifacts(index);
  const comparisons = getApprovedComparisonBundles(index);
  const headlineMetrics = runs.flatMap((run) =>
    Object.entries(run.metrics).slice(0, 3).map(([name, value]) => ({
      label: name,
      value,
      context: `${run.run.dataset_name} · ${run.run.run_id}`,
    })),
  );

  return (
    <EvidenceLayout>
      <div className="space-y-8">
        <section className="grid gap-6 lg:grid-cols-[1fr_300px] lg:items-end" aria-labelledby="overview-title">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-accent">Public evaluation evidence</p>
            <h1 id="overview-title" className="mt-3 max-w-3xl text-3xl font-semibold tracking-tight text-ink sm:text-4xl">Evidence Console</h1>
            <p className="mt-4 max-w-3xl text-base leading-7 text-muted">A calm, inspectable view of explicitly approved evaluation artifacts. Metrics retain their dataset, run, and claim boundaries.</p>
          </div>
          <div className="surface p-4 text-sm leading-6 text-muted"><strong className="text-ink">Read-only boundary.</strong> This static site does not run evaluators, call model providers, fetch data, or expose raw responses.</div>
        </section>

        <section className="grid gap-3 sm:grid-cols-3" aria-label="Evidence catalog summary">
          <SummaryCard label="Approved artifacts" value={String(index.artifacts.length)} detail="Explicit index membership" />
          <SummaryCard label="Run artifacts" value={String(runs.length)} detail="Available for inspection" />
          <SummaryCard label="Catalog state" value="Allowlisted" detail="Public Evidence Contract V1" />
        </section>

        <section aria-labelledby="headline-metrics-title">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
            <div><p className="eyebrow">No universal score</p><h2 id="headline-metrics-title" className="section-title">Headline metrics</h2></div>
            <p className="text-xs text-muted">Each value stays attached to its named run.</p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{headlineMetrics.map((metric) => <MetricStat key={`${metric.context}-${metric.label}`} {...metric} />)}</div>
        </section>

        <section aria-labelledby="runs-title">
          <CatalogSectionHeader eyebrow="Approved evidence" title="Run artifacts" href="/runs/" linkLabel="Browse all runs" id="runs-title" />
          <Card className="overflow-hidden">
            <Table>
              <caption className="sr-only">Approved EvalOps run artifacts</caption>
              <TableHeader><TableRow><TableHead>Artifact</TableHead><TableHead>Dataset</TableHead><TableHead>Claim dimensions</TableHead><TableHead>Metrics</TableHead><TableHead><span className="sr-only">Inspect</span></TableHead></TableRow></TableHeader>
              <TableBody>
                {runs.map((run) => (
                  <TableRow key={run.artifact_id}>
                    <th scope="row"><Link className="focus-ring rounded font-mono text-xs font-semibold text-accent underline-offset-4 hover:underline" href={`/runs/${run.artifact_id}`}>{run.artifact_id}</Link><span className="mt-1 block text-xs font-normal text-muted">{humanizeLabel(run.run.evaluation_type)}</span></th>
                    <TableCell><span className="font-medium">{run.run.dataset_name}</span><span className="mt-1 block text-xs text-muted">{run.run.dataset_version}</span></TableCell>
                    <TableCell><ArtifactBadges artifact={run} /></TableCell>
                    <TableCell><div className="space-y-1 text-xs">{Object.entries(run.metrics).slice(0, 3).map(([key, value]) => <div key={key}><span className="text-muted">{humanizeMetricName(key)}</span> <span className="font-mono font-semibold">{formatMetricValue(value)}</span></div>)}</div></TableCell>
                    <TableCell><Link className="focus-ring inline-flex rounded-md text-sm font-semibold text-accent underline-offset-4 hover:underline" href={`/runs/${run.artifact_id}`}>Inspect <span aria-hidden="true">→</span></Link></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        </section>

        <section aria-labelledby="comparisons-title">
          <CatalogSectionHeader eyebrow="Regression evidence" title="Regression evidence" href="/comparisons/" linkLabel="Browse all comparisons" id="comparisons-title" />
          <div className="grid gap-4">
            {comparisons.map(({ comparison, baseline, candidate }) => {
              const regressionCount = comparison.comparisons.filter((row) => row.status === "REGRESSION").length;
              const passCount = comparison.comparisons.filter((row) => row.status === "PASS").length;
              return (
                <Card className="p-5" key={comparison.artifact_id}>
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div><Link className="focus-ring rounded font-mono text-sm font-semibold text-accent underline underline-offset-4 hover:no-underline" href={`/comparisons/${comparison.artifact_id}`}>{comparison.artifact_id}</Link><p className="mt-2 text-sm text-muted">Synthetic same-population regression demonstration; not a benchmark or model-superiority result.</p></div>
                    <span className={comparison.passed ? "font-semibold text-success" : "font-semibold text-danger"}>{comparison.passed ? "Comparison passed" : "Regression detected"}</span>
                  </div>
                  <div className="mt-4 grid gap-3 text-sm sm:grid-cols-3"><div><p className="text-xs uppercase tracking-[0.1em] text-muted">Reference</p><Link className="focus-ring rounded font-mono text-xs text-accent underline underline-offset-4 hover:no-underline" href={`/runs/${baseline.artifact_id}`}>{baseline.artifact_id}</Link></div><div><p className="text-xs uppercase tracking-[0.1em] text-muted">Candidate</p><Link className="focus-ring rounded font-mono text-xs text-accent underline underline-offset-4 hover:no-underline" href={`/runs/${candidate.artifact_id}`}>{candidate.artifact_id}</Link></div><div><p className="text-xs uppercase tracking-[0.1em] text-muted">Metrics</p><span className="text-muted">{regressionCount} regression · {passCount} pass · </span><span className="font-semibold text-success">{comparison.population_compatibility}</span></div></div>
                  <div className="mt-4"><ArtifactBadges artifact={comparison} /></div>
                </Card>
              );
            })}
          </div>
        </section>

        <section className="grid gap-6 lg:grid-cols-2" aria-labelledby="boundary-title">
          <Card className="p-5"><CardHeader><CardTitle id="boundary-title">Interpretation boundary</CardTitle></CardHeader><p className="text-sm leading-6 text-muted">These artifacts are safe public evidence, not a universal model-quality ranking. Synthetic fixtures support integration claims only. A benchmark-shaped fixture is labeled as synthetic and must not be read as an official benchmark result.</p></Card>
          <Card className="p-5"><CardHeader><CardTitle>Provenance and limitations</CardTitle></CardHeader><ul className="space-y-2 text-sm leading-6 text-muted"><li>• The index is an explicit allowlist; no directory scan is used.</li><li>• Metrics preserve their <span className="font-mono">k</span> and run context.</li><li>• Detail pages expose only contract-approved metadata and evidence.</li></ul></Card>
        </section>
      </div>
    </EvidenceLayout>
  );
}

function CatalogSectionHeader({ eyebrow, title, href, linkLabel, id }: { eyebrow: string; title: string; href: string; linkLabel: string; id: string }) {
  return <div className="mb-4 flex flex-wrap items-end justify-between gap-3"><div><p className="eyebrow">{eyebrow}</p><h2 id={id} className="section-title">{title}</h2></div><Link className="focus-ring rounded text-sm font-semibold text-accent underline-offset-4 hover:underline" href={href}>{linkLabel} <span aria-hidden="true">→</span></Link></div>;
}

function SummaryCard({ label, value, detail }: { label: string; value: string; detail: string }) {
  return <Card className="p-4"><p className="text-xs font-semibold uppercase tracking-[0.1em] text-muted">{label}</p><p className="mt-2 text-xl font-semibold text-ink">{value}</p><p className="mt-1 text-xs text-muted">{detail}</p></Card>;
}
