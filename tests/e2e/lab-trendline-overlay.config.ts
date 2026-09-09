import { defineConfig, devices } from "@playwright/test";

/**
 * Descartável -- T3.49 (Everton: "quero conferir visualmente se a linha
 * estava certa"). Mesmo padrão de `lab-tabs-click.config.ts`: `testMatch`
 * restrito ao único arquivo desta tarefa; reaproveita o storage state já
 * autenticado do design-audit (refresque-o antes com
 * `bash .claude/state/tmp/run-design-audit.sh -g signup` se este spec
 * redirecionar para o sign-in). Viewport 1440x900 (brief: "screenshots a
 * 1440 dark/light").
 */
export default defineConfig({
  testDir: ".",
  testMatch: /lab-trendline-overlay\.audit\.ts/,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 90_000,
  outputDir: "../../.claude/state/tmp/lab-trendline-overlay-artifacts",
  reporter: "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "off",
    screenshot: "off",
    viewport: { width: 1440, height: 900 },
    storageState: "../../.claude/state/tmp/design-audit-auth.json",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
