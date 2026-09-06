import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import path from "node:path";

const screenshotsDir = path.resolve(process.cwd(), "../../docs/screenshots/evidence-console");
const desktopClip = { x: 0, y: 0, width: 1280, height: 720 };
const mobileClip = { x: 0, y: 0, width: 390, height: 844 };
const appBasePath = process.env.PAGES_MODE === "true" ? "/evalops-lab" : "";
const localPort = process.env.PAGES_MODE === "true" ? 4174 : 4173;
const homePath = appBasePath ? `${appBasePath}/` : "/";

async function tabUntilFocused(page: import("@playwright/test").Page, locator: import("@playwright/test").Locator, maxTabs = 20) {
  for (let index = 0; index < maxTabs; index += 1) {
    await page.keyboard.press("Tab");
    if (await locator.evaluate((element) => element === document.activeElement)) return true;
  }
  return false;
}

test("overview is accessible, local-only, and has a stable desktop visual", async ({ page }) => {
  const requests: string[] = [];
  page.on("request", (request) => requests.push(request.url()));
  await page.goto(homePath);
  await expect(page).toHaveTitle(/EvalOps Evidence Console/);
  await expect(page.getByRole("heading", { name: "Evidence Console" })).toBeVisible();
  await expect(page.getByText("SYNTHETIC_FIXTURE", { exact: false }).first()).toBeVisible();
  expect(requests.every((url) => url.startsWith(`http://127.0.0.1:${localPort}${appBasePath}/`) || url.startsWith("data:"))).toBe(true);
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
  await page.screenshot({ path: path.join(screenshotsDir, "overview-desktop.png"), fullPage: true });
  await expect(page).toHaveScreenshot("overview-desktop.png", { clip: desktopClip });
});

test("overview remains usable on mobile and keyboard focus is visible", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(homePath);
  await expect(page.getByRole("heading", { name: "Evidence Console" })).toBeVisible();
  const rootWidth = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(rootWidth.scrollWidth).toBeLessThanOrEqual(rootWidth.clientWidth);
  await page.evaluate(() => window.scrollTo(999, 0));
  expect(await page.evaluate(() => window.scrollX)).toBe(0);
  expect(await page.locator(".table-scroll").evaluate((element) => element.scrollWidth > element.clientWidth)).toBe(true);
  await page.keyboard.press("Tab");
  await expect(page.locator(":focus")).toHaveAttribute("href", `${appBasePath}/`);
  await page.screenshot({ path: path.join(screenshotsDir, "overview-mobile.png"), fullPage: true });
  await expect(page).toHaveScreenshot("overview-mobile.png", {
    clip: mobileClip,
    // Stable Linux CI capture measured 10,207 differing pixels on this fixed 390x844 clip.
    maxDiffPixels: 10_500,
  });
  await page.getByRole("button", { name: "Dark theme" }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  await expect(page.getByRole("button", { name: "Light theme" })).toBeVisible();
});

test("overview links to a static run detail with accessible evidence", async ({ page }) => {
  await page.goto(homePath);
  await page.getByRole("link", { name: /demo-retrieval-fixture-v1/ }).first().click();
  await expect(page).toHaveURL(/\/runs\/demo-retrieval-fixture-v1\/$/);
  await expect(page.getByRole("heading", { name: "retrieval-fixture" })).toBeVisible();
  await expect(page.getByText("No combined quality score")).toBeVisible();
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
  await page.screenshot({ path: path.join(screenshotsDir, "run-detail-desktop.png"), fullPage: true });
  await expect(page).toHaveScreenshot("run-detail-desktop.png", { clip: desktopClip });
});

