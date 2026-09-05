import { Badge } from "@/components/ui/badge";
import type {
  PublicArtifactSummary,
  PublicComparisonArtifact,
  PublicRunArtifact,
} from "@/lib/evidence/schemas";

type ClaimArtifact = PublicRunArtifact | PublicComparisonArtifact | PublicArtifactSummary;

const verificationStyles: Record<ClaimArtifact["verification_status"], string> = {
  VERIFIED: "badge-verified",
  PARTIAL: "badge-partial",
  UNVERIFIED: "badge-unverified",
  NOT_RUN: "badge-not-run",
};

export function VerificationBadge({ status }: { status: ClaimArtifact["verification_status"] }) {
  return (
    <Badge className={verificationStyles[status]}>
      Verification: {status}
    </Badge>
  );
}

export function DataKindBadge({ dataKind }: { dataKind: ClaimArtifact["data_kind"] }) {
  return <Badge className="badge-data">Data: {dataKind}</Badge>;
}

export function ClaimScopeBadge({ scope }: { scope: ClaimArtifact["claim_scope"] }) {
  return <Badge className="badge-scope">Claim: {scope}</Badge>;
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
