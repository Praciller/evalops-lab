import { expect, Page } from "@playwright/test";

export const BASE_URL = "http://127.0.0.1:18234";
export const NONCE = "e2e-test-nonce";
export const GT_JSONL =
  '{"query_id":"q1","relevant_document_ids":["d1"]}\n' +
  '{"query_id":"q2","relevant_document_ids":["d2"]}\n';
export const PRED_JSONL =
  '{"query_id":"q1","retrieved_document_ids":["d1","d3"]}\n' +
  '{"query_id":"q2","retrieved_document_ids":["d2","d4"]}\n';

export async function bootstrap(page: Page): Promise<void> {
  await page.goto(`${BASE_URL}/#bootstrap=${NONCE}`);
  await expect(page.getByRole("heading", { name: "Workspaces", exact: true })).toBeVisible();
}

export async function createWorkspace(page: Page, name: string): Promise<string> {
  await page.getByLabel("Workspace name").fill(name);
  await page.getByRole("button", { name: "Create workspace" }).click();
  await page.getByRole("link", { name, exact: true }).click();
  await expect(page.getByRole("heading", { name: "Register retrieval inputs" })).toBeVisible();
  const id = page.url().match(/\/workspaces\/(ws-[^/]+)\/inputs/)?.[1];
  expect(id).toBeTruthy();
  return id!;
}

export async function uploadJsonl(
  page: Page, role: "retrieval_ground_truth" | "retrieval_predictions",
  name: string, data: string
): Promise<void> {
  await page.locator("#input-kind").selectOption(role);
  await page.locator("#input-file").setInputFiles({
    name, mimeType: "application/x-ndjson", buffer: Buffer.from(data),
  });
  await page.getByRole("button", { name: "Validate & register" }).click();
  await expect(page.getByText(/Registered \d+ validated record/)).toBeVisible();
}

export async function runPair(page: Page): Promise<void> {
  await page.getByRole("link", { name: "Continue to Runs" }).click();
  await expect(page.getByRole("heading", { name: "Configure & review a run" })).toBeVisible();
  await page.locator("#top-k").fill("2");
  await page.getByRole("button", { name: "Validate & review" }).click();
  await expect(page.getByRole("heading", { name: "Review before evaluation" })).toBeVisible();
  await expect(page.getByText(/Ground truth SHA-256/)).toBeVisible();
  await page.getByRole("button", { name: "Run Evaluation" }).click();
  await expect(page.getByRole("heading", { name: "Evaluation progress" })).toBeVisible();
  await expect(page.locator(".status-text")).toHaveText("COMPLETE", { timeout: 15000 });
  await page.getByRole("link", { name: "View evaluation result" }).click();
  await expect(page.getByRole("heading", { name: "Evaluation result" })).toBeVisible();
}

export async function noOverflow(page: Page): Promise<void> {
  const overflow = await page.evaluate(() =>
    document.documentElement.scrollWidth > document.documentElement.clientWidth
  );
  expect(overflow, "root has horizontal overflow").toBe(false);
}
