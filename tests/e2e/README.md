# tests/e2e — `@hunter/e2e`

Playwright end-to-end suite (docs/plans/M0.md T12). Run against a live
`apps/web` (dev server locally, `docker compose` in CI) plus, for
`api-health.spec.ts` and `signup-onboarding.spec.ts`, a live `apps/api`.

## Run

```bash
pnpm install
pnpm --filter @hunter/e2e install-browsers   # downloads Chromium (~150 MB), once
pnpm --filter @hunter/e2e test               # apps/web must already be running on :3000
```

Or via the workspace pipeline: `pnpm e2e` (turbo `e2e` task, `dependsOn: ["build"]`).

Env vars:

| Var | Default | Purpose |
|---|---|---|
| `E2E_BASE_URL` | `http://localhost:3000` | `apps/web` origin |
| `E2E_API_URL` | `http://localhost:8000` | `apps/api` origin, used only by `api-health.spec.ts` |
| `CLERK_E2E_PUBLISHABLE_KEY`, `CLERK_E2E_SECRET_KEY` | unset | Real Clerk dev-instance keys with test mode on. Required only by `signup-onboarding.spec.ts`; every other spec runs without them. |

## Specs

- `public.spec.ts` — `/_design` and `/sign-in`. No auth, no API, no Clerk keys required (the fake-key case is itself an assertion).
- `api-health.spec.ts` — `apps/api` `/health` and `/ready` against the docker compose stack. Self-skips with the reason if the API isn't reachable.
- `signup-onboarding.spec.ts` — full signup → six-step onboarding → dashboard → `/system` → `/settings/members` walk. Self-skips with the reason "CLERK_E2E keys not configured" unless both `CLERK_E2E_PUBLISHABLE_KEY` and `CLERK_E2E_SECRET_KEY` are set.

No `kill-switch.spec.ts` exists yet — see below.

## Critical flows (docs/MVP.md §2) — status

The table below is docs/MVP.md §2's own "Critérios de sucesso" mapped to what
actually exists today, so nothing here pretends to be implemented before its
milestone lands (CLAUDE.md: "No fake anything ... no 'coming soon' pages").

| Flow | Verified by | Status |
|---|---|---|
| Usuário cria conta (signup) | `signup-onboarding.spec.ts` | **Implemented in M0** (skips without `CLERK_E2E_*` keys) |
| Onboarding cria organização | `signup-onboarding.spec.ts` | **Implemented in M0** — org/workspace only. Portfolio paper creation lands in M3 |
| Nenhum dado depende de arquivo local | `infra/scripts/forbidden_patterns.sh` (CI gate, not Playwright) | **Implemented in M0** |
| Public surfaces render without a session | `public.spec.ts` | **Implemented in M0** |
| `apps/api` health/readiness | `api-health.spec.ts` | **Implemented in M0** |
| Dashboard funciona (dados reais, cards completos) | none yet | **Lands in M5** — M0's dashboard is an honest empty-state shell, already covered incidentally by `signup-onboarding.spec.ts`'s assertions, but the real success criterion (cards backed by live data) has no spec until M5 |
| Market data realtime (`/system` < 5s) | none yet | **Lands in M1** |
| Scanner monitora ativos (`/radar`) | none yet | **Lands in M2** |
| Anomalias aparecem | none yet | **Lands in M2** |
| Opportunity Score / Explanation Panel | none yet | **Lands in M2** |
| Agentes geram sinais | none yet | **Lands in M4** |
| Risk Engine aceita/rejeita (kill switch, checks) | none yet | **Lands in M4** — this is the flow a `kill-switch.spec.ts` would cover. Not created now: the kill switch (`packages/risk-core`, `docs/RISK_ENGINE.md`) doesn't exist yet in M0, so a placeholder spec would either be empty (pure theater) or `test.skip` forever with no real assertion to eventually un-skip. Add it alongside the Risk Engine UI in M4 instead |
| Paper Wallet executa (orders/fills/positions) | none yet | **Lands in M3 + M4** |
| PnL calculado (equity reconciliation) | none yet | **Lands in M3** |
| Trade history (`/trades`, `/trades/[id]`) | none yet | **Lands in M3** |
| Dashboard atualiza via WS (< 1s) | none yet | **Lands in M5** |
