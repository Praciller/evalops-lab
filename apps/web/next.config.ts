import type { NextConfig } from "next";

const basePath = process.env.GITHUB_PAGES === "true" ? "/evalops-lab" : "";

const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  basePath,
  images: { unoptimized: true },
};

export default nextConfig;
