# @hunter/web

Next.js 15 (App Router) + React 19 + Tailwind 4 + shadcn/ui front end for PROJECT HUNTER. T08 built the scaffold, theme, auth pages and app shell; T09 added onboarding, the dashboard/system/settings pages, the typed API client and `@hunter/shared-types` (generated from `apps/api`'s OpenAPI document).

## Run

From the repo root (pnpm workspace):

```bash
pnpm install
pnpm --filter @hunter/web dev      # http://localhost:3000
pnpm --filter @hunter/web build
pnpm --filter @hunter/web lint
pnpm --filter @hunter/web typecheck
pnpm --filter @hunter/web test     # vitest
```

`pnpm --filter @hunter/web e2e` is a placeholder ("e2e lands in T12") until Playwright specs exist.

## Environment variables

See `.env.example` at the repo root. This app reads:

- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY` -- Clerk (docs/SECURITY.md §1)
- `API_URL` -- server-side base URL for `apps/api`, used by `lib/server/api.ts` (never exposed to the browser)
- `NEXT_PUBLIC_WS_URL` -- WebSocket gateway base URL, used by `lib/ws.ts` (not connected anywhere yet, see below)
- `HUNTER_ENV` -- gates whether `planned` nav items render (hidden in `production`)

## What's here (T08)

- Auth: `middleware.ts` (Clerk, protects everything except `/`, `/sign-in`, `/sign-up`, `/forgot-password`, `/api/webhooks`), `app/(auth)/{sign-in,sign-up,forgot-password}`.
- Theme: `app/globals.css`, Tailwind 4 `@theme` tokens, dark-first with a `[data-theme="light"]` override, fixed semantic long/short/positive/negative/warning colors, `tabular-nums` for numbers (Tailwind core utility).
- App shell: `app/(app)/[orgSlug]/layout.tsx` (chrome only, no pages -- see below), `components/layout/{sidebar,topbar,mobile-nav,planned-badge,theme-toggle,nav-links}.tsx`.
- Navigation: `lib/nav-registry.ts`, the single source of the sidebar (`docs/PRODUCT.md` §4). `visibleNavItems(role, env)` is unit-tested.
- `lib/logger.ts` -- the only file allowed to call `console.*`.
- `lib/server/{auth,api}.ts` -- server-only (Clerk session, `apiFetch`), marked with `import "server-only"` and enforced by ESLint boundaries.
- `lib/ws.ts` + `hooks/useRealtime.ts` -- typed realtime client with reconnect/backoff and the `auth`-first-message handshake from `docs/ARCHITECTURE.md` §5.2. **Not connected anywhere in M0**: `useRealtime`'s `enabled` option defaults to `false` because no worker publishes on any `rt:*` channel yet. Turn it on only once the corresponding M1+ backend piece exists.
- Sentry: intentionally **not wired**. `@sentry/nextjs` was left out rather than half-configured; add it when `NEXT_PUBLIC_SENTRY_DSN`/observability work is scheduled.

## Routes (T09)

| Route | What renders | Role gating |
|---|---|---|
| `/` | Redirects: signed out -> `/sign-in`; no memberships -> `/onboarding`; a membership with unfinished onboarding -> `/onboarding?org=<slug>`; else the first membership's `/<slug>/dashboard` | -- |
| `/onboarding/[[...step]]` | Six-step wizard (docs/PRODUCT.md §3): org+workspace name, objective, virtual capital, risk profile, exchanges, summary. `?org=<slug>` resumes an org that exists but hasn't finished onboarding | Any signed-in user |
| `/[orgSlug]/dashboard` | Honest M0 shell: org/workspace/members cards + empty states for markets (M1) and portfolio (M3). No PnL, no charts | VIEWER+ |
| `/[orgSlug]/system` | API env/version/git sha, live Postgres/Redis readiness (with a real refresh button), feature flags, workers empty state (M1) | VIEWER+ |
| `/[orgSlug]/settings/profile` | Clerk `<UserProfile>` | Any member |
| `/[orgSlug]/settings/organization` | Rename form -- editable ADMIN+, read-only otherwise | VIEWER+ (edit ADMIN+) |
| `/[orgSlug]/settings/members` | Roster + invitations. Role change/remove are OWNER-only; invite/revoke are ADMIN+ | VIEWER+ (manage per above) |
| `/[orgSlug]/settings/security` | Clerk `<UserProfile>` security tab + "API keys: Planejado (Fase 2)" | Any member |
| `/[orgSlug]/settings/appearance` | Theme (reuses `ThemeToggle`) + a real density toggle, both in `localStorage` | Any member |

Every `[orgSlug]` route resolves the caller's membership via `lib/api/org-context.ts`'s `resolveOrgContext` (built on `/api/v1/me`); an unknown or foreign slug is `notFound()`, never a 500.

## What T09 needs to know

- `app/(app)/[orgSlug]/layout.tsx` renders `children` as-is inside `<main>`; add pages as `app/(app)/[orgSlug]/<route>/page.tsx` (Server Component by default). It now resolves the real role from `/api/v1/me` (via `resolveOrgContext`) instead of the T08 `role = "VIEWER"` placeholder.
- Call the API from a Server Component with `import { apiFetch } from "@/lib/server/api"` -- never from `components/**` or `hooks/**` (ESLint fails the build if you try). `lib/api/*.ts` wraps `apiFetch` per resource; mutations live in `lib/api/*-actions.ts` (`"use server"`, zod-validated, return `ActionResult` instead of throwing).
- `lib/nav-registry.ts` is the only place to add/reorder nav items; bump an item from `planned` to `available` there when its milestone lands. Dashboard/system/settings are already `available` as of T08/T09.
- `packages/shared-types` is generated from `apps/api`'s OpenAPI document (`pnpm gen:types` at the repo root); never hand-edit `packages/shared-types/src/generated/api.d.ts`.