test("comparison detail is accessible, local-only, and has a stable desktop visual", async ({ page }) => {
  const requests: string[] = [];
  page.on("request", (request) => requests.push(request.url()));
  await page.goto(`${appBasePath}/comparisons/demo-retrieval-regression-v1/`);
  await expect(page.getByRole("heading", { name: "Regression detected" })).toBeVisible();
  await expect(page.getByText("Population compatibility: MATCHED", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Explore record changes" })).toBeVisible();
  expect(requests.every((url) => url.startsWith(`http://127.0.0.1:${localPort}${appBasePath}/`) || url.startsWith("data:"))).toBe(true);
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
  await page.getByRole("button", { name: "Dark theme" }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  await expect(page.getByRole("button", { name: "Light theme" })).toBeVisible();
  await page.getByRole("button", { name: "Light theme" }).click();
  expect(await tabUntilFocused(page, page.locator('nav[aria-label="Breadcrumb"] a'))).toBe(true);
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await page.screenshot({ path: path.join(screenshotsDir, "comparison-desktop.png"), fullPage: true });
  await expect(page).toHaveScreenshot("comparison-desktop.png", { clip: desktopClip });
});

test("comparison detail remains usable on mobile without root overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${appBasePath}/comparisons/demo-retrieval-regression-v1/`);
  await expect(page.getByRole("heading", { name: "Regression detected" })).toBeVisible();
  const rootWidth = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(rootWidth.scrollWidth).toBeLessThanOrEqual(rootWidth.clientWidth);
  await page.evaluate(() => window.scrollTo(999, 0));
  expect(await page.evaluate(() => window.scrollX)).toBe(0);
  expect(await page.locator(".table-scroll").evaluate((element) => element.scrollWidth > element.clientWidth)).toBe(true);
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
  await page.screenshot({ path: path.join(screenshotsDir, "comparison-mobile.png"), fullPage: true });
  await expect(page).toHaveScreenshot("comparison-mobile.png", {
    clip: mobileClip,
    // Stable Linux CI capture measured 10,832 differing pixels on this fixed 390x844 clip.
    maxDiffPixels: 11_000,
  });
});

test("failure explorer is accessible, local-only, and has a stable desktop visual", async ({ page }) => {
  const requests: string[] = [];
  page.on("request", (request) => requests.push(request.url()));
  await page.goto(`${appBasePath}/comparisons/demo-retrieval-regression-v1/failures/`);
  await expect(page.getByRole("heading", { name: "Record change explorer" })).toBeVisible();
  await expect(page.getByText("Reference → Candidate · 5 matched records", { exact: true })).toBeVisible();
  await expect(page.getByText("Introduced failure", { exact: true }).last()).toBeVisible();
  expect(requests.every((url) => url.startsWith(`http://127.0.0.1:${localPort}${appBasePath}/`) || url.startsWith("data:"))).toBe(true);
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
  for (const control of [
    page.getByRole("combobox", { name: "Transition" }),
    page.getByRole("combobox", { name: "Candidate category" }),
    page.getByRole("searchbox", { name: "Search record ID" }),
    page.getByRole("checkbox", { name: "Changed records only" }),
  ]) {
    expect(await tabUntilFocused(page, control)).toBe(true);
  }
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await page.screenshot({ path: path.join(screenshotsDir, "failure-explorer-desktop.png"), fullPage: true });
  await expect(page).toHaveScreenshot("failure-explorer-desktop.png", { clip: desktopClip });
});

test("failure explorer supports changed-only filtering and mobile internal table scrolling", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${appBasePath}/comparisons/demo-retrieval-regression-v1/failures/`);
  await expect(page.getByRole("heading", { name: "Record change explorer" })).toBeVisible();
  await page.getByRole("checkbox", { name: "Changed records only" }).check();
  await expect(page.getByRole("cell", { name: "Introduced failure" })).toBeVisible();
  await expect(page.locator(".data-table tbody tr").filter({ hasText: "THQA-001" })).toHaveCount(0);
  await expect(page.locator(".data-table tbody tr").filter({ hasText: "THQA-005" })).toContainText("Stable pass");
  const rootWidth = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(rootWidth.scrollWidth).toBeLessThanOrEqual(rootWidth.clientWidth);
  await page.evaluate(() => window.scrollTo(999, 0));
  expect(await page.evaluate(() => window.scrollX)).toBe(0);
  expect(await page.locator(".table-scroll").evaluate((element) => element.scrollWidth > element.clientWidth)).toBe(true);
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
  await page.screenshot({ path: path.join(screenshotsDir, "failure-explorer-mobile.png"), fullPage: true });
  await expect(page).toHaveScreenshot("failure-explorer-mobile.png", { clip: mobileClip });
});

test("comparison journey stays inside static evidence routes", async ({ page }) => {
  await page.goto(homePath);
  await page.getByRole("link", { name: "demo-retrieval-regression-v1" }).click();
  await expect(page).toHaveURL(/\/comparisons\/demo-retrieval-regression-v1\/$/);
  await page.getByRole("link", { name: "Explore record changes" }).click();
  await expect(page).toHaveURL(/\/comparisons\/demo-retrieval-regression-v1\/failures\/$/);
  await page.getByRole("link", { name: /Reference: demo-retrieval-reference-v1/ }).click();
  await expect(page).toHaveURL(/\/runs\/demo-retrieval-reference-v1\/$/);
  await page.goto(`${appBasePath}/comparisons/demo-retrieval-regression-v1/`);
  await page.getByRole("link", { name: "demo-retrieval-fixture-v1" }).click();
  await expect(page).toHaveURL(/\/runs\/demo-retrieval-fixture-v1\/$/);
});

test("Pages output exposes only the curated public Storybook", async ({ page }) => {
  test.skip(process.env.PAGES_MODE !== "true", "public Storybook exists only in assembled Pages output");

  const requests: string[] = [];
  page.on("request", (request) => requests.push(request.url()));
  await page.goto(`${appBasePath}/storybook/`);
  await expect(page).toHaveTitle(/storybook/i);
  await expect(page.locator("#root")).toBeVisible();

  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
      await page.goto(`${appBasePath}/storybook/iframe.html?id=foundations-canvas--light&viewMode=story&globals=colorScheme:light`);
  await expect(page.locator("#storybook-root")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Evidence Console" })).toBeVisible();

  const rootWidth = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(rootWidth.scrollWidth).toBeLessThanOrEqual(rootWidth.clientWidth);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);

      await page.goto(`${appBasePath}/storybook/iframe.html?id=foundations-canvas--light&viewMode=story&globals=colorScheme:dark`);
  await expect(page.locator(".dark").first()).toBeVisible();
      await page.goto(`${appBasePath}/storybook/iframe.html?id=foundations-canvas--light&viewMode=story&globals=colorScheme:light`);
  await expect(page.locator(".dark")).toHaveCount(0);

  expect(requests.every((url) => url.startsWith(`http://127.0.0.1:${localPort}${appBasePath}/`) || url.startsWith("data:"))).toBe(true);
});
