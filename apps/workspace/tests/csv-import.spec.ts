import { expect, test } from "@playwright/test";
import { BASE_URL, GT_JSONL, bootstrap, createWorkspace, noOverflow, uploadJsonl } from "./retrieval-helpers";

test("guided CSV Ground Truth + Predictions normalize and evaluate locally", async ({ page }) => {
  await bootstrap(page);
  const ws = await createWorkspace(page, "Synthetic CSV evaluation");
  await page.getByRole("radio", { name: "CSV mapping" }).check();
  await page.locator("#query-column").fill("qid");
  await page.locator("#docs-column").fill("docs");
  await page.locator("#input-file").setInputFiles({
    name: "truth.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("qid,docs\nq1,d1\nq2,d2\n"),
  });
  await page.getByRole("button", { name: "Validate & register" }).click();
  await expect(page.getByText(/Registered 2 validated record/)).toBeVisible();
  await page.locator("#input-kind").selectOption("retrieval_predictions");
  await page.locator("#input-file").setInputFiles({
    name: "predictions.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("qid,docs\nq1,d1\nq2,d2\n"),
  });
  await page.getByRole("button", { name: "Validate & register" }).click();
  await expect(page.getByText(/Registered 2 validated record/)).toBeVisible();
  await page.getByRole("link", { name: "Continue to Runs" }).click();
  await page.locator("#top-k").fill("2");
  await page.getByRole("button", { name: "Validate & review" }).click();
  await expect(page.getByRole("heading", { name: "Review before evaluation" })).toBeVisible();
  await page.getByRole("button", { name: "Run Evaluation" }).click();
  await expect(page.locator(".status-text")).toHaveText("COMPLETE", { timeout: 15000 });
  await page.getByRole("link", { name: "View evaluation result" }).click();
  await expect(page.getByText("Precision @2")).toBeVisible();
  await expect(page.getByText("LOCAL EVIDENCE — Not published")).toBeVisible();
  await noOverflow(page);

  // Compare actual persisted metrics for semantically equivalent CSV and JSONL inputs.
  const csvRunId = page.url().match(/\/runs\/(run-[a-f0-9]+)$/)?.[1];
  expect(csvRunId).toBeTruthy();
  const csvResult = await (await page.request.get(
    `${BASE_URL}/api/v1/workspaces/${ws}/runs/${csvRunId}`
  )).json();
  const before = await (await page.request.get(
    `${BASE_URL}/api/v1/workspaces/${ws}/inputs`
  )).json();
  const previousIds = new Set<string>(
    before.inputs.map((x: { input_id: string }) => x.input_id)
  );
  await page.getByRole("link", { name: "Inputs" }).click();
  await uploadJsonl(page, "retrieval_ground_truth", "truth.jsonl", GT_JSONL);
  await uploadJsonl(
    page, "retrieval_predictions", "predictions.jsonl",
    '{"query_id":"q1","retrieved_document_ids":["d1"]}\n' +
    '{"query_id":"q2","retrieved_document_ids":["d2"]}\n'
  );
  const after = await (await page.request.get(
    `${BASE_URL}/api/v1/workspaces/${ws}/inputs`
  )).json();
  const newer = (after.inputs as Array<{ input_id: string; kind: string }>)
    .filter((input) => !previousIds.has(input.input_id));
  expect(newer).toHaveLength(2);
  const jsonlTruth = newer.find((input) => input.kind === "retrieval_ground_truth");
  const jsonlPred = newer.find((input) => input.kind === "retrieval_predictions");
  expect(jsonlTruth).toBeDefined();
  expect(jsonlPred).toBeDefined();
  await page.getByRole("link", { name: "Continue to Runs" }).click();
  await page.locator("#truth-select").selectOption(jsonlTruth!.input_id);
  await page.locator("#prediction-select").selectOption(jsonlPred!.input_id);
  await page.locator("#top-k").fill("2");
  await page.getByRole("button", { name: "Validate & review" }).click();
  await expect(page.getByRole("heading", { name: "Review before evaluation" })).toBeVisible();
  await page.getByRole("button", { name: "Run Evaluation" }).click();
  await expect(page.locator(".status-text")).toHaveText("COMPLETE", { timeout: 15000 });
  await page.getByRole("link", { name: "View evaluation result" }).click();
  const jsonlRunId = page.url().match(/\/runs\/(run-[a-f0-9]+)$/)?.[1];
  expect(jsonlRunId).toBeTruthy();
  const jsonlResult = await (await page.request.get(
    `${BASE_URL}/api/v1/workspaces/${ws}/runs/${jsonlRunId}`
  )).json();
  expect(jsonlResult.metrics).toEqual(csvResult.metrics);
  expect(jsonlResult.failure_counts).toEqual(csvResult.failure_counts);
  expect(jsonlResult.evaluator_versions).toEqual(csvResult.evaluator_versions);
});
