import { spawnSync } from "node:child_process";
import { cpSync, rmSync } from "node:fs";
import path from "node:path";

function runNpmScript(script, env = process.env) {
  const result = spawnSync("npm", ["run", script], {
    env,
    shell: process.platform === "win32",
    stdio: "inherit",
  });

  if (result.error) {
    console.error(result.error);
    process.exit(1);
  }
  if (result.status !== 0) process.exit(result.status ?? 1);
}

function runNodeScript(script) {
  const result = spawnSync(process.execPath, [script], { stdio: "inherit" });
  if (result.error) {
    console.error(result.error);
    process.exit(1);
  }
  if (result.status !== 0) process.exit(result.status ?? 1);
}

runNpmScript("build", { ...process.env, GITHUB_PAGES: "true" });
runNpmScript("storybook:build:public");
runNodeScript("scripts/verify-public-storybook.mjs");

const publicOutput = path.join(process.cwd(), "storybook-public-static");
const pagesStorybookOutput = path.join(process.cwd(), "out", "storybook");
rmSync(pagesStorybookOutput, { force: true, recursive: true });
cpSync(publicOutput, pagesStorybookOutput, { recursive: true });
