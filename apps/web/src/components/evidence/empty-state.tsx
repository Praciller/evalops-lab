import { Card } from "@/components/ui/card";

type EmptyStateKind =
  | "no_artifacts"
  | "no_results"
  | "comparison_unavailable"
  | "unsupported"
  | "invalid_artifact";

const emptyStates: Record<EmptyStateKind, { title: string; description: string }> = {
  no_artifacts: { title: "No public artifacts", description: "The explicit public evidence catalog has no artifacts to show." },
  no_results: { title: "No matching results", description: "No evidence matches the selected filters." },
  comparison_unavailable: { title: "Comparison unavailable", description: "These populations cannot be compared safely." },
  unsupported: { title: "Unsupported evidence", description: "This evidence shape is not supported by the public contract." },
  invalid_artifact: { title: "Evidence unavailable", description: "The artifact did not pass the public evidence contract." },
};

export function EmptyState({ kind }: { kind: EmptyStateKind }) {
  const state = emptyStates[kind];
  return (
    <Card className="empty-state" role="status">
      <h2 className="text-base font-semibold text-ink">{state.title}</h2>
      <p className="mt-2">{state.description}</p>
    </Card>
  );
}
