import { Badge } from "@/components/ui/badge";
import type { PopulationCompatibility } from "@/lib/evidence/schemas";

const populationStyles: Record<PopulationCompatibility, string> = {
  MATCHED: "badge-verified",
  UNVERIFIED: "badge-partial",
  INCOMPATIBLE: "badge-unverified",
};

export function PopulationCompatibilityBadge({ status }: { status: PopulationCompatibility }) {
  return <Badge className={populationStyles[status]}>Population: {status}</Badge>;
}
