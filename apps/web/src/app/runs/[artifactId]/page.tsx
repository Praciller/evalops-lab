import { RunDetail } from "@/components/run-detail";
import { getEvidenceIndex, getRunArtifact } from "@/lib/evidence/repository";

export const dynamicParams = false;

export function generateStaticParams() {
  return getEvidenceIndex().artifacts
    .filter((artifact) => artifact.artifact_type === "run")
    .map((artifact) => ({ artifactId: artifact.artifact_id }));
}

export default async function RunDetailPage({ params }: { params: Promise<{ artifactId: string }> }) {
  const { artifactId } = await params;
  return <RunDetail artifact={getRunArtifact(artifactId)} />;
}
