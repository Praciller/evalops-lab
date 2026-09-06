"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { FilterBar, type FilterOption } from "@/components/catalog/filter-bar";
import { EmptyState } from "@/components/evidence/empty-state";
import { ClaimScopeBadge, DataKindBadge, VerificationBadge } from "@/components/evidence/evidence-badges";
import { PopulationCompatibilityBadge } from "@/components/evidence/population-compatibility-badge";
import { RegressionIndicator } from "@/components/evidence/regression-indicator";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { ComparisonCatalogItem } from "@/lib/evidence/catalog";
import { matchesComparisonFilters, parseComparisonFilters, withFilter, type FilterKey } from "@/lib/evidence/filters";

const filterOptions: readonly FilterOption[] = [
  { key: "verification", label: "Verification", values: ["VERIFIED", "PARTIAL", "UNVERIFIED", "NOT_RUN"] },
  { key: "data", label: "Data kind", values: ["SYNTHETIC_FIXTURE", "CURATED_DATASET", "OFFICIAL_BENCHMARK"] },
  { key: "scope", label: "Claim scope", values: ["INTEGRATION_ONLY", "PROTOCOL_SPECIFIC", "BENCHMARK_RESULT"] },
  { key: "population", label: "Population", values: ["MATCHED", "UNVERIFIED", "INCOMPATIBLE"] },
  { key: "result", label: "Result", values: ["PASS", "REGRESSION"] },
];

export function ComparisonCatalog({ comparisons }: { comparisons: ComparisonCatalogItem[] }) {
  const pathname = usePathname() ?? "/comparisons/";
  const router = useRouter();
  const searchParams = useSearchParams();
  const params = new URLSearchParams(searchParams.toString());
  const filters = parseComparisonFilters(params);
  const filteredComparisons = comparisons.filter((comparison) => matchesComparisonFilters(comparison, filters));

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
      <section aria-labelledby="comparisons-title">
        <p className="eyebrow">Aggregate policy evidence</p>
        <h1 id="comparisons-title" className="section-title mt-2">Comparisons</h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-muted">Inspect validated baseline-to-candidate comparisons without inferring record-level outcomes from aggregate deltas.</p>
      </section>
      <FilterBar options={filterOptions} active={filters} onChange={changeFilter} onClear={(key) => changeFilter(key, null)} onClearAll={clearAll} />
      {filteredComparisons.length ? (
        <Table>
          <caption className="sr-only">Approved public comparison artifacts</caption>
          <TableHeader><TableRow><TableHead>Comparison</TableHead><TableHead>Operands</TableHead><TableHead>Claim dimensions</TableHead><TableHead>Compatibility</TableHead><TableHead>Result</TableHead><TableHead><span className="sr-only">Inspect</span></TableHead></TableRow></TableHeader>
          <TableBody>
            {filteredComparisons.map((comparison) => (
              <TableRow key={comparison.artifact_id}>
                <th scope="row" className="min-w-56 align-top"><Link className="focus-ring break-words rounded font-mono text-xs font-semibold text-accent underline-offset-4 hover:underline" href={`/comparisons/${comparison.artifact_id}/`}>{comparison.artifact_id}</Link></th>
                <TableCell className="align-top"><p className="text-xs text-muted">Reference</p><Link className="focus-ring break-words rounded font-mono text-xs text-accent underline-offset-4 hover:underline" href={`/runs/${comparison.baseline_artifact_id}/`}>{comparison.baseline_artifact_id}</Link><p className="mt-3 text-xs text-muted">Candidate</p><Link className="focus-ring break-words rounded font-mono text-xs text-accent underline-offset-4 hover:underline" href={`/runs/${comparison.candidate_artifact_id}/`}>{comparison.candidate_artifact_id}</Link></TableCell>
                <TableCell className="align-top"><div className="flex flex-wrap gap-2"><VerificationBadge status={comparison.verification_status} /><DataKindBadge dataKind={comparison.data_kind} /><ClaimScopeBadge scope={comparison.claim_scope} /></div></TableCell>
                <TableCell className="align-top"><PopulationCompatibilityBadge status={comparison.population_compatibility} /></TableCell>
                <TableCell className="align-top"><div className="flex flex-wrap items-center gap-2">{comparison.result ? <RegressionIndicator status={comparison.result} /> : <span className="badge badge-not-run">Unavailable</span>}<span className="text-xs text-muted">{comparison.regression_count} regression {comparison.regression_count === 1 ? "row" : "rows"}</span></div></TableCell>
                <TableCell className="align-top"><Link className="focus-ring inline-flex rounded-md text-sm font-semibold text-accent underline-offset-4 hover:underline" href={`/comparisons/${comparison.artifact_id}/`}>Inspect comparison <span aria-hidden="true">→</span></Link><Link className="focus-ring mt-2 inline-flex rounded-md text-sm font-semibold text-accent underline-offset-4 hover:underline" href={`/comparisons/${comparison.artifact_id}/failures/`}>Explore record changes</Link></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : <EmptyState kind={comparisons.length ? "no_results" : "no_artifacts"} />}
    </div>
  );
}
