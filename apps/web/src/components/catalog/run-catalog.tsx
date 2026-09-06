"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { EmptyState } from "@/components/evidence/empty-state";
import { DataKindBadge, ClaimScopeBadge, VerificationBadge } from "@/components/evidence/evidence-badges";
import { FilterBar, type FilterOption } from "@/components/catalog/filter-bar";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { RunCatalogItem } from "@/lib/evidence/catalog";
import { formatMetricValue, humanizeLabel, humanizeMetricName } from "@/lib/evidence/format";
import { parseRunFilters, withFilter, type FilterKey } from "@/lib/evidence/filters";

const filterOptions: readonly FilterOption[] = [
  { key: "verification", label: "Verification", values: ["VERIFIED", "PARTIAL", "UNVERIFIED", "NOT_RUN"] },
  { key: "data", label: "Data kind", values: ["SYNTHETIC_FIXTURE", "CURATED_DATASET", "OFFICIAL_BENCHMARK"] },
  { key: "scope", label: "Claim scope", values: ["INTEGRATION_ONLY", "PROTOCOL_SPECIFIC", "BENCHMARK_RESULT"] },
];

export function RunCatalog({ runs }: { runs: RunCatalogItem[] }) {
  const pathname = usePathname() ?? "/runs/";
  const router = useRouter();
  const searchParams = useSearchParams();
  const params = new URLSearchParams(searchParams.toString());
  const filters = parseRunFilters(params);
  const filteredRuns = runs.filter((run) =>
    (!filters.verification || run.verification_status === filters.verification) &&
    (!filters.data || run.data_kind === filters.data) &&
    (!filters.scope || run.claim_scope === filters.scope),
  );

  function navigate(nextQuery: string) {
    router.push(nextQuery ? `${pathname}?${nextQuery}` : pathname, { scroll: false });
  }

  function changeFilter(key: FilterKey, value: string | null) {
    navigate(withFilter(params, key, value));
  }

  function clearAll() {
    let next = params;
    for (const option of filterOptions) next = new URLSearchParams(withFilter(next, option.key, null));
    navigate(next.toString());
  }

  return (
    <div className="space-y-6">
      <section aria-labelledby="runs-title">
        <p className="eyebrow">Explicit public catalog</p>
        <h1 id="runs-title" className="section-title mt-2">Runs</h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-muted">Inspect approved run summaries without turning the catalog into a universal scorecard.</p>
      </section>
      <FilterBar options={filterOptions} active={filters} onChange={changeFilter} onClear={(key) => changeFilter(key, null)} onClearAll={clearAll} />
      {filteredRuns.length ? (
        <Table>
          <caption className="sr-only">Approved public run artifacts</caption>
          <TableHeader><TableRow><TableHead>Artifact</TableHead><TableHead>Dataset / evaluation</TableHead><TableHead>Claim dimensions</TableHead><TableHead>Metrics</TableHead><TableHead><span className="sr-only">Inspect</span></TableHead></TableRow></TableHeader>
          <TableBody>
            {filteredRuns.map((run) => (
              <TableRow key={run.artifact_id}>
                <th scope="row" className="min-w-52 align-top">
                  <Link className="focus-ring break-words rounded font-mono text-xs font-semibold text-accent underline-offset-4 hover:underline" href={`/runs/${run.artifact_id}/`}>{run.artifact_id}</Link>
                  <span className="mt-1 block break-words text-xs font-normal text-muted">{run.run_id ?? "Run identity unavailable"}</span>
                </th>
                <TableCell className="align-top"><span className="block font-medium">{run.dataset_name ?? "Dataset unavailable"}</span><span className="mt-1 block text-xs text-muted">{run.evaluation_type ? humanizeLabel(run.evaluation_type) : "Evaluation unavailable"}</span></TableCell>
                <TableCell className="align-top"><div className="flex min-w-56 flex-wrap gap-2"><VerificationBadge status={run.verification_status} /><DataKindBadge dataKind={run.data_kind} /><ClaimScopeBadge scope={run.claim_scope} /></div></TableCell>
                <TableCell className="align-top"><div className="min-w-40 space-y-1 text-xs">{Object.entries(run.metrics).slice(0, 3).map(([name, value]) => <div key={name}><span className="text-muted">{humanizeMetricName(name)}</span> <span className="technical">{formatMetricValue(value)}</span></div>)}</div></TableCell>
                <TableCell className="align-top"><Link className="focus-ring inline-flex rounded-md text-sm font-semibold text-accent underline-offset-4 hover:underline" href={`/runs/${run.artifact_id}/`}>Inspect {run.artifact_id} <span aria-hidden="true">→</span></Link></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : <EmptyState kind="no_results" />}
    </div>
  );
}
