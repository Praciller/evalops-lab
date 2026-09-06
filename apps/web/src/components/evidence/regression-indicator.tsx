import { Badge } from "@/components/ui/badge";
import type { PublicComparisonArtifact } from "@/lib/evidence/schemas";

type RegressionStatus = PublicComparisonArtifact["comparisons"][number]["status"];

const regressionStyles: Record<RegressionStatus, string> = {
  PASS: "badge-verified",
  REGRESSION: "badge-partial",
  MISSING: "badge-not-run",
};

export function RegressionIndicator({ status }: { status: RegressionStatus }) {
  return <Badge className={regressionStyles[status]}>{status}</Badge>;
}
