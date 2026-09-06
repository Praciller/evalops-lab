import type { ComparisonCatalogItem, RunCatalogItem } from "./catalog";
import type { PublicArtifactSummary } from "./schemas";

export type FilterKey = "verification" | "data" | "scope" | "population" | "result";

export type RunFilterState = {
  verification?: RunCatalogItem["verification_status"];
  data?: RunCatalogItem["data_kind"];
  scope?: RunCatalogItem["claim_scope"];
};

export type ComparisonFilterState = RunFilterState & {
  population?: ComparisonCatalogItem["population_compatibility"];
  result?: "PASS" | "REGRESSION";
};

type ClaimFilterable = Pick<RunCatalogItem, "verification_status" | "data_kind" | "claim_scope">;

const FILTER_VALUES: Record<FilterKey, readonly string[]> = {
  verification: ["VERIFIED", "PARTIAL", "UNVERIFIED", "NOT_RUN"],
  data: ["SYNTHETIC_FIXTURE", "CURATED_DATASET", "OFFICIAL_BENCHMARK"],
  scope: ["INTEGRATION_ONLY", "PROTOCOL_SPECIFIC", "BENCHMARK_RESULT"],
  population: ["MATCHED", "UNVERIFIED", "INCOMPATIBLE"],
  result: ["PASS", "REGRESSION"],
};

function parseSingleFilter<T extends string>(params: URLSearchParams, key: FilterKey, values: readonly T[]): T | undefined {
  const rawValues = params.getAll(key);
  if (rawValues.length !== 1 || !values.includes(rawValues[0] as T)) return undefined;
  return rawValues[0] as T;
}

export function parseRunFilters(params: URLSearchParams): RunFilterState {
  const filters: RunFilterState = {};
  const verification = parseSingleFilter(params, "verification", FILTER_VALUES.verification);
  const data = parseSingleFilter(params, "data", FILTER_VALUES.data);
  const scope = parseSingleFilter(params, "scope", FILTER_VALUES.scope);
  if (verification) filters.verification = verification as PublicArtifactSummary["verification_status"];
  if (data) filters.data = data as PublicArtifactSummary["data_kind"];
  if (scope) filters.scope = scope as PublicArtifactSummary["claim_scope"];
  return filters;
}

export function parseComparisonFilters(params: URLSearchParams): ComparisonFilterState {
  return {
    ...parseRunFilters(params),
    ...(parseSingleFilter(params, "population", FILTER_VALUES.population)
      ? { population: parseSingleFilter(params, "population", FILTER_VALUES.population) as ComparisonCatalogItem["population_compatibility"] }
      : {}),
    ...(parseSingleFilter(params, "result", FILTER_VALUES.result)
      ? { result: parseSingleFilter(params, "result", FILTER_VALUES.result) as "PASS" | "REGRESSION" }
      : {}),
  };
}

export function withFilter(params: URLSearchParams, key: FilterKey, value: string | null): string {
  const next = new URLSearchParams(params);
  next.delete(key);
  if (value !== null && FILTER_VALUES[key].includes(value)) next.set(key, value);
  return next.toString();
}

export function matchesRunFilters(item: ClaimFilterable, filters: RunFilterState): boolean {
  return (
    (!filters.verification || item.verification_status === filters.verification) &&
    (!filters.data || item.data_kind === filters.data) &&
    (!filters.scope || item.claim_scope === filters.scope)
  );
}

export function matchesComparisonFilters(
  item: ComparisonCatalogItem,
  filters: ComparisonFilterState,
): boolean {
  return (
    matchesRunFilters(item, filters) &&
    (!filters.population || item.population_compatibility === filters.population) &&
    (!filters.result || item.result === filters.result)
  );
}
