# T1.7 — Integration + E2E tests for the M1 market pipeline (PROJECT HUNTER)

Owner: `test-engineer`. Runs after T1.6 (operational proof) lands. Kit: `.claude/state/review-T1.7.md` (Sexta-feira). Files: `tests/integration/**`, `tests/e2e/**`, `services/market-worker/tests/**` (only new files), `apps/api/tests/integration/**` (only new files), `.github/workflows/ci.yml` (only to add the new suites to the gate). Do NOT touch product code; if a test reveals a bug, report it with the failing test and let the orchestrator dispatch the fix.

## What to prove (each item = one test with real infra via testcontainers or the compose stack)
1. **Pipeline contract with a fake adapter:** scripted stream (ticker, trades, book, kline partial→final, markPrice, forceOrder) → worker → Redis hashes/lists exactly per contract (`mkt:*:ticker` fields + `price_ts`/`book_ts`, `book` msgpack with `depth=20,kind=snapshot`, `trades` LPUSH order, `candles:1m` rules: partial updates partial, final replaces partial, partial never replaces final, older ts discarded) → Postgres (`candles` finals only, once; `market_snapshots` one per minute per market, none when no hot state; `liquidations` `ON CONFLICT (id, ts)` dedupe; `open_interest_history` bucket per cycle) → API responses (`/markets`, `/markets/{ex}/{sym}`, `/candles`, `/system/workers`, `/system/market-status`) → WS `rt:market:*` and `rt:system` frames via the gateway.
2. **Invariants:** `open_time` aligned; no duplicate candle; `event_id` of `market.liquidations` == row id; staleness aggregate branches (ticker/book/mark absent, gap open/failed, time advancing) at the API; `components.*.age_ms` from exchange `ts`, never flush time.
3. **Recovery:** delete a middle candle → `check_gaps` registers an internal hole → REST backfill (fake adapter) → `recovered` in the same transaction; 5 failures → `failed`; failed reopens after cooldown.
4. **Supervision:** child task dies → process exits non-zero; per-connection silence → restart of that connection; readiness `initializing` false, `connecting` tolerated ≤ 120 s monotonic then 503; persistence stuck → 503.
5. **Operational (compose, marked `live`, run in CI only when `HUNTER_LIVE_TESTS=1`):** worker against real Binance for 120 s: ≥ 1 ticker per monitored market, ≥ 1 final candle persisted, `/system/market-status` `ws_state=connected`; container restart without duplicate candles; `docker network disconnect` 40 s → reconnect + gap recovered.
6. **E2E Playwright (`tests/e2e/markets.spec.ts`, gated by `CLERK_E2E_*` like signup):** list loads with real rows, row click opens detail, Ctrl/⌘K search, quality badge ages when the WS is cut (mock the WS URL to a closed port), System shows the `market` worker.
7. **Anti-useless-test check:** break one invariant on purpose in a scratch branch (e.g., allow a partial to replace a final) and show the suite goes red; revert.

## Verification to paste
```
uv run pytest tests/integration -q -p no:cacheprovider
uv run pytest services/market-worker apps/api -q -p no:cacheprovider -k "t17 or pipeline or invariant"
HUNTER_LIVE_TESTS=1 uv run pytest tests/integration -m live -q -p no:cacheprovider
pnpm --filter @hunter/e2e e2e
```
Report: STATUS, tests added (file → cases), real output, bugs found (with the failing test), Segunda opinião (Astra) on coverage gaps.
