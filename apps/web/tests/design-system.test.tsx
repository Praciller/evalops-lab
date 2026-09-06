import fs from "node:fs";
import path from "node:path";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  ClaimScopeBadge,
  DataKindBadge,
  VerificationBadge,
} from "@/components/evidence/evidence-badges";
import { EmptyState } from "@/components/evidence/empty-state";
import { MetricDelta } from "@/components/evidence/metric-delta";
import { PopulationCompatibilityBadge } from "@/components/evidence/population-compatibility-badge";
import { RegressionIndicator } from "@/components/evidence/regression-indicator";

const cssPath = path.join(process.cwd(), "src/app/globals.css");

describe("Evidence Console design system", () => {
  it("publishes the semantic token families used by production and Storybook", () => {
    const css = fs.readFileSync(cssPath, "utf8");

    expect(css).toContain("--color-accent:");
    expect(css).toContain("--color-line-strong:");
    expect(css).toContain("--space-md:");
    expect(css).toContain("--radius-md:");
    expect(css).toContain("--font-sans:");
    expect(css).toContain("--font-mono:");
  });

  it("reserves technical typography for evidence values", () => {
    render(
      <div>
        <p>Metric value</p>
        <span className="font-mono tabular-nums">0.97</span>
      </div>,
    );

    expect(screen.getByText("0.97")).toHaveClass("font-mono", "tabular-nums");
    expect(screen.getByText("Metric value")).not.toHaveClass("font-mono");
  });

  it("provides generic native primitives with accessible semantics", () => {
    render(
      <>
        <Button aria-label="Run evaluation" className="custom-button" disabled>
          Run
        </Button>
        <Input aria-label="Search evidence" />
        <Select aria-label="Choose view" defaultValue="overview">
          <option value="overview">Overview</option>
        </Select>
        <Separator />
        <Card className="custom-card">Card content</Card>
        <Badge className="custom-badge">Label</Badge>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Metric</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow>
              <TableCell>Hit rate</TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </>,
    );

    expect(screen.getByRole("button", { name: "Run evaluation" })).toHaveAttribute("type", "button");
    expect(screen.getByRole("button", { name: "Run evaluation" })).toBeDisabled();
    expect(screen.getByRole("textbox", { name: "Search evidence" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Choose view" })).toBeInTheDocument();
    expect(screen.getByRole("separator")).toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Metric" })).toBeInTheDocument();
    expect(screen.getByText("Card content")).toHaveClass("custom-card");
    expect(screen.getByText("Label")).toHaveClass("custom-badge");
  });

  it("maps every supported evidence value to a typed presentation", () => {
    render(
      <div>
        {(["VERIFIED", "PARTIAL", "UNVERIFIED", "NOT_RUN"] as const).map((status) => (
          <VerificationBadge key={status} status={status} />
        ))}
        {(["SYNTHETIC_FIXTURE", "CURATED_DATASET", "OFFICIAL_BENCHMARK"] as const).map((dataKind) => (
          <DataKindBadge key={dataKind} dataKind={dataKind} />
        ))}
        {(["INTEGRATION_ONLY", "PROTOCOL_SPECIFIC", "BENCHMARK_RESULT"] as const).map((scope) => (
          <ClaimScopeBadge key={scope} scope={scope} />
        ))}
        {(["MATCHED", "UNVERIFIED", "INCOMPATIBLE"] as const).map((status) => (
          <PopulationCompatibilityBadge key={status} status={status} />
        ))}
        {(["PASS", "REGRESSION", "MISSING"] as const).map((status) => (
          <RegressionIndicator key={status} status={status} />
        ))}
      </div>,
    );

    expect(screen.getByText("Verification: VERIFIED")).toBeInTheDocument();
    expect(screen.getByText("Verification: PARTIAL")).toBeInTheDocument();
    expect(screen.getByText("Verification: UNVERIFIED")).toBeInTheDocument();
    expect(screen.getByText("Verification: NOT_RUN")).toBeInTheDocument();
    expect(screen.getByText("Data: SYNTHETIC_FIXTURE")).toBeInTheDocument();
    expect(screen.getByText("Data: CURATED_DATASET")).toBeInTheDocument();
    expect(screen.getByText("Data: OFFICIAL_BENCHMARK")).toBeInTheDocument();
    expect(screen.getByText("Claim: INTEGRATION_ONLY")).toBeInTheDocument();
    expect(screen.getByText("Claim: PROTOCOL_SPECIFIC")).toBeInTheDocument();
    expect(screen.getByText("Claim: BENCHMARK_RESULT")).toBeInTheDocument();
    expect(screen.getByText("Population: MATCHED")).toBeInTheDocument();
    expect(screen.getByText("Population: UNVERIFIED")).toBeInTheDocument();
    expect(screen.getByText("Population: INCOMPATIBLE")).toBeInTheDocument();
    expect(screen.getByText("PASS")).toBeInTheDocument();
    expect(screen.getByText("REGRESSION")).toBeInTheDocument();
    expect(screen.getByText("MISSING")).toBeInTheDocument();
  });

  it("uses metric direction and status instead of the raw delta sign", () => {
    render(<MetricDelta delta={0.05} direction="lower_is_better" status="REGRESSION" />);

    expect(screen.getByText(/regression/i)).toBeInTheDocument();
    expect(screen.getByText("+0.050")).toBeInTheDocument();
  });

  it("provides safe empty-state vocabulary for unavailable evidence", () => {
    render(<EmptyState kind="comparison_unavailable" />);

    expect(screen.getByRole("heading", { name: "Comparison unavailable" })).toBeInTheDocument();
    expect(screen.getByText(/cannot be compared safely/i)).toBeInTheDocument();
  });
});
