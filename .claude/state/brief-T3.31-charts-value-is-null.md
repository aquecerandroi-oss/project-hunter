# Brief T3.31 — todos os gráficos (lightweight-charts) morrem com "Error: Value is null" — a curva do Lab está vazia na VPS

**Owner:** frontend-specialist. **Reviewers afterwards:** product-designer (tela real), code-reviewer. **Do not commit.** **Operational rule: never a background shell; foreground commands with a timeout <= 5 min; the tree is shared — never `git stash`/`checkout --`/`restore`/`reset`/`clean`/`commit -a`; add exact files only; do not touch `.env*`; do not stop or recreate local stack containers (the orchestrator rebuilds `docker-web-1` for you when you ask).** Base: `main` at `970c20b`. In flight elsewhere: T3.18c (`apps/api/**`), T3.29 (`services/execution-worker/**`) — nothing else in `apps/web/**`. Your scope: `apps/web/components/lab/lab-curve-chart.tsx`, `apps/web/components/markets/candles-chart.tsx`, `apps/web/components/portfolio/portfolio-equity-chart.tsx`, `apps/web/lib/charts/**` (or wherever `cssVar`/chart helpers live), their tests.

## Measured (VPS, 2026-09-08 14:55Z, Everton's Chrome on `https://<vps>/ever/lab`, web `42ec146`)
Console: two `EXCEPTION Error: Value is null` from chunk `3e7f71f0` (lightweight-charts) at `M` → `tR.Line [as gh]` → `tR.Sh` → `sp.Rb` → `Array.map` → `sp.Lg` … The "Curva de resultado simulado" section renders 7 canvases and the legend (5 versions) but **no lines**. The same exception was logged during the 375 design audit this morning (before T3.24b), and T3.28b's notes (`.claude/state/notes-T3.28b.md` concern 3) traced it to `ensureNotNull`/`ensureDefined` inside lightweight-charts, reached from `candles-chart.tsx` and `portfolio-equity-chart.tsx` too — so this predates the Lab redesign and hits every chart.

## Suspects (verify, do not assume)
1. `cssVar(...)` returning `""`/`null` for a token that T3.24a renamed (`--color-*` contrast tokens) → `addSeries(LineSeries, { color: "" })` or `applyOptions({ color: null })`. Check `getComputedStyle(document.documentElement).getPropertyValue(...)` at the moment `useEffect` runs (before the theme attribute is set?).
2. `setData` with a point whose `value` is `null`/`NaN` (Decimal string → `Number("0E-20")`? — `parseDecimal` handles exponents since `b6f5c2c`, but check `toSeriesData`), or unsorted/duplicate `time` values (lightweight-charts throws on non-ascending time; that error text differs, but check).
3. Series created on a chart already removed (React 19 strict effects / `remove()` ordering) — `Value is null` from `ensureNotNull(this._chart)`.

## Deliver
1. Reproduce with Playwright against `http://localhost:3000/ever/lab` and `/ever/markets/binance/BTCUSDT` (storage state `.claude/state/tmp/design-audit-auth.json`; runner `bash .claude/state/tmp/run-design-audit.sh`; write a throwaway spec `tests/e2e/_probe.audit.ts` + `_probe.config.ts` and delete both at the end), capturing `pageerror` with the un-minified stack: run the page against a non-minified build if needed (`NODE_ENV=development next dev` is not available in the container — use source maps: `next build` emits them if `productionBrowserSourceMaps: true` — do not commit that flag).
2. Fix the root cause in the shared helper (one place), not per chart; guard `cssVar` (fallback to a defined token + `console.warn` once), validate series points (drop non-finite, sort by time, dedupe), and make chart effects idempotent under React strict mode.
3. Tests: unit for the helper (token missing → fallback, non-finite dropped, duplicate time deduped) and the three charts render a line with the fixtures (jsdom mock of `createChart` as already used in `lab-curve-chart.test.tsx`).
4. Proof: after the orchestrator rebuilds `docker-web-1`, the Lab curve and the BTCUSDT candles render lines (screenshots in `.claude/state/design/2026-09-08/`), console with zero `Value is null`.

## Prove
`pnpm --filter web lint|typecheck|test` with real output; report in Portuguese, extended format; `.claude/state/notes-T3.31.md`.
