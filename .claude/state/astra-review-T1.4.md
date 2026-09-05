Reviewed the 2 modified and 11 untracked `apps/api` files against M1 and Astra rodada 4. **T1.4 is not ready for acceptance.**

**Must-fix**

1. **Recent trades read the wrong end of Redis.** [markets.py:285](C:/dev/project-hunter/apps/api/hunter_api/services/markets.py:285) reads the last 50 entries and reverses them, but the worker uses `LPUSH`, newest first. Failure: with trades `60…1` retained, the API returns `1…50` instead of `60…11`—reproduced in memory. At capacity, it returns the oldest 50 of 2,000 trades. Align reading/parsing with the writer and test the actual producer ordering.

2. **Missing `/book` and `/trades` endpoints.** [routers/markets.py:89](C:/dev/project-hunter/apps/api/hunter_api/routers/markets.py:89) ends with the candles route. Failure: clients calling the two explicitly planned routes receive 404 even for existing markets. Including these fields in market detail does not fulfill the separate route contract.

3. **Liquidation freshness is absent.** [MarketComponentsOut:116](C:/dev/project-hunter/apps/api/hunter_api/schemas/markets.py:116) exposes only ticker, book, mark, OI and funding. Failure: after liquidations stop arriving, clients cannot determine their last observation or age. Rodada 4 explicitly requires liquidation age independently of the 10-second aggregate rule.

4. **Degradation reasons are discarded.** [markets.py:186](C:/dev/project-hunter/apps/api/hunter_api/services/markets.py:186) consumes `has_gap`, but the response exposes neither gap status nor a reason. Failure: a failed gap with fresh components yields `degraded` alongside three `ok` components, with no explanation; a concurrent stale component also conceals the gap cause. Preserve machine-readable reasons, as required by rodada 4.

**Nice-to-have**

- Replace the fabricated `utcnow()` fallback for malformed trade timestamps in [markets.py:320](C:/dev/project-hunter/apps/api/hunter_api/services/markets.py:320) with explicit invalid-data handling.
- Strengthen acceptance tests: current “book stopped” coverage models absence, and the failed-gap unit test passes a boolean rather than exercising a persisted `failed` row. Add frozen-book, actual expiry, and failed-gap HTTP scenarios.
- Restrict funding kinds to `estimated | realized`; document the worker’s actual heartbeat states and separate process/exchange heartbeat identities.

**Agreements**

- Aggregate precedence is correct: all absent → unavailable; gap/missing required component → degraded; stale required component → stale; otherwise ok.
- Individual qualities survive aggregation; independent `mark_ts`/`oi_ts` prevent OI from rejuvenating mark.
- Request-time age calculation supports aging without new publications.
- Book projection, Decimal string serialization, final-only chronological candles, authenticated global reads and Redis `SCAN` are appropriate.

**Validation:** targeted pytest run with bytecode/cache writing disabled: **54 passed, 337 deselected**, one dependency deprecation warning. Tests currently miss the reproduced trade-order defect. Generated shared types still lack these routes; the planned regeneration and live-worker curl evidence remain outstanding.

No files modified.