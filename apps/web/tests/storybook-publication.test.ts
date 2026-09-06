import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const publicConfigPath = path.join(process.cwd(), ".storybook-public", "main.ts");
const publicManifestPath = path.join(process.cwd(), "storybook.public.json");
const pagesBuildScriptPath = path.join(process.cwd(), "scripts", "build-pages.mjs");

const expectedTitles = [
  "Foundations/Canvas",
  "Primitives/Button",
  "Primitives/Badge",
  "Primitives/Card",
  "Primitives/Table",
  "Evidence/Claim Badges",
  "Evidence/Population Compatibility",
  "Evidence/Regression",
  "Evidence/Empty States",
  "Comparison/Metric Delta",
  "Patterns/Metric Stat",
  "Patterns/Provenance",
];

describe("public Storybook publication boundary", () => {
  it("uses an explicit public-story allowlist instead of the internal story tree", () => {
    expect(fs.existsSync(publicConfigPath)).toBe(true);

    const config = fs.readFileSync(publicConfigPath, "utf8");
    expect(config).toContain("../src/stories/public/**/*.public.stories.@(ts|tsx)");
    expect(config).not.toContain("../src/stories/**/*.stories.@(ts|tsx)");
  });

  it("publishes only the exact curated title allowlist", () => {
    expect(fs.existsSync(publicManifestPath)).toBe(true);

    const manifest = JSON.parse(fs.readFileSync(publicManifestPath, "utf8")) as { titles?: unknown };
    expect(manifest.titles).toEqual(expectedTitles);
    expect(new Set(manifest.titles as string[]).size).toBe(expectedTitles.length);
    expect((manifest.titles as string[]).some((title) => /^(Internal|Debug)\//.test(title))).toBe(false);
  });

  it("assembles the verified public Storybook into the Pages output", () => {
    const script = fs.readFileSync(pagesBuildScriptPath, "utf8");

    expect(script).toContain('GITHUB_PAGES: "true"');
    expect(script).toContain('"storybook:build:public"');
    expect(script).toContain("verify-public-storybook.mjs");
    expect(script).toContain("storybook-public-static");
    expect(script).toContain('"out", "storybook"');
    expect(script).toContain("cpSync");
  });
});
