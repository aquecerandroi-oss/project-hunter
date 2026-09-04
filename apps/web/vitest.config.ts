import path from "node:path";
import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

const dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  // The repo's tsconfig sets `jsx: "preserve"` for Next.js's own build
  // pipeline; Vite's esbuild transform reads that same tsconfig, and
  // "preserve" leaves JSX syntax untouched, which esbuild's JS parser then
  // rejects. Force the automatic runtime here so `.test.tsx` files (React
  // Testing Library) transform correctly without needing a separate
  // @vitejs/plugin-react dependency.
  oxc: {
    jsx: { runtime: "automatic" },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    include: ["tests/**/*.test.{ts,tsx}"],
    css: false,
  },
  resolve: {
    alias: {
      "@": dirname,
    },
  },
});
