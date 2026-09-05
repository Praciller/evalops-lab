"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { EvidenceLayout } from "@/components/evidence-layout";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { formatMetricValue, humanizeLabel, humanizeMetricName } from "@/lib/evidence/format";
import type { ComparisonBundle } from "@/lib/evidence/repository";
import {
  buildFailureTransitions,
  hasRecordChange,
  type FailureTransitionKind,
  type FailureTransitionRow,
} from "@/lib/evidence/transitions";

const transitionLabels: Record<FailureTransitionKind, string> = {
  STABLE_PASS: "Stable pass",
  INTRODUCED_FAILURE: "Introduced failure",
  RESOLVED_FAILURE: "Resolved failure",
  PERSISTENT_CATEGORY: "Persistent category",
  CHANGED_FAILURE_CATEGORY: "Changed failure category",
};

export function FailureExplorer({ bundle }: { bundle: ComparisonBundle }) {
  const transitionResult = buildFailureTransitions(bundle.baseline, bundle.candidate);
  if (transitionResult.status === "UNAVAILABLE") {
    return (
      <EvidenceLayout>
        <section className="surface border-danger/40 p-6" role="alert" aria-labelledby="unavailable-title">
          <p className="eyebrow text-danger">Evidence boundary</p>
          <h1 id="unavailable-title" className="mt-2 text-2xl font-semibold text-ink">Record-level comparison unavailable</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-muted">This comparison does not provide enough compatible public evidence to infer record transitions.</p>
        </section>
      </EvidenceLayout>
    );
  }

  return <AvailableExplorer bundle={bundle} rows={transitionResult.rows} />;
}

