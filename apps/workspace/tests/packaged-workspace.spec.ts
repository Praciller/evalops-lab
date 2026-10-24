import { createHash } from "node:crypto";
import { readFile, readdir } from "node:fs/promises";
import { join } from "node:path";
import { expect, test } from "@playwright/test";
import { GT_JSONL, PRED_JSONL, runPair, uploadJsonl } from "./retrieval-helpers";

const bootstrapUrl = process.env.EVALOPS_PACKAGED_BOOTSTRAP_URL;
const destination = process.env.EVALOPS_PACKAGED_EXPORT_DIR;
if (!bootstrapUrl || !destination) {
  throw new Error("packaged browser test requires explicit installed server and destination");
}
const baseUrl = new URL(bootstrapUrl).origin;

test("clean installed wheel performs a real browser evaluation and sanitized local export", async ({ page }) => {
  test.setTimeout(180000);
  const unexpected: string[] = [];
  page.on("request", request => {
    if (!request.url().startsWith(baseUrl + "/") && !request.url().startsWith("data:")) {
      unexpected.push(request.url());
    }
  });

  await page.goto(bootstrapUrl);
  await expect(page.getByRole("heading", { name: "Workspaces", exact: true })).toBeVisible();
  await page.getByLabel("Workspace name").fill("Packaged wheel browser fixture");
  await page.getByRole("button", { name: "Create workspace" }).click();
  await page.getByRole("link", { name: "Packaged wheel browser fixture" }).click();
  await expect(page.getByRole("heading", { name: "Register retrieval inputs" })).toBeVisible();
  await uploadJsonl(page, "retrieval_ground_truth", "wheel-truth.jsonl", GT_JSONL);
  await uploadJsonl(page, "retrieval_predictions", "wheel-predictions.jsonl", PRED_JSONL);
  await runPair(page);
  const runId = page.url().match(/\/runs\/(run-[0-9a-f]{32})/)?.[1];
  expect(runId).toBeTruthy();

  await page.getByRole("link", { name: "Exports", exact: true }).click();
  await page.locator("#export-source-id").selectOption(runId!);
  await expect(page.getByLabel(/Destination directory/)).toHaveCount(0);
  const responsePromise = page.waitForResponse(response => response.url().endsWith("/exports/preview"));
  await page.getByRole("button", { name: "Create sanitized preview" }).click();
  const response = await responsePromise;
  expect(response.status()).toBe(200);
  const preview = await response.json() as {
    eligible: boolean;
    output_files: { filename: string; sha256: string; size_bytes: number }[];
  };
  expect(preview.eligible).toBe(true);
  expect(preview.output_files).toHaveLength(1);
  await expect(page.getByRole("heading", { name: "Included" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Removed" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Transformed" })).toBeVisible();
  await expect(page.getByText(/does not publish to GitHub Pages/).first()).toBeVisible();

  await page.getByLabel(/Destination directory/).fill(destination);
  const confirm = page.getByRole("button", { name: "Confirm & write sanitized files" });
  await expect(confirm).toBeDisabled();
  await page.getByRole("checkbox").check();
  const confirmation = page.waitForResponse(response => response.url().endsWith("/exports/confirm"));
  await confirm.click();
  expect((await confirmation).status()).toBe(201);
  await expect(page.getByRole("heading", { name: "Local export completed" })).toBeVisible();

  const names = await readdir(destination);
  expect(names).toEqual([preview.output_files[0].filename]);
  const payload = await readFile(join(destination, names[0]));
  expect(createHash("sha256").update(payload).digest("hex")).toBe(preview.output_files[0].sha256);
  expect(payload.length).toBe(preview.output_files[0].size_bytes);
  const artifact = JSON.parse(payload.toString("utf8")) as {
    artifact_type: string;
    verification_status: string;
    data_kind: string;
    claim_scope: string;
    run: { run_id: string };
  };
  expect(artifact.artifact_type).toBe("run");
  expect(artifact.run.run_id).toBe(runId);
  expect(artifact.verification_status).toBe("UNVERIFIED");
  expect(artifact.data_kind).toBe("SYNTHETIC_FIXTURE");
  expect(artifact.claim_scope).toBe("INTEGRATION_ONLY");
  for (const secret of ["bootstrap", "session_token", "wheel-truth.jsonl", "wheel-predictions.jsonl"]) {
    expect(payload.toString("utf8")).not.toContain(secret);
  }
  expect(unexpected).toEqual([]);
});
