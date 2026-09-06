import Link from "next/link";

import { ArtifactBadges } from "@/components/evidence/evidence-badges";
import { MetricDelta } from "@/components/evidence/metric-delta";
import { PopulationCompatibilityBadge } from "@/components/evidence/population-compatibility-badge";
import { EvidenceLayout } from "@/components/evidence-layout";
import { LimitationsPanel } from "@/components/provenance-panel";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { formatMetricValue, humanizeLabel, humanizeMetricName } from "@/lib/evidence/format";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { buildFailureTransitions, hasRecordChange } from "@/lib/evidence/transitions";
import type { ComparisonBundle } from "@/lib/evidence/repository";

function formatNullable(value: number | null): string {
  return value === null ? "Not available" : formatMetricValue(value);
}

export function ComparisonDetail({ bundle }: { bundle: ComparisonBundle }) {
  const { comparison, baseline, candidate } = bundle;
  const transitions = buildFailureTransitions(baseline, candidate);
  const changedRecords = transitions.status === "AVAILABLE"
    ? transitions.rows.filter(hasRecordChange).length
    : null;
  const regressionCount = comparison.comparisons.filter((row) => row.status === "REGRESSION").length;
  const passCount = comparison.comparisons.filter((row) => row.status === "PASS").length;

  return (
    <EvidenceLayout>
      <div className="space-y-8">
        <nav aria-label="Breadcrumb" className="text-sm">
          <Link className="focus-ring rounded text-accent underline underline-offset-4 hover:no-underline" href="/">
            Evidence Console
          </Link>
          <span className="mx-2 text-muted" aria-hidden="true">/</span>
          <span className="font-mono text-xs text-muted">{comparison.artifact_id}</span>
        </nav>

        <section aria-labelledby="comparison-title" className="grid gap-6 lg:grid-cols-[1fr_300px] lg:items-end">
          <div>
            <p className="eyebrow">Comparison artifact · regression policy</p>
            <h1 id="comparison-title" className="mt-3 text-3xl font-semibold tracking-tight text-ink sm:text-4xl">
              {comparison.passed ? "Comparison passed" : "Regression detected"}
            </h1>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-muted">
              Candidate <span className="font-mono text-ink">{candidate.artifact_id}</span> is compared with reference <span className="font-mono text-ink">{baseline.artifact_id}</span> using the artifact-provided aggregate policy results.
            </p>
            <div className="mt-5"><ArtifactBadges artifact={comparison} /></div>
          </div>
          <div className="surface p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.1em] text-muted">Artifact ID</p>
            <p className="mt-2 break-all font-mono text-xs font-semibold text-ink">{comparison.artifact_id}</p>
            <p className="mt-4 text-xs leading-5 text-muted">Claim scope: {humanizeLabel(comparison.claim_scope)}.</p>
          </div>
        </section>

        <section className="grid gap-6 lg:grid-cols-2" aria-label="Comparison operands">
          <OperandCard label="Reference" artifactId={baseline.artifact_id} runId={baseline.run.run_id} />
          <OperandCard label="Candidate" artifactId={candidate.artifact_id} runId={candidate.run.run_id} />
        </section>

        <section className="surface p-5" aria-labelledby="population-title">
          <CardHeader><CardTitle id="population-title">Population compatibility</CardTitle></CardHeader>
          <PopulationCompatibilityBadge status={comparison.population_compatibility} />
          <p className="mt-3 text-sm leading-6 text-muted">Population compatibility: {comparison.population_compatibility}</p>
          <p className="mt-2 text-xs leading-5 text-muted">Dataset, protocol, top-k, and evaluator-version metadata are matched before record transitions are derived.</p>
        </section>

        <section className="surface p-5" aria-labelledby="metric-comparison-title">
          <CardHeader>
            <div><p className="eyebrow">Aggregate policy result</p><CardTitle id="metric-comparison-title">Metric comparison</CardTitle></div>
            <span className="text-xs text-muted">{regressionCount} regression · {passCount} pass</span>
          </CardHeader>
          <Table className="min-w-[760px]" containerProps={{ tabIndex: 0, role: "region", "aria-label": "Metric comparison table" }}>
              <caption className="sr-only">Reference and candidate metric comparison</caption>
              <TableHeader><TableRow><TableHead>Metric</TableHead><TableHead>Reference</TableHead><TableHead>Candidate</TableHead><TableHead>Delta</TableHead><TableHead>Direction</TableHead><TableHead>Result</TableHead></TableRow></TableHeader>
              <TableBody>
                {comparison.comparisons.map((row) => (
                  <TableRow key={row.metric_name}>
                    <th scope="row">{humanizeMetricName(row.metric_name)}</th>
                    <TableCell className="font-mono">{formatNullable(row.baseline_value)}</TableCell>
                    <TableCell className="font-mono">{formatNullable(row.candidate_value)}</TableCell>
                    <TableCell><MetricDelta delta={row.delta} direction={row.direction} status={row.status} /></TableCell>
                    <TableCell>{row.direction === "higher_is_better" ? "Higher is better" : "Lower is better"}</TableCell>
                    <TableCell>
                      <span className="font-semibold">{row.status === "REGRESSION" ? "Regression" : row.status === "PASS" ? "Within allowance" : "Missing"}</span>
                      <span className="mt-1 block text-xs leading-5 text-muted">{row.reason}</span>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
          </Table>
        </section>

        <section className="surface p-5" aria-labelledby="record-change-title">
          <CardHeader><CardTitle id="record-change-title">Record-change summary</CardTitle><span className="text-xs text-muted">{transitions.status === "AVAILABLE" ? `${transitions.rows.length} matched records` : "Unavailable"}</span></CardHeader>
          <p className="text-sm leading-6 text-muted">{changedRecords === null ? "Record-level comparison unavailable." : `${changedRecords} matched records have a category transition or metric delta. Category transitions remain separate from aggregate regression statuses.`}</p>
          <Link className="focus-ring mt-4 inline-flex rounded text-sm font-semibold text-accent underline underline-offset-4 hover:no-underline" href={`/comparisons/${comparison.artifact_id}/failures/`}>Explore record changes <span aria-hidden="true">→</span></Link>
        </section>

        <LimitationsPanel limitations={comparison.limitations} />
        <section className="surface p-5" aria-labelledby="contract-title">
          <h2 id="contract-title" className="text-base font-semibold text-ink">Interpretation boundary</h2>
          <p className="mt-2 text-sm leading-6 text-muted">Synthetic same-population regression demonstration; not a benchmark or model-superiority result.</p>
          <p className="mt-2 text-xs leading-5 text-muted">Status and reason text are sourced from the deterministic comparison artifact. No statistical significance or record-level regression policy is inferred.</p>
        </section>
      </div>
    </EvidenceLayout>
  );
}

function OperandCard({ label, artifactId, runId }: { label: string; artifactId: string; runId: string | null }) {
  return (
    <Card className="p-5">
      <CardHeader><CardTitle>{label} run</CardTitle></CardHeader>
      <Link className="focus-ring break-all rounded font-mono text-xs font-semibold text-accent underline underline-offset-4 hover:no-underline" href={`/runs/${artifactId}`}>{artifactId}</Link>
      <p className="mt-3 text-xs text-muted">Run ID: <span className="font-mono">{runId ?? "Not included"}</span></p>
    </Card>
  );
}
