import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // infra/docker/Dockerfile.web copies only `.next/standalone` + `.next/static`
  // + `public` into the runtime image (docs/DEPLOYMENT.md §2) — this trims a
  // full `node_modules` out of the image.
  output: "standalone",
};

export default nextConfig;