function AvailableExplorer({ bundle, rows }: { bundle: ComparisonBundle; rows: FailureTransitionRow[] }) {
  const [transition, setTransition] = useState<FailureTransitionKind | "ALL">("ALL");
  const [candidateCategory, setCandidateCategory] = useState("ALL");
  const [changedOnly, setChangedOnly] = useState(false);
  const [search, setSearch] = useState("");
  const categories = useMemo(
    () => [...new Set(rows.map((row) => row.candidateCategory))].sort(),
    [rows],
  );
  const filteredRows = rows.filter((row) => (
    (transition === "ALL" || row.kind === transition) &&
    (candidateCategory === "ALL" || row.candidateCategory === candidateCategory) &&
    (!changedOnly || hasRecordChange(row)) &&
    row.recordRef.toLowerCase().includes(search.toLowerCase())
  ));

  return (
    <EvidenceLayout>
      <div className="space-y-8">
        <nav aria-label="Breadcrumb" className="text-sm">
          <Link className="focus-ring rounded text-accent underline underline-offset-4 hover:no-underline" href={`/comparisons/${bundle.comparison.artifact_id}/`}>Comparison</Link>
          <span className="mx-2 text-muted" aria-hidden="true">/</span>
          <span className="font-mono text-xs text-muted">failures</span>
        </nav>
        <section aria-labelledby="explorer-title">
          <p className="eyebrow">Comparison-scoped evidence</p>
          <h1 id="explorer-title" className="mt-3 text-3xl font-semibold tracking-tight text-ink sm:text-4xl">Record change explorer</h1>
          <p className="mt-3 text-sm leading-6 text-muted">Reference → Candidate · {rows.length} matched records</p>
          <div className="mt-4 flex flex-wrap gap-3 text-sm">
            <Link className="focus-ring rounded text-accent underline underline-offset-4 hover:no-underline" href={`/runs/${bundle.baseline.artifact_id}/`}>Reference: {bundle.baseline.artifact_id}</Link>
            <Link className="focus-ring rounded text-accent underline underline-offset-4 hover:no-underline" href={`/runs/${bundle.candidate.artifact_id}/`}>Candidate: {bundle.candidate.artifact_id}</Link>
          </div>
        </section>

        <Card className="p-5">
          <CardHeader><CardTitle>Filter record changes</CardTitle><span className="text-xs text-muted">{filteredRows.length} shown</span></CardHeader>
          <div className="grid gap-4 md:grid-cols-3">
            <label className="grid gap-2 text-xs font-semibold text-muted" htmlFor="transition-filter">Transition<select id="transition-filter" className="control w-full" value={transition} onChange={(event) => setTransition(event.target.value as FailureTransitionKind | "ALL")}><option value="ALL">All transitions</option>{Object.entries(transitionLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            <label className="grid gap-2 text-xs font-semibold text-muted" htmlFor="category-filter">Candidate category<select id="category-filter" className="control w-full" value={candidateCategory} onChange={(event) => setCandidateCategory(event.target.value)}><option value="ALL">All categories</option>{categories.map((category) => <option key={category} value={category}>{humanizeLabel(category)}</option>)}</select></label>
            <label className="grid gap-2 text-xs font-semibold text-muted" htmlFor="record-search">Search record ID<input id="record-search" aria-label="Search record ID" className="control w-full" type="search" placeholder="THQA-004" value={search} onChange={(event) => setSearch(event.target.value)} /></label>
          </div>
          <label className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-ink" htmlFor="changed-only"><input id="changed-only" type="checkbox" checked={changedOnly} onChange={(event) => setChangedOnly(event.target.checked)} />Changed records only</label>
        </Card>

        <Card className="p-5">
          <div className="table-scroll" tabIndex={0} role="region" aria-label="Record change table">
            <table className="data-table min-w-[960px]">
              <caption className="sr-only">Record-level reference and candidate changes</caption>
              <thead><tr><th scope="col">Record ID</th><th scope="col">Transition</th><th scope="col">Reference category</th><th scope="col">Candidate category</th><th scope="col">Changed metrics</th><th scope="col">Evidence</th></tr></thead>
              <tbody>
                {filteredRows.map((row) => <TransitionRow key={row.recordRef} row={row} />)}
              </tbody>
            </table>
          </div>
          {!filteredRows.length ? <p className="empty-state mt-4">No record changes match the selected filters.</p> : null}
        </Card>
      </div>
    </EvidenceLayout>
  );
}

function TransitionRow({ row }: { row: FailureTransitionRow }) {
  return (
    <tr>
      <th scope="row" className="font-mono text-xs">{row.recordRef}</th>
      <td><span className={row.kind === "STABLE_PASS" ? "font-semibold text-success" : "font-semibold text-danger"}>{transitionLabels[row.kind]}</span></td>
      <td>{row.baselineCategory}</td>
      <td>{row.candidateCategory}</td>
      <td className="text-xs">{row.metricDeltas.length ? row.metricDeltas.map((delta) => <div key={delta.metricName}>{humanizeMetricName(delta.metricName)} {delta.delta === null ? "changed" : `${delta.delta > 0 ? "+" : ""}${formatMetricValue(delta.delta)}`}</div>) : "No metric delta"}</td>
      <td>
        <details>
          <summary className="focus-ring cursor-pointer rounded text-sm font-semibold text-accent">Inspect evidence</summary>
          <div className="mt-3 space-y-2 text-xs leading-5 text-muted">
            <p>Reference retrieved IDs: <span className="font-mono">{row.baselineRecord.retrieved_document_ids.join(", ") || "Not included"}</span></p>
            <p>Candidate retrieved IDs: <span className="font-mono">{row.candidateRecord.retrieved_document_ids.join(", ") || "Not included"}</span></p>
            <p>Relevant IDs: <span className="font-mono">{row.candidateRecord.relevant_document_ids.join(", ") || "Not included"}</span></p>
            <p>Reference metrics: <span className="font-mono">{JSON.stringify(row.baselineRecord.metrics)}</span></p>
            <p>Candidate metrics: <span className="font-mono">{JSON.stringify(row.candidateRecord.metrics)}</span></p>
          </div>
        </details>
      </td>
    </tr>
  );
}
