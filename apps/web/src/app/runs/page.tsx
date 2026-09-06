import { Suspense } from "react";

import { RunCatalog } from "@/components/catalog/run-catalog";
import { EvidenceLayout } from "@/components/evidence-layout";
import { getRunCatalogItems } from "@/lib/evidence/catalog";

export default function RunsPage() {
  return (
    <EvidenceLayout>
      <Suspense fallback={<p className="text-sm text-muted">Loading run catalog…</p>}>
        <RunCatalog runs={getRunCatalogItems()} />
      </Suspense>
    </EvidenceLayout>
  );
}
