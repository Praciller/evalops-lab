import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import {
  BASE_URL, GT_JSONL, PRED_JSONL, bootstrap, createWorkspace,
  noOverflow, runPair, uploadJsonl,
} from "./retrieval-helpers";

test("real JSONL upload → validated pair → COMPLETE → metrics survive reload", async ({ page }) => {
  const external: string[] = [];
  page.on("request", (request) => {
    if (!request.url().startsWith(BASE_URL) && !request.url().startsWith("data:")) {
      external.push(request.url());
    }
  });
  await bootstrap(page);
  await createWorkspace(page, "Synthetic retrieval happy path");
  await uploadJsonl(page, "retrieval_ground_truth", "truth.jsonl", GT_JSONL);
  await uploadJsonl(page, "retrieval_predictions", "predictions.jsonl", PRED_JSONL);
  await runPair(page);
  await expect(page.getByText("LOCAL EVIDENCE — Not published")).toBeVisible();
  await expect(page.getByText("Precision @2")).toBeVisible();
  await expect(page.getByText("Hit rate @2")).toBeVisible();
  const metric = await page.getByText("Precision @2").locator("..").innerText();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Evaluation result" })).toBeVisible();
  const reloaded = await page.getByText("Precision @2").locator("..").innerText();
  expect(reloaded).toBe(metric);
  await expect(page.getByText("LOCAL EVIDENCE — Not published")).toBeVisible();
  expect(external).toEqual([]);
});

test("Input, Review, Job, Result: responsive and WCAG axe matrix at 390/768/1280px", async ({
  page,
}) => {
  test.setTimeout(120000);
  await page.setViewportSize({ width: 390, height: 844 });
  await bootstrap(page);
  await createWorkspace(page, "Responsive retrieval fixture");

  async function checkScreen(name: string) {
    for (const width of [390, 768, 1280]) {
      await page.setViewportSize({ width, height: 850 });
      await noOverflow(page);
      const axe = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();
      const issues = axe.violations.map((v) => ({ rule: v.id, impact: v.impact }));
      expect(issues, `${name} at ${width}px must have no WCAG violations`).toEqual([]);
    }
    await page.setViewportSize({ width: 390, height: 844 });
  }

  await checkScreen("Inputs");
  await uploadJsonl(page, "retrieval_ground_truth", "truth.jsonl", GT_JSONL);
  await uploadJsonl(page, "retrieval_predictions", "pred.jsonl", PRED_JSONL);
  await page.getByRole("link", { name: "Continue to Runs" }).click();
  await page.locator("#top-k").fill("2");
  await page.getByRole("button", { name: "Validate & review" }).click();
  await expect(page.getByRole("heading", { name: "Review before evaluation" })).toBeVisible();
  await checkScreen("Run review");
  await page.getByRole("button", { name: "Run Evaluation" }).click();
  await expect(page.getByRole("heading", { name: "Evaluation progress" })).toBeVisible();
  await expect(page.locator(".status-text")).toHaveText("COMPLETE", { timeout: 15000 });
  await checkScreen("Job");
  await page.getByRole("link", { name: "View evaluation result" }).click();
  await expect(page.getByRole("heading", { name: "Evaluation result" })).toBeVisible();
  await checkScreen("Run result");
});
