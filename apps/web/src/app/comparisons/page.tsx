import { Suspense } from "react";

import { ComparisonCatalog } from "@/components/catalog/comparison-catalog";
import { EvidenceLayout } from "@/components/evidence-layout";
import { getComparisonCatalogItems } from "@/lib/evidence/catalog";

export default function ComparisonsPage() {
  return (
    <EvidenceLayout>
      <Suspense fallback={<p className="text-sm text-muted">Loading comparison catalog…</p>}>
        <ComparisonCatalog comparisons={getComparisonCatalogItems()} />
      </Suspense>
    </EvidenceLayout>
  );
}
