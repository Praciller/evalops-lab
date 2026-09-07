import path from "node:path";
import type { NextConfig } from "next";

const basePath = process.env.GITHUB_PAGES === "true" ? "/evalops-lab" : "";

const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  basePath,
  images: { unoptimized: true },
  turbopack: {
    root: path.resolve(process.cwd(), "../.."),
  },
};

export default nextConfig;
