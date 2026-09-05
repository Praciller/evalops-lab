import { humanizeMetricName, formatMetricValue } from "@/lib/evidence/format";
import { Card } from "@/components/ui/card";

export function MetricCard({
  name,
  value,
  context,
}: {
  name: string;
  value: number;
  context: string;
}) {
  return (
    <Card className="p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-muted">{humanizeMetricName(name)}</p>
      <p className="metric-value mt-2">{formatMetricValue(value)}</p>
      <p className="mt-2 text-xs text-muted">{context}</p>
    </Card>
  );
}
