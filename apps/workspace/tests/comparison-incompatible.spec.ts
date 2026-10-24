import { expect, Page, test } from "@playwright/test";
import {
  BASE_URL, GT_JSONL, PRED_JSONL, bootstrap, createWorkspace, uploadJsonl,
} from "./retrieval-helpers";

async function createRun(page: Page, k: number, groundTruthInputId?: string): Promise<string> {
  await page.getByRole("link", { name: "Runs", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Configure & review a run" })).toBeVisible();
  await page.locator("#top-k").fill(String(k));
  if (groundTruthInputId) {
    await page.locator("#truth-select").selectOption(groundTruthInputId);
  }
  await page.getByRole("button", { name: "Validate & review" }).click();
  await page.getByRole("button", { name: "Run Evaluation" }).click();
  await expect(page.locator(".status-text")).toHaveText("COMPLETE", { timeout: 20000 });
  await page.getByRole("link", { name: "View evaluation result" }).click();
  const runId = page.url().match(/\/runs\/(run-[0-9a-f]{32})/)?.[1];
  expect(runId).toBeTruthy();
  return runId!;
}

test("real incompatible k and ground-truth population fail canonical, exploratory never promotes", async ({ page }, testInfo) => {
  test.setTimeout(120000);
  const external: string[] = [];
  page.on("request", r => {
    if (!r.url().startsWith(BASE_URL) && !r.url().startsWith("data:")) external.push(r.url());
  });
  await bootstrap(page);
  const ws = await createWorkspace(page, `Phase 6.3 incompatible E2E retry ${testInfo.retry}`);
  await uploadJsonl(page, "retrieval_ground_truth", "truth.jsonl", GT_JSONL);
  await uploadJsonl(page, "retrieval_predictions", "predictions.jsonl", PRED_JSONL);
  const baseline = await createRun(page, 10);
  await page.getByRole("button", { name: "Set as workspace baseline" }).click();
  await expect(page.getByText("This completed run is the pinned workspace baseline.")).toBeVisible();
  const candidate = await createRun(page, 20);
  expect(candidate).not.toBe(baseline);
  await page.getByRole("link", { name: "Comparisons", exact: true }).click();
  await page.getByLabel("Completed candidate run").selectOption(candidate);
  await page.getByRole("button", { name: "Check & create canonical comparison" }).click();
  await expect(page.getByText(/Not comparable — canonical regression blocked/)).toBeVisible();
  await expect(page.getByText(/top_k/)).toBeVisible();
  await expect(page.getByText("No persisted comparisons yet.")).toBeVisible();

  page.once("dialog", async dialog => {
    expect(dialog.message()).toContain("ineligible for a public regression claim");
    await dialog.accept();
  });
  await page.getByRole("button", { name: "Create separate exploratory comparison" }).click();
  await expect(page.getByRole("heading", { name: "Comparison detail" })).toBeVisible();
  expect(page.url()).toContain(`/workspaces/${ws}/comparisons/`);
  await expect(page.getByText(/EXPLORATORY_ONLY — Not eligible for public regression claim/)).toBeVisible();
  await expect(page.getByRole("heading", { name: /Population compatibility — NON_COMPARABLE/ })).toBeVisible();

  // Independently prove that renamed metadata never overrides changed ground-truth content.
  await page.getByRole("link", { name: "Inputs", exact: true }).click();
  const changedTruth =
    '{"query_id":"q1","relevant_document_ids":["modified-relevance"]}\n' +
    '{"query_id":"q2","relevant_document_ids":["d2"]}\n';
  const changedTruthResponse = page.waitForResponse(response =>
    response.request().method() === "POST" &&
    response.url().endsWith(`/workspaces/${ws}/inputs/upload`) && response.ok()
  );
  await uploadJsonl(page, "retrieval_ground_truth", "changed-truth.jsonl", changedTruth);
  const registeredTruth = await (await changedTruthResponse).json() as { input_id: string };
  expect(registeredTruth.input_id).toMatch(/^input-[0-9a-f]{32}$/);
  const changed = await createRun(page, 10, registeredTruth.input_id);
  await page.getByRole("link", { name: "Comparisons", exact: true }).click();
  await page.getByLabel("Completed candidate run").selectOption(changed);
  await page.getByRole("button", { name: "Check & create canonical comparison" }).click();
  await expect(page.getByText(/ground_truth_population/)).toBeVisible();
  await expect(page.getByText(/Not comparable — canonical regression blocked/)).toBeVisible();
  await expect(page.getByText("EXPLORATORY_ONLY — Not publishable")).toBeVisible();
  expect(external).toEqual([]);
});
