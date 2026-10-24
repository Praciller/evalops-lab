import { expect, Page, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import {
  BASE_URL, GT_JSONL, bootstrap, createWorkspace, noOverflow, uploadJsonl,
} from "./retrieval-helpers";

const BASE_PRED =
  '{"query_id":"q1","retrieved_document_ids":["d1","d3"]}\n' +
  '{"query_id":"q2","retrieved_document_ids":["missing"]}\n';
const CAND_PRED =
  '{"query_id":"q1","retrieved_document_ids":["missing"]}\n' +
  '{"query_id":"q2","retrieved_document_ids":["missing","d2"]}\n';

async function evaluate(page: Page, k: number, predictionInputId?: string): Promise<string> {
  await page.getByRole("link", { name: "Runs", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Configure & review a run" })).toBeVisible();
  await page.locator("#top-k").fill(String(k));
  if (predictionInputId) {
    await page.locator("#prediction-select").selectOption(predictionInputId);
  }
  await page.getByRole("button", { name: "Validate & review" }).click();
  await expect(page.getByRole("heading", { name: "Review before evaluation" })).toBeVisible();
  await page.getByRole("button", { name: "Run Evaluation" }).click();
  await expect(page.locator(".status-text")).toHaveText("COMPLETE", { timeout: 20000 });
  await page.getByRole("link", { name: "View evaluation result" }).click();
  await expect(page.getByRole("heading", { name: "Evaluation result" })).toBeVisible();
  const id = page.url().match(/\/runs\/(run-[a-f0-9]{32})/)?.[1];
  expect(id).toBeTruthy();
  return id!;
}

test("real compatible baseline and candidate keep immutable comparisons and private failure transitions", async ({ page }, testInfo) => {
  test.setTimeout(180000);
  const external: string[] = [];
  page.on("request", request => {
    if (!request.url().startsWith(BASE_URL) && !request.url().startsWith("data:")) {
      external.push(request.url());
    }
  });

  await bootstrap(page);
  const ws = await createWorkspace(page, `Phase 6.3 compatible E2E retry ${testInfo.retry}`);
  await uploadJsonl(page, "retrieval_ground_truth", "truth.jsonl", GT_JSONL);
  await uploadJsonl(page, "retrieval_predictions", "baseline.jsonl", BASE_PRED);
  const baselineId = await evaluate(page, 2);

  await page.getByRole("button", { name: "Set as workspace baseline" }).click();
  await expect(page.getByText("This completed run is the pinned workspace baseline.")).toBeVisible();

  await page.getByRole("link", { name: "Inputs", exact: true }).click();
  const candidateUploadResponse = page.waitForResponse(response =>
    response.request().method() === "POST" &&
    response.url().endsWith(`/workspaces/${ws}/inputs/upload`) && response.ok()
  );
  await uploadJsonl(page, "retrieval_predictions", "candidate.jsonl", CAND_PRED);
  const registeredCandidate = await (await candidateUploadResponse).json() as { input_id: string };
  expect(registeredCandidate.input_id).toMatch(/^input-[0-9a-f]{32}$/);
  const candidateId = await evaluate(page, 2, registeredCandidate.input_id);

  await page.getByRole("link", { name: "Comparisons", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Compare retrieval runs" })).toBeVisible();
  await page.getByLabel("Completed candidate run").selectOption(candidateId);
  await page.getByRole("button", { name: "Check & create canonical comparison" }).click();
  await expect(page.getByRole("heading", { name: "Comparison detail" })).toBeVisible();
  const comparisonId = page.url().match(/\/comparisons\/(comparison-[a-f0-9]{32})/)?.[1];
  expect(comparisonId).toBeTruthy();

  const compatibility = page.getByRole("heading", { name: /Population compatibility — COMPARABLE/ });
  const metrics = page.getByRole("heading", { name: "Fixed-policy metric comparison" });
  await expect(compatibility).toBeVisible();
  await expect(metrics).toBeVisible();
  const position = await page.evaluate(() => {
    const sections = [...document.querySelectorAll("section.surface")];
    return sections.map(section => section.querySelector("h3")?.textContent ?? "");
  });
  expect(position.findIndex(label => label.includes("Population compatibility")))
    .toBeLessThan(position.findIndex(label => label.includes("Fixed-policy metric comparison")));
  await expect(page.getByRole("cell", { name: "REGRESSION" }).first()).toBeVisible();

  for (const width of [390, 768, 1280]) {
    await page.setViewportSize({ width, height: 850 });
    await noOverflow(page);
    const result = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    expect(result.violations, `Comparison at ${width}px must have zero WCAG violations`).toEqual([]);
  }

  await page.getByRole("link", { name: "Inspect query-level failure transitions" }).click();
  await expect(page.getByRole("heading", { name: "Query-level transitions" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "REGRESSED" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "IMPROVED" })).toBeVisible();
  await page.getByLabel("Transition", { exact: true }).selectOption("REGRESSED");
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect(page.getByRole("rowheader", { name: "q1" })).toBeVisible();
  await expect(page.getByRole("rowheader", { name: "q2" })).toHaveCount(0);
  for (const width of [390, 768, 1280]) {
    await page.setViewportSize({ width, height: 850 });
    await noOverflow(page);
    const result = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    expect(result.violations, `Failure Explorer at ${width}px must have zero WCAG violations`).toEqual([]);
  }

  await page.goto(`${BASE_URL}/workspaces/${ws}/runs/${candidateId}`);
  await expect(page.getByRole("heading", { name: "Evaluation result" })).toBeVisible();
  page.once("dialog", async dialog => {
    expect(dialog.message()).toContain(baselineId);
    expect(dialog.message()).toContain(candidateId);
    await dialog.accept();
  });
  await page.getByRole("button", { name: "Replace baseline with this run" }).click();
  await expect(page.getByText(/Baseline pinned and verified/)).toBeVisible();
  await page.goto(`${BASE_URL}/workspaces/${ws}/comparisons/${comparisonId}`);
  await expect(page.getByRole("link", { name: baselineId })).toBeVisible();
  await expect(page.getByRole("link", { name: candidateId })).toBeVisible();
  expect(external).toEqual([]);
});
