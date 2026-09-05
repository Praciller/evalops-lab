import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import path from "node:path";

const screenshotsDir = path.resolve(process.cwd(), "../../docs/screenshots/evidence-console");
const desktopClip = { x: 0, y: 0, width: 1280, height: 720 };
const mobileClip = { x: 0, y: 0, width: 390, height: 844 };
const appBasePath = process.env.PAGES_MODE === "true" ? "/evalops-lab" : "";
const localPort = process.env.PAGES_MODE === "true" ? 4174 : 4173;
const homePath = appBasePath ? `${appBasePath}/` : "/";

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
  await expect(page).toHaveScreenshot("overview-mobile.png", { clip: mobileClip });
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
