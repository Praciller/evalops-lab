import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const publicConfigPath = path.join(process.cwd(), ".storybook-public", "main.ts");

describe("public Storybook publication boundary", () => {
  it("uses an explicit public-story allowlist instead of the internal story tree", () => {
    expect(fs.existsSync(publicConfigPath)).toBe(true);

    const config = fs.readFileSync(publicConfigPath, "utf8");
    expect(config).toContain("../src/stories/public/**/*.public.stories.@(ts|tsx)");
    expect(config).not.toContain("../src/stories/**/*.stories.@(ts|tsx)");
  });
});
