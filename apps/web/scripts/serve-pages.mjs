import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "out");
const basePath = "/evalops-lab";
const port = Number(process.env.PORT ?? (process.env.PAGES_MODE === "true" ? 4174 : 4173));
const contentTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".txt": "text/plain; charset=utf-8",
  ".woff2": "font/woff2",
};

function fileForRequest(requestPath) {
  if (requestPath !== basePath && !requestPath.startsWith(`${basePath}/`)) return null;
  let relativePath;
  try {
    relativePath = decodeURIComponent(requestPath.slice(basePath.length)).replace(/^\/+/, "");
  } catch {
    return null;
  }
  const candidate = path.resolve(root, relativePath || "index.html");
  if (candidate !== root && !candidate.startsWith(`${root}${path.sep}`)) return null;
  return candidate;
}

async function resolveFile(candidate) {
  try {
    const details = await stat(candidate);
    if (details.isFile()) return candidate;
    if (details.isDirectory()) return resolveFile(path.join(candidate, "index.html"));
  } catch {
    if (!path.extname(candidate)) {
      try {
        return await resolveFile(path.join(candidate, "index.html"));
      } catch {
        return null;
      }
    }
  }
  return null;
}

const server = createServer(async (request, response) => {
  if (request.method !== "GET" && request.method !== "HEAD") {
    response.writeHead(405, { Allow: "GET, HEAD" });
    response.end();
    return;
  }

  const requestPath = new URL(request.url ?? "/", "http://127.0.0.1").pathname;
  const candidate = fileForRequest(requestPath);
  const filePath = candidate ? await resolveFile(candidate) : null;
  if (!filePath) {
    response.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
    response.end("Not found");
    return;
  }

  const body = await readFile(filePath);
  response.writeHead(200, {
    "Cache-Control": "no-store",
    "Content-Length": body.byteLength,
    "Content-Type": contentTypes[path.extname(filePath)] ?? "application/octet-stream",
  });
  if (request.method === "GET") response.end(body);
  else response.end();
});

server.listen(port, "127.0.0.1", () => {
  console.log(`Pages-mode static server listening at http://127.0.0.1:${port}${basePath}/`);
});
