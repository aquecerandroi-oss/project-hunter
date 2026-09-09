import { defineConfig, devices } from "@playwright/test";

/**
 * Descartável -- T3.44d (diagnóstico dos fechamentos de WS iniciados pelo
 * cliente). Mesmo padrão de `design-audit.config.ts`: `testMatch` restrito
 * ao único arquivo desta tarefa para o suite normal nunca coletá-lo.
 *
 * Não lê `.env`: `CLERK_E2E_*`/`E2E_BASE_URL` vêm exportados no shell de quem
 * roda (mesmo contrato do `playwright.config.ts` oficial).
 */
export default defineConfig({
  testDir: ".",
  testMatch: /ws-disconnect-repro\.audit\.ts/,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  outputDir: "../../.claude/state/tmp/ws-repro-artifacts",
  reporter: "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "off",
    screenshot: "off",
    // md breakpoint+ so the desktop `Sidebar` (real `next/link`s) renders --
    // this script clicks those, never `page.goto()`, to tell a soft
    // client-side transition apart from a hard page navigation.
    viewport: { width: 1280, height: 900 },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
