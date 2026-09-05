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
});
