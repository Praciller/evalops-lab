import { Card } from "@/components/ui/card";
import { formatMetricValue, humanizeMetricName } from "@/lib/evidence/format";

export function MetricStat({
  label,
  value,
  context,
}: {
  label: string;
  value: number;
  context?: string;
}) {
  return (
    <Card className="p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-muted">{humanizeMetricName(label)}</p>
      <p className="metric-value mt-2">{formatMetricValue(value)}</p>
      {context ? <p className="mt-2 text-xs text-muted">{context}</p> : null}
    </Card>
  );
}
