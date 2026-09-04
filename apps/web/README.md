# @hunter/web

Next.js 15 (App Router) + React 19 + Tailwind 4 + shadcn/ui front end for PROJECT HUNTER. Implemented in Milestone 0 (T08): scaffold, theme, auth pages, app shell. Onboarding and in-app pages land in T09.

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

## What T09 needs to know

- `app/(app)/[orgSlug]/layout.tsx` renders `children` as-is inside `<main>`; add pages as `app/(app)/[orgSlug]/<route>/page.tsx` (Server Component by default).
- Call the API from a Server Component with `import { apiFetch } from "@/lib/server/api"` -- never from `components/**` or `hooks/**` (ESLint fails the build if you try). Client components that need API data should get it via props from a Server Component parent, or through a client-side fetch/TanStack Query call of their own (not `apiFetch`, which is server-only).
- The layout hardcodes `role = "VIEWER"` until an orgs/membership endpoint exists (see the `TODO(T09/T06)` comment in that file); replace it once `apps/api` exposes current-user role for an org. This doesn't hide any M0 nav item today since every item's `minRole` is `VIEWER`.
- `lib/nav-registry.ts` is the only place to add/reorder nav items; bump an item from `planned` to `available` there when its milestone lands.
