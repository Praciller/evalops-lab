import { createHash } from "node:crypto";
import { readFile, readdir } from "node:fs/promises";
import { join } from "node:path";
import { expect, test } from "@playwright/test";
import {
  GT_JSONL, PRED_JSONL, createWorkspace, runPair, uploadJsonl,
} from "./retrieval-helpers";

const baseUrl = process.env.EVALOPS_PACKAGED_BASE_URL;
const bootstrapUrl = process.env.EVALOPS_PACKAGED_BOOTSTRAP_URL;
const destination = process.env.EVALOPS_PACKAGED_DESTINATION;

test("installed Python wheel serves the real Workspace and exports sanitized local evidence", async ({ page }) => {
  test.setTimeout(180_000);
  if (!baseUrl || !bootstrapUrl || !destination) {
    throw new Error("packaged acceptance requires explicit isolated-server variables");
  }
  const unexpected: string[] = [];
  page.on("request", request => {
    if (!request.url().startsWith(baseUrl) && !request.url().startsWith("data:")) {
      unexpected.push(request.url());
    }
  });

  await page.goto(bootstrapUrl);
  await expect(page.getByRole("heading", { name: "Workspaces", exact: true })).toBeVisible();
  const workspaceId = await createWorkspace(page, "Packaged wheel acceptance fixture");
  expect(workspaceId).toMatch(/^ws-[0-9a-f]{32}$/);
  await uploadJsonl(page, "retrieval_ground_truth", "ground.jsonl", GT_JSONL);
  await uploadJsonl(page, "retrieval_predictions", "predictions.jsonl", PRED_JSONL);
  await runPair(page);
  const runId = page.url().match(/\/runs\/(run-[0-9a-f]{32})/)?.[1];
  expect(runId).toBeTruthy();

  await page.getByRole("link", { name: "Exports", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Sanitized evidence export" })).toBeVisible();
  await page.locator("#export-source-id").selectOption(runId!);
  expect(await page.locator("#export-verification").inputValue()).toBe("UNVERIFIED");
  expect(await page.locator("#export-kind").inputValue()).toBe("SYNTHETIC_FIXTURE");

  const previewResponse = page.waitForResponse(response =>
    response.url().endsWith("/exports/preview") && response.request().method() === "POST"
  );
  await page.getByRole("button", { name: "Create sanitized preview" }).click();
  const preview = await previewResponse;
  expect(preview.status()).toBe(200);
  const document = await preview.json() as {
    eligible: boolean;
    output_files: { filename: string; sha256: string; size_bytes: number }[];
  };
  expect(document.eligible).toBe(true);
  expect(document.output_files).toHaveLength(1);
  await expect(page.getByText(/Creating sanitized export does not publish to GitHub Pages/).first()).toBeVisible();
  await page.getByLabel(/Destination directory/).fill(destination);
  await page.getByRole("checkbox").check();

  const confirmResponse = page.waitForResponse(response =>
    response.url().endsWith("/exports/confirm") && response.request().method() === "POST"
  );
  await page.getByRole("button", { name: "Confirm & write sanitized files" }).click();
  expect((await confirmResponse).status()).toBe(201);
  await expect(page.getByRole("heading", { name: "Local export completed" })).toBeVisible();

  expect(await readdir(destination)).toEqual([document.output_files[0].filename]);
  const payload = await readFile(join(destination, document.output_files[0].filename));
  const publicArtifact = JSON.parse(payload.toString("utf8")) as {
    run: { run_id: string };
    data_kind: string;
    claim_scope: string;
    verification_status: string;
  };
  expect(publicArtifact.run.run_id).toBe(runId);
  expect(publicArtifact.data_kind).toBe("SYNTHETIC_FIXTURE");
  expect(publicArtifact.claim_scope).toBe("INTEGRATION_ONLY");
  expect(publicArtifact.verification_status).toBe("UNVERIFIED");
  expect(createHash("sha256").update(payload).digest("hex")).toBe(document.output_files[0].sha256);
  expect(payload.length).toBe(document.output_files[0].size_bytes);
  for (const secret of ["ground.jsonl", "predictions.jsonl", "bootstrap", "session_token", "source_path"]) {
    expect(payload.toString("utf8")).not.toContain(secret);
  }
  expect(unexpected).toEqual([]);
});
