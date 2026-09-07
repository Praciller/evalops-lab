import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: "list",
  use: {
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  // Playwright E2E requires the server to already be running
  // (started by scripts/run_workspace_e2e_server.py)
  webServer: {
    command: `python ${process.cwd().replace(/\\/g, '/')}/../../scripts/run_workspace_e2e_server.py --port 18234 --nonce e2e-test-nonce`,
    url: "http://127.0.0.1:18234",
    timeout: 30000,
    reuseExistingServer: !process.env.CI,
    stdout: "pipe",
    stderr: "pipe",
  },
});
