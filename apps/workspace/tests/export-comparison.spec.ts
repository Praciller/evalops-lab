import { createHash } from "node:crypto";
import { mkdtemp, readFile, readdir, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, Page, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import {
  BASE_URL, GT_JSONL, bootstrap, createWorkspace, noOverflow, uploadJsonl,
} from "./retrieval-helpers";

const BASE_PRED =
  '{"query_id":"q1","retrieved_document_ids":["d1","d3"]}\n' +
  '{"query_id":"q2","retrieved_document_ids":["d2","d4"]}\n';
const CAND_PRED =
  '{"query_id":"q1","retrieved_document_ids":["missing"]}\n' +
  '{"query_id":"q2","retrieved_document_ids":["missing","d2"]}\n';

async function evaluate(page: Page, predictionInputId?: string): Promise<string> {
  await page.getByRole("link", { name: "Runs", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Configure & review a run" })).toBeVisible();
  await page.locator("#top-k").fill("2");
  if (predictionInputId) {
    await page.locator("#prediction-select").selectOption(predictionInputId);
  }
  await page.getByRole("button", { name: "Validate & review" }).click();
  await expect(page.getByRole("heading", { name: "Review before evaluation" })).toBeVisible();
  await page.getByRole("button", { name: "Run Evaluation" }).click();
  await expect(page.locator(".status-text")).toHaveText("COMPLETE", { timeout: 20000 });
  await page.getByRole("link", { name: "View evaluation result" }).click();
  const id = page.url().match(/\/runs\/(run-[0-9a-f]{32})/)?.[1];
  expect(id).toBeTruthy();
  return id!;
}

type PublicArtifactShape = {
  artifact_type?: string;
  artifact_id?: string;
  population_compatibility?: string;
  baseline_artifact_id?: string;
  candidate_artifact_id?: string;
  baseline_run_id?: string;
  candidate_run_id?: string;
  catalog_status?: string;
  artifacts?: { artifact_id: string }[];
};

type Preview = { eligible: boolean; output_files: {
  filename: string; sha256: string; size_bytes: number;
}[] };

test("canonical browser comparison exports four validated artifacts; exploratory stays private", async ({ page }, info) => {
  test.setTimeout(210000);
  const destination = await mkdtemp(join(tmpdir(), "evalops-browser-comparison-"));
  const external: string[] = [];
  page.on("request", request => {
    if (!request.url().startsWith(BASE_URL) && !request.url().startsWith("data:")) {
      external.push(request.url());
    }
  });
  try {
    await bootstrap(page);
    const ws = await createWorkspace(page, "Phase 6.4 comparison export retry " + info.retry);
    await uploadJsonl(page, "retrieval_ground_truth", "truth.jsonl", GT_JSONL);
    await uploadJsonl(page, "retrieval_predictions", "base.jsonl", BASE_PRED);
    const baseline = await evaluate(page);
    await page.getByRole("button", { name: "Set as workspace baseline" }).click();
    await expect(page.getByText("This completed run is the pinned workspace baseline.")).toBeVisible();

    await page.getByRole("link", { name: "Inputs", exact: true }).click();
    const uploadedPromise = page.waitForResponse(response =>
      response.request().method() === "POST" &&
      response.url().endsWith("/workspaces/" + ws + "/inputs/upload") && response.ok()
    );
    await uploadJsonl(page, "retrieval_predictions", "candidate.jsonl", CAND_PRED);
    const uploaded = await (await uploadedPromise).json() as { input_id: string };
    expect(uploaded.input_id).toMatch(/^input-[0-9a-f]{32}$/);
    const candidate = await evaluate(page, uploaded.input_id);

    await page.getByRole("link", { name: "Comparisons", exact: true }).click();
    await page.getByLabel("Completed candidate run").selectOption(candidate);
    await page.getByRole("button", { name: "Check & create canonical comparison" }).click();
    await expect(page.getByRole("heading", { name: "Comparison detail" })).toBeVisible();
    const comparisonId = page.url().match(/\/comparisons\/(comparison-[0-9a-f]{32})/)?.[1];
    expect(comparisonId).toBeTruthy();

    await page.getByRole("link", { name: "Exports", exact: true }).click();
    await page.locator("#export-source-type").selectOption("comparison");
    await page.locator("#export-source-id").selectOption(comparisonId!);
    const responsePromise = page.waitForResponse(response =>
      response.request().method() === "POST" && response.url().endsWith("/exports/preview")
    );
    await page.getByRole("button", { name: "Create sanitized preview" }).click();
    const response = await responsePromise;
    expect(response.status()).toBe(200);
    const preview = await response.json() as Preview;
    expect(preview.eligible).toBe(true);
    expect(preview.output_files).toHaveLength(4);
    await expect(page.getByRole("heading", { name: "Included" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Removed" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Transformed" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Classification" })).toBeVisible();
    await expect(page.getByText(/does not publish to GitHub Pages/).first()).toBeVisible();

    for (const width of [390, 768, 1280]) {
      await page.setViewportSize({ width, height: 850 });
      await noOverflow(page);
      const axe = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
      expect(axe.violations, "Comparison export at " + width + "px").toEqual([]);
    }

    await page.getByLabel(/Destination directory/).fill(destination);
    await page.getByRole("checkbox").check();
    const confirmResponse = page.waitForResponse(response =>
      response.request().method() === "POST" && response.url().endsWith("/exports/confirm")
    );
    await page.getByRole("button", { name: "Confirm & write sanitized files" }).click();
    expect((await confirmResponse).status()).toBe(201);
    await expect(page.getByRole("heading", { name: "Local export completed" })).toBeVisible();

    const bundleNames = await readdir(destination);
    expect(bundleNames).toHaveLength(1);
    const root = join(destination, bundleNames[0]);
    const names = (await readdir(root)).sort();
    expect(names).toEqual(["baseline.json", "candidate.json", "comparison.json", "index.json"]);
    const files = Object.fromEntries(await Promise.all(names.map(async name => {
      const bytes = await readFile(join(root, name));
      const previewEntry = preview.output_files.find(item => item.filename.endsWith("/" + name));
      expect(previewEntry).toBeDefined();
      expect(previewEntry!.sha256).toBe(createHash("sha256").update(bytes).digest("hex"));
      expect(previewEntry!.size_bytes).toBe(bytes.length);
      for (const privateValue of ["e2e-test-nonce", "candidate.jsonl", "truth.jsonl", "session_token", "transitions"]) {
        expect(bytes.toString("utf8")).not.toContain(privateValue);
      }
      return [name, JSON.parse(bytes.toString("utf8"))];
    }))) as Record<string, PublicArtifactShape>;
    expect(files["baseline.json"].artifact_type).toBe("run");
    expect(files["candidate.json"].artifact_type).toBe("run");
    expect(files["comparison.json"].artifact_type).toBe("comparison");
    expect(files["comparison.json"].population_compatibility).toBe("MATCHED");
    expect(files["comparison.json"].baseline_artifact_id).toBe(files["baseline.json"].artifact_id);
    expect(files["comparison.json"].candidate_artifact_id).toBe(files["candidate.json"].artifact_id);
    expect(files["comparison.json"].baseline_run_id).toBe(baseline);
    expect(files["comparison.json"].candidate_run_id).toBe(candidate);
    expect(files["index.json"].catalog_status).toBe("EXPLICIT_ALLOWLIST");
    const artifacts = files["index.json"].artifacts ?? [];
    expect(artifacts).toHaveLength(3);
    expect(artifacts.map((item: {artifact_id: string}) => item.artifact_id).sort()).toEqual(
      [files["baseline.json"].artifact_id, files["candidate.json"].artifact_id, files["comparison.json"].artifact_id].sort()
    );

    // Explicit exploratory creation is permanently ineligible even if the
    // same source runs happen to share a population.
    const created = await page.evaluate(async args => {
      const response = await fetch("/api/v1/workspaces/" + args.ws + "/comparisons", {
        method: "POST", credentials: "same-origin", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({candidate_run_id: args.candidate, mode: "EXPLORATORY_ONLY"}),
      });
      return { status: response.status, value: await response.json() };
    }, { ws, candidate });
    expect(created.status).toBe(201);
    const exploratory = created.value.comparison_id as string;
    await page.reload();
    await page.locator("#export-source-type").selectOption("comparison");
    await page.locator("#export-source-id").selectOption(exploratory);
    await page.getByRole("button", { name: "Create sanitized preview" }).click();
    await expect(page.getByRole("alert")).toContainText("NON_CANONICAL_COMPARISON");
    await expect(page.getByLabel(/Destination directory/)).toHaveCount(0);
    expect(await readdir(destination)).toEqual(bundleNames);
    expect(external).toEqual([]);
  } finally {
    await rm(destination, { recursive: true, force: true });
  }
});
