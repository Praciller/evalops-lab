import fs from "node:fs";
import path from "node:path";
import process from "node:process";

const appRoot = process.cwd();
const outputRoot = path.join(appRoot, "storybook-public-static");
const indexPath = path.join(outputRoot, "index.json");
const manifestPath = path.join(appRoot, "storybook.public.json");

const forbiddenPatterns = [
  ["internal story marker", /\.internal\.stories/gi],
  ["internal title", /(?:^|[\\/])Internal\//g],
  ["debug title", /(?:^|[\\/])Debug\//g],
  ["Windows absolute path", /(?:^|[\s"'])[A-Za-z]:[\\/]/g],
  ["home absolute path", /\/home\//g],
  ["environment file marker", /(?:["'`]|[\\/])\.env(?:["'`.\\/]|$)/gi],
  ["OpenAI-like key", /sk-[A-Za-z0-9_-]{20,}/g],
  ["Google-like key", /gsk_[A-Za-z0-9_-]{20,}/g],
  ["raw prompt marker", /raw_prompt/gi],
  ["raw response marker", /raw_response/gi],
  ["raw corpus marker", /raw_corpus/gi],
  ["hidden reasoning marker", /hidden_reasoning/gi],
  ["authorization field", /["'`]authorization["'`]\s*:/gi],
  ["authorization bearer", /authorization\s*:\s*bearer/gi],
  ["api key field", /["'`]api_key["'`]\s*:/gi],
];

function fail(message) {
  throw new Error(`[public-storybook] ${message}`);
}

function walkFiles(directory) {
  const files = [];
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const entryPath = path.join(directory, entry.name);
    if (entry.isDirectory()) files.push(...walkFiles(entryPath));
    else files.push(entryPath);
  }
  return files;
}

if (!fs.existsSync(indexPath)) fail(`missing ${path.relative(appRoot, indexPath)}`);
if (!fs.existsSync(manifestPath)) fail(`missing ${path.relative(appRoot, manifestPath)}`);

const index = JSON.parse(fs.readFileSync(indexPath, "utf8"));
const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
const actualTitles = new Set(
  Object.values(index.entries ?? {})
    .filter((entry) => entry.type === "story")
    .map((entry) => entry.title),
);
const expectedTitles = new Set(manifest.titles ?? []);

const actualSorted = [...actualTitles].sort();
const expectedSorted = [...expectedTitles].sort();
if (JSON.stringify(actualSorted) !== JSON.stringify(expectedSorted)) {
  fail(`title allowlist mismatch; expected ${expectedSorted.join(", ")}, got ${actualSorted.join(", ")}`);
}

for (const title of actualTitles) {
  if (/^(Internal|Debug)\//.test(title)) fail(`forbidden public title ${title}`);
}

for (const filePath of walkFiles(outputRoot)) {
  const contents = fs.readFileSync(filePath, "utf8");
  for (const [label, pattern] of forbiddenPatterns) {
    pattern.lastIndex = 0;
    if (pattern.test(contents)) fail(`${label} found in ${path.relative(appRoot, filePath)}`);
  }
}

console.log(`[public-storybook] verified ${actualTitles.size} curated titles and ${walkFiles(outputRoot).length} output files`);
