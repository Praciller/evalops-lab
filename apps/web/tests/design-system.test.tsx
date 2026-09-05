import fs from "node:fs";
import path from "node:path";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

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
});
