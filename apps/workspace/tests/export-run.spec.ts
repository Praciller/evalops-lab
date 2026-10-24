import { createHash } from "node:crypto";
import { mkdtemp, readFile, readdir, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, Page, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import {
  BASE_URL, GT_JSONL, PRED_JSONL, bootstrap, createWorkspace, noOverflow,
  runPair, uploadJsonl,
} from "./retrieval-helpers";

type PreviewBody = {
  preview_id: string;
  eligible: boolean;
  output_files: { filename: string; sha256: string; size_bytes: number }[];
};

async function completedRun(page: Page, name: string) {
  await bootstrap(page);
  const workspaceId = await createWorkspace(page, name);
  await uploadJsonl(page, "retrieval_ground_truth", "truth.jsonl", GT_JSONL);
  await uploadJsonl(page, "retrieval_predictions", "predictions.jsonl", PRED_JSONL);
  await runPair(page);
  const runId = page.url().match(/\/runs\/(run-[0-9a-f]{32})/)?.[1];
  expect(runId).toBeTruthy();
  return { workspaceId, runId: runId! };
}

async function previewRun(page: Page, runId: string): Promise<PreviewBody> {
  await page.getByRole("link", { name: "Exports", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Sanitized evidence export" })).toBeVisible();
  await page.locator("#export-source-id").selectOption(runId);
  expect(await page.locator("#export-verification").inputValue()).toBe("UNVERIFIED");
  expect(await page.locator("#export-kind").inputValue()).toBe("SYNTHETIC_FIXTURE");
  await expect(page.getByLabel(/Destination directory/)).toHaveCount(0);

  const responsePromise = page.waitForResponse(
    response => response.url().endsWith("/exports/preview") && response.request().method() === "POST"
  );
  await page.getByRole("button", { name: "Create sanitized preview" }).click();
  const response = await responsePromise;
  expect(response.status()).toBe(200);
  const body = await response.json() as PreviewBody;
  expect(body.eligible).toBe(true);
  await expect(page.getByRole("heading", { name: "Sanitized export preview" })).toBeVisible();
  for (const section of ["Classification", "Included", "Removed", "Transformed", "Output files"]) {
    await expect(page.getByRole("heading", { name: section, exact: true })).toBeVisible();
  }
  await expect(page.getByText(/Creating sanitized export does not publish to GitHub Pages/).first()).toBeVisible();
  return body;
}

test("actual browser run export is explicit, sanitized, hashed and locally confirmed", async ({ page }, info) => {
  test.setTimeout(180000);
  const destination = await mkdtemp(join(tmpdir(), "evalops-browser-run-export-"));
  const unexpected: string[] = [];
  page.on("request", request => {
    if (!request.url().startsWith(BASE_URL) && !request.url().startsWith("data:")) {
      unexpected.push(request.url());
    }
  });
  try {
    const { runId } = await completedRun(page, "Phase 6.4 run export retry " + info.retry);
    const preview = await previewRun(page, runId);
    expect(preview.output_files).toHaveLength(1);
    expect(await readdir(destination)).toEqual([]);
    for (const width of [390, 768, 1280]) {
      await page.setViewportSize({ width, height: 850 });
      await noOverflow(page);
      const axe = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
      expect(axe.violations, "Run export at " + width + "px must have zero WCAG violations").toEqual([]);
    }
    await page.getByLabel(/Destination directory/).fill(destination);
    const button = page.getByRole("button", { name: "Confirm & write sanitized files" });
    await expect(button).toBeDisabled();
    await page.getByRole("checkbox").check();
    const responsePromise = page.waitForResponse(
      response => response.url().endsWith("/exports/confirm") && response.request().method() === "POST"
    );
    await button.click();
    const response = await responsePromise;
    expect(response.status()).toBe(201);
    const exported = await response.json() as { export_id: string; destination: string };
    expect(exported.export_id).toMatch(/^export-[0-9a-f]{32}$/);
    await expect(page.getByRole("heading", { name: "Local export completed" })).toBeVisible();
    const files = await readdir(destination);
    expect(files).toEqual([preview.output_files[0].filename]);
    const bytes = await readFile(join(destination, files[0]));
    const artifact = JSON.parse(bytes.toString("utf8")) as {
      artifact_type: string;
      verification_status: string;
      data_kind: string;
      claim_scope: string;
      run: { run_id: string };
    };
    expect(artifact.artifact_type).toBe("run");
    expect(artifact.verification_status).toBe("UNVERIFIED");
    expect(artifact.data_kind).toBe("SYNTHETIC_FIXTURE");
    expect(artifact.claim_scope).toBe("INTEGRATION_ONLY");
    expect(artifact.run.run_id).toBe(runId);
    expect(createHash("sha256").update(bytes).digest("hex")).toBe(preview.output_files[0].sha256);
    expect(bytes.length).toBe(preview.output_files[0].size_bytes);
    for (const forbidden of [
      "e2e-test-nonce", "truth.jsonl", "predictions.jsonl",
      "evalops-e2e-", "bootstrap", "session_token", "source_path",
    ]) {
      expect(bytes.toString("utf8")).not.toContain(forbidden);
    }
    expect(unexpected).toEqual([]);
  } finally {
    await rm(destination, { recursive: true, force: true });
  }
});

test("tampering immutable run evidence after preview blocks export without writing a file", async ({ page }, info) => {
  test.setTimeout(180000);
  const destination = await mkdtemp(join(tmpdir(), "evalops-browser-tampered-export-"));
  try {
    const { runId } = await completedRun(page, "Phase 6.4 tamper retry " + info.retry);
    const preview = await previewRun(page, runId);
    const response = await page.request.post(BASE_URL + "/__test__/exports/tamper-latest-run");
    expect(response.ok()).toBe(true);
    expect((await response.json() as { tampered: boolean }).tampered).toBe(true);
    await page.getByLabel(/Destination directory/).fill(destination);
    await page.getByRole("checkbox").check();
    await page.getByRole("button", { name: "Confirm & write sanitized files" }).click();
    await expect(page.getByRole("alert")).toContainText("source changed");
    await expect(page.getByRole("heading", { name: "Local export completed" })).toHaveCount(0);
    expect(preview.eligible).toBe(true);
    expect(await readdir(destination)).toEqual([]);
  } finally {
    await rm(destination, { recursive: true, force: true });
  }
});
