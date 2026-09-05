export function humanizeMetricName(name: string): string {
  const atK = name.match(/^(.*)_at_(\d+)$/);
  const base = atK ? atK[1] : name;
  const pretty = base
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
  const normalized = pretty === "Ndcg" ? "nDCG" : pretty === "Mrr" ? "MRR" : pretty;
  return atK ? `${normalized}@${atK[2]}` : normalized;
}

export function formatMetricValue(value: number): string {
  return value.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
}

export function formatTimestamp(timestamp: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeZone: "UTC",
  }).format(new Date(timestamp));
}

export function humanizeLabel(value: string): string {
  return value
    .split("_")
    .map((part) => part.charAt(0) + part.slice(1).toLowerCase())
    .join(" ");
}
