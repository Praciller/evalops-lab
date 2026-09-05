import { Badge } from "@/components/ui/badge";
import type {
  PublicArtifactSummary,
  PublicComparisonArtifact,
  PublicRunArtifact,
} from "@/lib/evidence/schemas";

type ClaimArtifact = PublicRunArtifact | PublicComparisonArtifact | PublicArtifactSummary;
type VerificationStatus = ClaimArtifact["verification_status"];
type DataKind = ClaimArtifact["data_kind"];
type ClaimScope = ClaimArtifact["claim_scope"];

const verificationStyles: Record<VerificationStatus, string> = {
  VERIFIED: "badge-verified",
  PARTIAL: "badge-partial",
  UNVERIFIED: "badge-unverified",
  NOT_RUN: "badge-not-run",
};

const dataKindStyles: Record<DataKind, string> = {
  SYNTHETIC_FIXTURE: "badge-data-synthetic",
  CURATED_DATASET: "badge-data-curated",
  OFFICIAL_BENCHMARK: "badge-data-official",
};

const claimScopeStyles: Record<ClaimScope, string> = {
  INTEGRATION_ONLY: "badge-scope",
  PROTOCOL_SPECIFIC: "badge-scope",
  BENCHMARK_RESULT: "badge-scope",
};

export function VerificationBadge({ status }: { status: VerificationStatus }) {
  return <Badge className={verificationStyles[status]}>Verification: {status}</Badge>;
}

export function DataKindBadge({ dataKind }: { dataKind: DataKind }) {
  return <Badge className={dataKindStyles[dataKind]}>Data: {dataKind}</Badge>;
}

export function ClaimScopeBadge({ scope }: { scope: ClaimScope }) {
  return <Badge className={claimScopeStyles[scope]}>Claim: {scope}</Badge>;
}

export function ArtifactBadges({ artifact }: { artifact: ClaimArtifact }) {
  return (
    <div className="flex flex-wrap gap-2" aria-label="Evidence claim dimensions">
      <VerificationBadge status={artifact.verification_status} />
      <DataKindBadge dataKind={artifact.data_kind} />
      <ClaimScopeBadge scope={artifact.claim_scope} />
    </div>
  );
}
