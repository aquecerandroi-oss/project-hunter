import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright config for `@hunter/e2e` (docs/plans/M0.md T12).
 *
 * `webServer` is deliberately NOT configured here: this package never boots
 * `apps/web` itself.
 *   - Locally, point it at the dev server that's already running on
 *     `http://localhost:3000` (`pnpm --filter @hunter/web dev`).
 *   - In CI, `.github/workflows/ci.yml`'s `e2e` job brings up the real stack
 *     with `docker compose -f infra/docker/docker-compose.yml up -d --build`
 *     (web served via `next start`, matching production) and waits for
 *     `/ready` before running this suite.
 * Starting a second, throwaway `next dev`/`next build` here would diverge
 * from both of those and hide real integration issues.
 */
export default defineConfig({
  testDir: ".",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  outputDir: "./artifacts",
  reporter: process.env.CI ? [["github"], ["html", { open: "never", outputFolder: "./artifacts/html-report" }]] : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
