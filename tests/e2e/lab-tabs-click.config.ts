import { defineConfig, devices } from "@playwright/test";

/**
 * Descartável -- T3.51 (Everton na VPS: "eu clico e não resolve nada" nas
 * abas Concluídas/Abertas/Pendentes/Todas do `/lab`). Mesmo padrão de
 * `ws-repro.config.ts`/`design-audit.config.ts`: `testMatch` restrito ao
 * único arquivo desta tarefa para o suite normal (`*.spec.ts`) nunca
 * coletá-lo.
 *
 * Não lê `.env`: `E2E_BASE_URL` vem exportado no shell de quem roda (mesmo
 * contrato do `playwright.config.ts` oficial). A sessão reaproveita o
 * storage state já autenticado do design-audit
 * (`.claude/state/tmp/design-audit-auth.json`) -- refresque-o antes com
 * `bash .claude/state/tmp/run-design-audit.sh -g signup` se este repro
 * redirecionar para o sign-in.
 */
export default defineConfig({
  testDir: ".",
  testMatch: /lab-tabs-click\.audit\.ts/,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 90_000,
  outputDir: "../../.claude/state/tmp/lab-tabs-click-artifacts",
  reporter: "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "off",
    screenshot: "off",
    storageState: "../../.claude/state/tmp/design-audit-auth.json",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
