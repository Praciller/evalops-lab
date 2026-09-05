import { defineConfig, devices } from "@playwright/test";

const pagesMode = process.env.PAGES_MODE === "true";
const appBasePath = pagesMode ? "/evalops-lab" : "";
const localPort = pagesMode ? 4174 : 4173;
const localBaseURL = `http://127.0.0.1:${localPort}${appBasePath}`;

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: `${localBaseURL}/`,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  expect: {
    toHaveScreenshot: { animations: "disabled", maxDiffPixelRatio: 0.03 },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: pagesMode ? "npm run start:pages" : "npm run start:static",
    url: `${localBaseURL}/`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
  snapshotPathTemplate: "{testDir}/__screenshots__/{arg}{ext}",
});
