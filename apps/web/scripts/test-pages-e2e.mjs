import { spawnSync } from "node:child_process";

const result = spawnSync("npm", ["run", "test:e2e"], {
  env: { ...process.env, PAGES_MODE: "true" },
  shell: process.platform === "win32",
  stdio: "inherit",
});

if (result.error) {
  console.error(result.error);
  process.exit(1);
}

process.exit(result.status ?? 1);
