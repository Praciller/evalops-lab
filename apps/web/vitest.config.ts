import path from "node:path";
import { defineConfig } from "vitest/config";

import { playwright } from "@vitest/browser-playwright";
import { storybookTest } from "@storybook/addon-vitest/vitest-plugin";

export default defineConfig({
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  test: {
    projects: [
      {
        extends: true,
        test: {
          name: "unit",
          environment: "jsdom",
          setupFiles: ["./tests/setup.ts"],
          include: ["tests/**/*.test.{ts,tsx}"],
          exclude: ["tests/e2e/**"],
        },
      },
      {
        extends: true,
        plugins: [
          storybookTest({
            configDir: path.resolve(__dirname, ".storybook"),
            initialGlobals: { colorScheme: "light" },
          }),
        ],
        test: {
          name: "storybook-light",
          setupFiles: ["./.storybook/vitest.setup.ts"],
          browser: {
            enabled: true,
            headless: true,
            provider: playwright({}),
            instances: [{ browser: "chromium" }],
          },
        },
      },
      {
        extends: true,
        plugins: [
          storybookTest({
            configDir: path.resolve(__dirname, ".storybook"),
            initialGlobals: { colorScheme: "dark" },
          }),
        ],
        test: {
          name: "storybook-dark",
          setupFiles: ["./.storybook/vitest.setup.ts"],
          browser: {
            enabled: true,
            headless: true,
            provider: playwright({}),
            instances: [{ browser: "chromium" }],
          },
        },
      },
    ],
  },
});
