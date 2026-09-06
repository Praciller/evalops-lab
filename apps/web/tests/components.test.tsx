import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { usePathname } from "next/navigation";

import { Overview } from "@/components/overview";
import { ComparisonDetail } from "@/components/comparison-detail";
import { FailureExplorer } from "@/components/failure-explorer";
import { RunDetail } from "@/components/run-detail";
import { ProductHeader } from "@/components/shell/product-header";
import { EvidenceLayout } from "@/components/evidence-layout";
import { ArtifactBadges } from "@/components/status-badges";
import { getComparisonBundle, getRunArtifact } from "@/lib/evidence/repository";

vi.mock("next/navigation", () => ({ usePathname: vi.fn() }));

const mockedUsePathname = vi.mocked(usePathname);

describe("Evidence Console components", () => {
  beforeEach(() => {
    mockedUsePathname.mockReturnValue("/");
  });

  it.each([
    ["/", "Overview"],
    ["/runs/demo-retrieval-fixture-v1/", "Runs"],
    ["/comparisons/demo-retrieval-regression-v1/", "Comparisons"],
  ])("marks %s as the active primary route", (pathname, activeLabel) => {
    mockedUsePathname.mockReturnValue(pathname);
    render(<ProductHeader storybookHref="/storybook/" />);

    expect(screen.getByRole("link", { name: activeLabel })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Storybook" })).not.toHaveAttribute("aria-current");
  });

  it("renders the complete product shell with a plain Storybook anchor and boundary footer", () => {
    render(
      <EvidenceLayout>
        <p>Test content</p>
      </EvidenceLayout>,
    );

    expect(screen.getByRole("link", { name: "Overview" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Runs" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Comparisons" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Storybook" })).toHaveAttribute("href", "/storybook/");
    expect(screen.getByRole("button", { name: /theme/i })).toBeInTheDocument();
    expect(screen.getByText("Public Evidence Contract V1 · explicit allowlist")).toBeInTheDocument();
    expect(screen.getByText("No runtime API · no inference · no raw corpus")).toBeInTheDocument();
  });

  it("renders overview identity, catalog summary, and safe run links", () => {
    render(<Overview />);
    expect(screen.getByRole("heading", { name: "Evidence Console" })).toBeInTheDocument();
    expect(screen.getByText("Explicit index membership")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /demo-retrieval-fixture-v1/ }).length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "Regression evidence" })).toBeInTheDocument();
    expect(screen.getAllByText("SYNTHETIC_FIXTURE", { exact: false })).toHaveLength(4);
  });

  it("renders comparison verdict, operand links, and metric statuses", () => {
    render(<ComparisonDetail bundle={getComparisonBundle("demo-retrieval-regression-v1")} />);
    expect(screen.getByRole("heading", { name: "Regression detected" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /demo-retrieval-reference-v1/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /demo-retrieval-fixture-v1/ })).toBeInTheDocument();
    expect(screen.getByText(/Population compatibility: MATCHED/i)).toBeInTheDocument();
    expect(screen.getAllByText(/REGRESSION/)).toHaveLength(4);
    expect(screen.getByText(/2 matched records have a category transition or metric delta/)).toBeInTheDocument();
  });

  it("adds a bounded regression evidence section to the overview", () => {
    render(<Overview />);
    expect(screen.getByRole("heading", { name: "Regression evidence" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /demo-retrieval-regression-v1/ })).toBeInTheDocument();
    expect(screen.getByText(/Synthetic same-population regression demonstration/i)).toBeInTheDocument();
  });

  it("renders introduced failure and persistent category without overstating abstention", () => {
    render(<FailureExplorer bundle={getComparisonBundle("demo-retrieval-regression-v1")} />);
    expect(screen.getByText("THQA-004")).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Introduced failure" })).toBeInTheDocument();
    expect(screen.getByText("THQA-002")).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Persistent category" })).toBeInTheDocument();
    expect(screen.queryByText(/persistent system failure/i)).not.toBeInTheDocument();
  });

  it("filters to changed records and supports record search", () => {
    render(<FailureExplorer bundle={getComparisonBundle("demo-retrieval-regression-v1")} />);
    fireEvent.click(screen.getByRole("checkbox", { name: "Changed records only" }));
    expect(screen.queryByText("THQA-001")).not.toBeInTheDocument();
    expect(screen.queryByText("THQA-002")).not.toBeInTheDocument();
    expect(screen.getByText("THQA-004")).toBeInTheDocument();
    expect(screen.getByText("THQA-005")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("searchbox", { name: "Search record ID" }), { target: { value: "THQA-004" } });
    expect(screen.getByText("THQA-004")).toBeInTheDocument();
    expect(screen.queryByText("THQA-005")).not.toBeInTheDocument();
  });

  it("keeps unchanged persistent categories visible when changed-only is disabled", () => {
    render(<FailureExplorer bundle={getComparisonBundle("demo-retrieval-regression-v1")} />);
    expect(screen.getByText("THQA-002")).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Persistent category" })).toBeInTheDocument();
  });

  it("renders an unavailable state instead of partially joining record populations", () => {
    const bundle = structuredClone(getComparisonBundle("demo-retrieval-regression-v1"));
    bundle.candidate.evidence.pop();
    render(<FailureExplorer bundle={bundle} />);
    expect(screen.getByRole("heading", { name: "Record-level comparison unavailable" })).toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: "Changed records only" })).not.toBeInTheDocument();
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
