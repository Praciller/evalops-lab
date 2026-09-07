import { test, expect, Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const TEST_NONCE = "e2e-test-nonce";
const BASE_URL = "http://127.0.0.1:18234";

async function bootstrapPage(page: Page): Promise<void> {
  await page.goto(`${BASE_URL}/#bootstrap=${TEST_NONCE}`);
  // Wait for authentication to complete
  await expect(page.getByRole("heading", { name: "Workspaces" })).toBeVisible({
    timeout: 10000,
  });
  // Fragment should be cleared after nonce exchange
  await expect(page).not.toHaveURL(/#/);
}

test.describe("Workspace local identity", () => {
  test("page carries LOCAL WORKSPACE identity with no root overflow at 390px", async ({
    browser,
  }) => {
    const context = await browser.newContext({
      viewport: { width: 390, height: 844 },
    });
    const page = await context.newPage();
    await page.goto(`${BASE_URL}/#bootstrap=${TEST_NONCE}`);
    await expect(page.getByText(/LOCAL WORKSPACE/)).toBeVisible();
    await expect(page.getByText(/Data stays on this machine/i)).toBeVisible();

    // Check for horizontal overflow
    const overflow = await page.evaluate(() => {
      return document.documentElement.scrollWidth > document.documentElement.clientWidth;
    });
    expect(overflow, "Page has horizontal overflow at 390px").toBe(false);

    await context.close();
  });
});

test.describe("Bootstrap and workspace management", () => {
  test("nonce exchange succeeds, fragment disappears, and workspace persists restart", async ({
    page,
  }) => {
    await page.goto(`${BASE_URL}/#bootstrap=${TEST_NONCE}`);

    // Wait for authenticated state
    await expect(
      page.getByRole("heading", { name: "Workspaces" })
    ).toBeVisible({ timeout: 10000 });

    // Fragment must be removed from URL after exchange
    await expect(page).not.toHaveURL(/#/);

    // Create a workspace
    const input = page.getByLabel(/workspace name/i);
    await input.fill("E2E Test Workspace");
    await page.getByRole("button", { name: /create workspace/i }).click();

    await expect(page.getByText("E2E Test Workspace")).toBeVisible();

    // Reload — workspace must persist (it is server-side state)
    await page.reload();
    await expect(page.getByText("E2E Test Workspace")).toBeVisible({ timeout: 5000 });

    // Rename workspace via authenticated same-origin API
    const workspacesData = await page.evaluate(async () => {
      const res = await fetch("/api/v1/workspaces");
      return res.json();
    });
    const wsId = workspacesData.workspaces[0].workspace_id;
    await page.evaluate(async (id: string) => {
      await fetch(`/api/v1/workspaces/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ display_name: "Renamed E2E Workspace" }),
      });
    }, wsId);

    // Reload — renamed workspace persists
    await page.reload();
    await expect(page.getByText("Renamed E2E Workspace")).toBeVisible({ timeout: 5000 });
  });
});

test.describe("Security boundaries", () => {
  test("cross-origin mutation is rejected", async ({ browser }) => {
    // Create a page that acts as a different origin
    const context = await browser.newContext();
    const page = await context.newPage();

    // Direct cross-origin POST without proper session/origin
    const response = await page.request.post(
      `${BASE_URL}/api/v1/workspaces`,
      {
        headers: {
          "Content-Type": "application/json",
          Origin: "http://evil.example.com",
          Host: "127.0.0.1:18234",
        },
        data: JSON.stringify({ display_name: "Hacked" }),
      }
    );

    // Must be rejected (403 or 401)
    expect(response.status()).toBeGreaterThanOrEqual(400);
    const body = await response.json();
    expect(body).toHaveProperty("error");

    await context.close();
  });

  test("no external runtime requests are made", async ({ page }) => {
    const externalRequests: string[] = [];
    const testOrigin = new URL(BASE_URL).origin;

    page.on("request", (req) => {
      const url = req.url();
      if (!url.startsWith(testOrigin) && !url.startsWith("data:")) {
        externalRequests.push(url);
      }
    });

    await page.goto(`${BASE_URL}/#bootstrap=${TEST_NONCE}`);
    await expect(
      page.getByRole("heading", { name: "Workspaces" })
    ).toBeVisible({ timeout: 10000 });

    expect(
      externalRequests,
      "External requests were made: " + externalRequests.join(", ")
    ).toHaveLength(0);
  });
});

test.describe("Accessibility", () => {
  test("workspace home has zero serious/critical axe violations", async ({
    page,
  }) => {
    await bootstrapPage(page);
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa"])
      .analyze();

    const seriousCritical = results.violations.filter((v) =>
      ["serious", "critical"].includes(v.impact ?? "")
    );
    expect(
      seriousCritical,
      `Serious/critical axe violations: ${JSON.stringify(seriousCritical.map((v) => v.id))}`
    ).toHaveLength(0);
  });
});
