import { RegressionIndicator } from "@/components/evidence/regression-indicator";
import type { PublicComparisonArtifact } from "@/lib/evidence/schemas";

type MetricDirection = PublicComparisonArtifact["comparisons"][number]["direction"];
type RegressionStatus = PublicComparisonArtifact["comparisons"][number]["status"];

export function MetricDelta({
  delta,
  direction,
  status,
}: {
  delta: number | null;
  direction: MetricDirection;
  status: RegressionStatus;
}) {
  const formattedDelta = delta === null ? "Unavailable" : `${delta >= 0 ? "+" : ""}${delta.toFixed(3)}`;
  const directionLabel = direction === "higher_is_better" ? "higher is better" : "lower is better";

  return (
    <span className="inline-flex items-center gap-2" title={`Metric direction: ${directionLabel}`}>
      <RegressionIndicator status={status} />
      <span className="technical">{formattedDelta}</span>
    </span>
  );
}
