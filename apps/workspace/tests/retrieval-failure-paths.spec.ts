import { test, expect, Page } from "@playwright/test";
import {
  BASE_URL, GT_JSONL, PRED_JSONL, bootstrap, createWorkspace, uploadJsonl,
} from "./retrieval-helpers";

async function awaitGate(page: Page) {
  await expect.poll(async () => {
    const r = await page.request.get(`${BASE_URL}/__test__/gate/status`);
    return (await r.json()).entered as boolean;
  }, { timeout: 10000, intervals: [100, 250] }).toBe(true);
}

async function noPartialArtifacts(page: Page, ws: string, run: string) {
  const response = await page.request.get(
    `${BASE_URL}/__test__/artifacts/status`
  );
  expect(response.ok()).toBe(true);
  expect(await response.json()).toEqual({
    workspace_id: ws, run_id: run, result: false, provenance: false,
  });
}

async function runReview(page: Page) {
  await page.getByRole("link", { name: "Continue to Runs" }).click();
  await page.locator("#top-k").fill("2");
  await page.getByRole("button", { name: "Validate & review" }).click();
  await expect(page.getByRole("heading", { name: "Review before evaluation" })).toBeVisible();
}

async function jobRefs(page: Page) {
  const jobId = page.url().match(/\/jobs\/(job-[a-z0-9]+)/)?.[1] ?? "";
  expect(jobId).toMatch(/^job-/);
  const job = await (await page.request.get(`${BASE_URL}/api/v1/jobs/${jobId}`)).json();
  return { jobId, runId: job.run_id as string, workspaceId: job.workspace_id as string };
}

test("referenced source mutation during queued execution fails with INPUT_HASH_CHANGED", async ({
  page,
}) => {
  await bootstrap(page);
  const ws = await createWorkspace(page, "Synthetic source mutation");
  await uploadJsonl(page, "retrieval_ground_truth", "truth.jsonl", GT_JSONL);

  const fixture = await (await page.request.post(`${BASE_URL}/__test__/fixture/reference`)).json();
  expect(fixture.path).toContain("predictions.jsonl");
  await page.getByRole("radio", { name: "Local path" }).check();
  await page.locator("#input-kind").selectOption("retrieval_predictions");
  await page.getByLabel("Absolute local JSONL path").fill(fixture.path);
  await page.getByRole("button", { name: "Validate & register" }).click();
  await expect(page.getByText(/Registered 1 validated record/)).toBeVisible();

  await runReview(page);
  await page.request.post(`${BASE_URL}/__test__/gate/enable`);
  await page.getByRole("button", { name: "Run Evaluation" }).click();
  await awaitGate(page);
  const ids = await jobRefs(page);
  expect(ids.workspaceId).toBe(ws);
  const mutated = await page.request.post(`${BASE_URL}/__test__/fixture/mutate`);
  expect((await mutated.json()).mutated).toBe(true);
  await page.request.post(`${BASE_URL}/__test__/gate/release`);
  await expect(page.locator(".status-text")).toHaveText("FAILED", { timeout: 12000 });
  await expect(page.getByRole("alert")).toContainText("INPUT_HASH_CHANGED");
  await noPartialArtifacts(page, ws, ids.runId);
  const run = await (await page.request.get(
    `${BASE_URL}/api/v1/workspaces/${ws}/runs/${ids.runId}`
  )).json();
  expect(run.metrics).toBeNull();
});

test("cooperative cancellation at a deterministic gate writes no result or provenance", async ({
  page,
}) => {
  await bootstrap(page);
  const ws = await createWorkspace(page, "Synthetic cancellation");
  await uploadJsonl(page, "retrieval_ground_truth", "truth.jsonl", GT_JSONL);
  await uploadJsonl(page, "retrieval_predictions", "predictions.jsonl", PRED_JSONL);
  await runReview(page);
  await page.request.post(`${BASE_URL}/__test__/gate/enable`);
  await page.getByRole("button", { name: "Run Evaluation" }).click();
  await awaitGate(page);
  const ids = await jobRefs(page);
  await page.getByRole("button", { name: "Cancel run" }).click();
  await expect(page.getByText(/Cancellation requested/i)).toBeVisible();
  await page.request.post(`${BASE_URL}/__test__/gate/release`);
  await expect(page.locator(".status-text")).toHaveText("CANCELLED", { timeout: 12000 });
  await noPartialArtifacts(page, ws, ids.runId);

  // Retry never rewrites the original job and produces a new immutable identity.
  await page.getByRole("button", { name: "Retry as new job" }).click();
  await expect(page).not.toHaveURL(new RegExp(`/jobs/${ids.jobId}$`));
  await expect(page.locator(".status-text")).toHaveText("COMPLETE", { timeout: 15000 });
});

test("real server restart interrupts in-flight job; authenticated retry uses new job ID", async ({
  page,
}) => {
  await bootstrap(page);
  const ws = await createWorkspace(page, "Synthetic restart recovery");
  await uploadJsonl(page, "retrieval_ground_truth", "truth.jsonl", GT_JSONL);
  await uploadJsonl(page, "retrieval_predictions", "predictions.jsonl", PRED_JSONL);
  const seeded = await (await page.request.post(
    `${BASE_URL}/__test__/jobs/seed-transient`, {
      data: { workspace_id: "../../untrusted", ground_truth_input_id: "input-untrusted" },
    }
  )).json();
  // Arbitrary HTTP input cannot select filesystem identities in the test harness.
  expect(seeded.workspace_id).toBe(ws);
  const pid = (await (await page.request.get(`${BASE_URL}/__test__/pid`)).json()).pid;
  await page.request.post(`${BASE_URL}/__test__/restart`);
  await expect.poll(async () => {
    try {
      const r = await page.request.get(`${BASE_URL}/__test__/pid`);
      if (!r.ok()) return false;
      return (await r.json()).pid !== pid;
    } catch { return false; }
  }, { timeout: 20000, intervals: [200, 400, 800] }).toBe(true);

  // Process-local sessions are invalid after restart.
  expect((await page.request.get(`${BASE_URL}/api/v1/session`)).status()).toBe(401);
  await bootstrap(page);
  await page.goto(`${BASE_URL}/jobs/${seeded.job_id}`);
  await expect(page.locator(".status-text")).toHaveText("INTERRUPTED");
  await expect(page.getByRole("alert")).toContainText("WORKER_RESTART");
  await page.getByRole("button", { name: "Retry as new job" }).click();
  await expect(page).not.toHaveURL(new RegExp(`/jobs/${seeded.job_id}$`));
  await expect(page.locator(".status-text")).toHaveText("COMPLETE", { timeout: 15000 });
  await page.getByRole("link", { name: "View evaluation result" }).click();
  await expect(page.getByText("LOCAL EVIDENCE — Not published")).toBeVisible();
});
