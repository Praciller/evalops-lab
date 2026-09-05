import { ComparisonDetail } from "@/components/comparison-detail";
import { getComparisonBundle, getEvidenceIndex } from "@/lib/evidence/repository";

export const dynamicParams = false;

export function generateStaticParams() {
  return getEvidenceIndex().artifacts
    .filter((artifact) => artifact.artifact_type === "comparison")
    .map((artifact) => ({ artifactId: artifact.artifact_id }));
}

export default async function ComparisonPage({ params }: { params: Promise<{ artifactId: string }> }) {
  const { artifactId } = await params;
  return <ComparisonDetail bundle={getComparisonBundle(artifactId)} />;
}
