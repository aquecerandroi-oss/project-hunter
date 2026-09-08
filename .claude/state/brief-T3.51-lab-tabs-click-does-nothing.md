# Brief T3.51 — Lab: clicar nas abas "Concluídas / Abertas / Pendentes / Todas" não muda nada (Everton, 2026-09-08 19:55, na VPS: "aqui não tá funcionando, eu clico e não resolve nada")

**Owner:** frontend-specialist. **Reviewer afterwards:** code-reviewer. **Do not commit.** **Operational rule: never a background shell; foreground commands with a timeout <= 5 min; no testcontainers; the tree is shared — never `git stash`/`checkout --`/`restore`/`reset`/`clean`/`commit -a` (git-guard blocks); add exact files only; do not touch `.env*`; do not stop or recreate local stack containers (the orchestrator rebuilds `web` when you say the files are ready); VPS read-only.** Base: `main` at `dfe6116` (VPS web = `2e39774`, same Lab code). Scope: `apps/web/components/lab/lab-segment-tabs.tsx`, `apps/web/components/lab/lab-signals-table.tsx`, `apps/web/components/lab/lab-signal-pager.tsx` (same pattern), `apps/web/components/auto-refresh.tsx`, `apps/web/lib/auto-refresh-interval.ts`, their tests, one Playwright repro under `tests/e2e/*.audit.ts`. Do not touch `useRealtime.ts`/`live-status.tsx`/topbar (T3.44d) nor radar pages (T3.46c).

## What the orchestrator already measured (local stack, Playwright, saved session, 2026-09-08 19:58 BRT)
```
URL0 http://localhost:3000/ever/lab   tabs: Concluídas (159) · Abertas (0) · Pendentes/sem entrada (41) · Todas (200)   selected0: [true,false,false,false]
click "Abertas" → wait 8 s
URL1 http://localhost:3000/ever/lab   selected1: [false,true,false,false]      ← aria-selected moved, the URL did NOT (no ?state=open)
click "Todas"   → wait 8 s
URL2 http://localhost:3000/ever/lab   selected2: [false,false,false,true]
pageerror ×2: "Error: Value is null" (lightweight-charts, separate — T3.31 lineage)
```
So the click runs (`handleSelect` → `startTransition(() => router.push(hrefs[segment]))`), the tree flips, but the URL is left at the bare pathname and the next `AutoRefresh` tick (`router.refresh()` every 12 s, `apps/web/components/auto-refresh.tsx`) re-fetches the bare URL and the page falls back to the default segment. On the VPS (slower RSC round-trip) Everton sees "nothing happens". Hypothesis to confirm first: the `router.refresh()` transition races the `router.push()` transition (Next 15 app router keeps one canonical URL per tree and the refresh wins with its stale snapshot). Prove it by (a) reproducing with the repro script pattern in `.claude/state/tmp/lab-tabs-repro.mjs` (run it from `tests/e2e/` so `@playwright/test` resolves; refresh the session with `bash .claude/state/tmp/run-design-audit.sh -g signup` when it redirects to sign-in), (b) the same run with `AutoRefresh` disabled (`intervalMs` huge) — if the URL then carries `?state=open`, the race is confirmed; paste both.

## Deliver
1. **Tabs and pager become real links**: `<Link href={hrefs[segment]} role="tab" aria-selected …>` (an `<a>`, works without JS, keeps the URL as the source of truth); same for `LabSignalPager` prev/next/page-size if they use `router.push`. Keep `isPending` feedback via `useLinkStatus` or a transition wrapper if it costs nothing; drop it otherwise.
2. **AutoRefresh stops racing navigations**: refresh through `startTransition` and skip the tick while a previous refresh is pending; skip the tick within N s after `usePathname()`/`useSearchParams()` changed (a navigation just happened); never call `router.refresh()` when `document.visibilityState !== "visible"` (already). Unit tests for the tick logic (fake timers).
3. **Proof**: Vitest for the tabs (anchor hrefs contain `state=open|pending|all`, `aria-selected` from the `state` prop only), and the Playwright run repeated after the orchestrator rebuilds `web`: URL carries `?state=…` after each click and the rows/pager change (paste counts), 30 s later still on the chosen segment (three AutoRefresh ticks).
4. Report the exact file list to commit; then the orchestrator deploys and re-runs the proof against `https://169.58.116.99`.

## Prove
`pnpm --filter web lint|typecheck|test`, the Playwright outputs; report in Portuguese, extended format; `.claude/state/notes-T3.51.md`.
