import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Overview } from "@/components/overview";
import { RunDetail } from "@/components/run-detail";
import { ArtifactBadges } from "@/components/status-badges";
import { getRunArtifact } from "@/lib/evidence/repository";

describe("Evidence Console components", () => {
  it("renders overview identity, catalog summary, and safe run links", () => {
    render(<Overview />);
    expect(screen.getByRole("heading", { name: "Evidence Console" })).toBeInTheDocument();
    expect(screen.getByText("Explicit index membership")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /demo-retrieval-fixture-v1/ })).toBeInTheDocument();
    expect(screen.getAllByText("SYNTHETIC_FIXTURE", { exact: false })).toHaveLength(2);
  });

  it("renders all three claim dimensions as text badges", () => {
    render(<ArtifactBadges artifact={getRunArtifact("demo-retrieval-fixture-v1")} />);
    expect(screen.getByText(/Verification: VERIFIED/i)).toBeInTheDocument();
    expect(screen.getByText(/Data: SYNTHETIC_FIXTURE/i)).toBeInTheDocument();
    expect(screen.getByText(/Claim: INTEGRATION_ONLY/i)).toBeInTheDocument();
  });

  it("renders a detail view without universal scores or raw internals", () => {
    render(<RunDetail artifact={getRunArtifact("demo-retrieval-fixture-v1")} />);
    expect(screen.getByRole("heading", { name: "retrieval-fixture" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Metrics" })).toBeInTheDocument();
    expect(screen.getByText(/No combined quality score/)).toBeInTheDocument();
    expect(screen.queryByText(/raw_response/i)).not.toBeInTheDocument();
  });
});
