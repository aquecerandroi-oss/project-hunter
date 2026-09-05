# Fix brief — T1.3 part A1: persistence path, bounded queues, session timeouts, partition readiness

You are fixing an existing, working implementation. Baseline **verified by the orchestrator right before dispatch**: `uv run pytest services/market-worker -q -p no:cacheprovider` → **83 passed in 77s**. Every item below is an accepted finding with a concrete failure scenario, reconciled from `code-reviewer`, `exchange-integration-specialist`, `database-architect` (two passes, measured against a real Postgres) and an adversarial second opinion from the original implementer (Astra/GPT-6).

Do not redesign. Make the minimal correct change and prove each one with a test that **fails before your change and passes after** — run it before, keep the failure output, then fix.

A second agent (**A2**) is working **in parallel** on `recovery.py`, `sampling.py`, `funding.py`, `universe.py`, `heartbeat.py` and their tests. Touching those files will collide and both diffs will be thrown away.

## Files you may touch (nothing else)
- `services/market-worker/hunter_market_worker/persist.py`
- `services/market-worker/hunter_market_worker/persist_rows.py`
- `services/market-worker/hunter_market_worker/queues.py`
- `services/market-worker/hunter_market_worker/main.py` (only to register the partition readiness check of HIGH-3)
- `services/market-worker/hunter_market_worker/partitions.py` (**new file**, HIGH-3)
- `packages/core/hunter_core/db/session.py` (**only** the two changes of D3)
- `packages/core/tests/**` (only to add/adjust a test for D3)
- `services/market-worker/tests/test_persistence_contracts.py`
- `services/market-worker/tests/db_helpers.py`, `services/market-worker/tests/builders.py` (**additive only** — other modules import them and A2 reads them)
- New test files you create under `services/market-worker/tests/` (suggested: `test_persist_batch.py`, `test_queues.py`, `test_partitions.py`)

**Forbidden (A2 or another task owns them right now):** `services/market-worker/hunter_market_worker/{recovery,sampling,funding,universe,heartbeat,ingest,hot_state,streaming,supervision,publication,config,wire}.py`, `services/market-worker/tests/{test_persist,test_recovery,test_recovery_contracts,test_universe,test_funding,conftest,fakes,test_contracts,test_hot_state,test_ingest_coalesce,test_ingest_integration,test_supervision,test_heartbeat,test_config,test_role_registration}.py`, `services/market-worker/README.md`, everything else in `packages/core` (including `observability.py` — see below), `packages/exchange-adapters/**`, `apps/**`, `infra/**`, `docs/**`, `.env`.

**Already done for you by the orchestrator — use it, do not re-create it:**
- Every new Prometheus metric you need is already declared in `packages/core/hunter_core/observability.py`. Import them; **do not edit that file**:
  `market_liquidation_duplicates_total`, `market_persistence_loss_reports_dropped_total`, `market_snapshot_stale_fields_total`, `market_snapshot_skipped_no_data_total`, `market_sampling_bucket_skipped_total`, `market_ingestion_gaps` (the last four belong to A2; ignore them).
- `hunter_market_worker.persist_rows.oi_bucket(ts)` already exists (5-minute UTC grid, idempotent). Use it instead of the inline `.replace(minute=...)` arithmetic.

**No Alembic migration.** If a fix would need a schema change, report it as NOT FIXED with the exact DDL you would need.
**Never `git commit` / `git push` / `git add` / `git checkout` / `git stash`.**

## Hard rules (CLAUDE.md)
`Decimal` for every monetary/quantity value; **UTC** everywhere persisted, `time.monotonic()` only for watchdogs and internal age; **no file over 350 lines** (`uv run python infra/scripts/check_file_size.py`); `structlog` via `get_logger`, never `print`; no local state on disk; **no fake data** — absence becomes `stale`/`degraded`/`unavailable`, never a stale value republished as fresh; every meaningful mutation observable.

---

## H1 (= MEDIUM-7) — a transient DB blip kills the whole worker through the loss-reporting path
`persist.py:80`. `drain_loop` starts every iteration with an unguarded `await report_losses(factory, exchange_code, queues)`, while the sibling `flush_batch` at `:115` is wrapped in `try/except Exception: runtime.mark_error()`. `report_losses` opens a real `role_session` whenever `queues.losses` is non-empty, which happens routinely (a `Snapshot` "replaced" drop occurs every time a new minute snapshot supersedes one not yet flushed).

**Scenario:** Postgres has a 2 s blip (pool recycle, cold start) while one loss is pending → `report_losses` raises → propagates out of `drain_loop` → `forever("persist", ...)` re-raises → the `TaskGroup` in `main.py` cancels ingest, universe, recovery and heartbeat → the process exits non-zero and the liquidations still buffered in memory are lost. The 30 s readiness grace and the `/ready` 503 exist precisely so this degrades instead of dying.

**Fix:** wrap the `report_losses` call in the same catch-log-`mark_error` pattern as `flush_batch`, leaving `queues.losses` untouched so it retries on the next iteration. Do the same for the `record_system_event("persistence_lag", ...)` call at `persist.py:110` (a raise there kills the loop too).

**Test:** a `report_losses` (monkeypatched) that raises leaves the loop alive, leaves `queues.losses` intact and calls `runtime.mark_error()`.

---

## CRITICAL-1 (= H6) + D10 — the production persistence path inserts one row per round trip
`persist_rows.py` `flush_batch`, the snapshot loop and the open-interest loop at the end of the function. This **is** the production path: `main.py:69-74` always passes `queues`, so `sampling.py`'s batched code never runs for these two tables.

**Measured by the database-architect against a real Postgres:** 400 single-row inserts = **19.85 s** vs **83 ms** for the same rows in one statement. `persist.py:115` wraps the whole flush in `asyncio.wait_for(..., timeout=10)`, so at the target universe of 200 markets the transaction is cancelled before commit, the batch is retried from scratch, and 60 s later the entire queue is discarded by age — including final candles, which then become ingestion gaps.

**Fix:** build **one** `pg_insert(MarketSnapshot).values(list_of_dicts).on_conflict_do_nothing(index_elements=["market_id", "ts"])` and **one** equivalent for `OpenInterestHistory` (bucket via `oi_bucket()`).

**D10 corrects the rationale of the original finding — read this before you code:** a multi-row `INSERT ... ON CONFLICT DO NOTHING` does **not** raise `CardinalityViolation` (only `DO UPDATE` does); PostgreSQL silently keeps the **first** occurrence. That is the wrong one: the later reading is the newer one. So dedupe **in Python, keeping the LAST occurrence per conflict key**, for every one of the five paths:
- `MarketSnapshot` → key `(market_id, ts)`
- `OpenInterestHistory` → key `(market_id, ts)` **after** bucketing
- `Candle` → key `(market_id, timeframe, open_time)`
- `FundingRate` → key `(market_id, funding_time)`
- `Liquidation` → key `(id, ts)`

**Tests:** (a) a batch of 200 snapshots issues exactly **one** `INSERT` for `market_snapshots` — count executed statements with a SQLAlchemy `before_execute`/`before_cursor_execute` event listener or an `AsyncSession` spy; (b) flushing the same batch twice is idempotent (row count unchanged); (c) a batch with two OI readings for the same market in the same 5-minute bucket with **different values** persists the **second** value; (d) two identical liquidations in one batch do not raise and produce one row.

---

## M1 + D7 — deduped and dropped rows are invisible, and dropped rows are still published
`persist_rows.py` `upsert_liquidations` (`ON CONFLICT (id, ts) DO NOTHING` with no `.returning(...)`) and `persist.py:131-133` (publishes **every** liquidation in the batch to `market.liquidations`). Rows whose symbol has no `markets` row are skipped silently inside a flush that reports success (`persist_rows.py` lines guarded by `if ... in market_ids` / `market_ids.get(...) is None`).

**Scenario A:** an overlapping WS reconnect redelivers thousands of liquidations. History stays correct, but the duplicate storm is invisible — an operator watching persisted-liquidation volume drop cannot distinguish "we deduped correctly" from "we are losing data" — and every item is republished to the stream, so downstream consumers double-count.
**Scenario B:** a market is delisted or the universe refresh has not yet inserted a newly listed symbol. Every candle/liquidation/snapshot for it is dropped inside a "successful" flush; nothing counts it, so the data loss is undetectable.

**Fix:**
- `upsert_liquidations` gains `.returning(Liquidation.id)`, computes `len(values) - len(inserted_ids)`, increments `market_liquidation_duplicates_total` by that difference, and **returns the set of ids actually inserted**.
- `flush_batch` returns those ids (change its return type; it currently returns `None`).
- `drain_loop` publishes only the liquidations whose `liquidation_id(item)` is in that set.
- Every row skipped because its symbol is not in `market_ids` increments the **existing** counter in `queues.py`: `losses_total.labels(kind=<the item kind>, reason="unknown_market").inc()`.

**Tests:** insert the same batch twice → on the second pass `market_liquidation_duplicates_total` grew by the batch size and no second publication happened; a batch containing a symbol with no `markets` row bumps `market_persistence_drops_total{reason="unknown_market"}`.

Note for A2 compatibility: `services/market-worker/tests/test_funding.py:45` and `test_persist.py:59` call `flush_batch` and ignore the return value — returning a set keeps them passing. If any test **outside your file list** breaks because of your signature change, do **not** edit it: report it and the orchestrator will handle it.

---

## D11 — liquidation dedupe is exact only to the millisecond
`persist_rows.py` `upsert_liquidations`. `liquidation_id()` (`publication.py:34`) hashes the timestamp truncated to **milliseconds** (`int(ts.timestamp()) * 1000 + ts.microsecond // 1000`), but the row stores the full-microsecond `liq.ts`, and the primary key is `(ts, id)`.

**Scenario:** an exchange (or a normalization path) delivers the same liquidation twice with `ts` differing by microseconds. `id` is identical, `ts` is not → the conflict target `(id, ts)` does not match → the same liquidation is stored twice and the notional is double-counted by every consumer.

**Fix:** truncate the stored `ts` to the millisecond in `upsert_liquidations` (`liq.ts.replace(microsecond=(liq.ts.microsecond // 1000) * 1000)`), so the persisted key is exactly the key the id was computed from. Do **not** touch `publication.py`. Do not use a bare `assert` (it is stripped under `-O` and, when it does fire, it kills the whole flush).
**Test:** two liquidations identical except for sub-millisecond `ts` produce one row.

---

## MEDIUM-8 — the loss path opens duplicate, and sometimes bogus, ingestion gaps
`persist.py:59-69`. `report_losses` adds an `IngestionGap` for every dropped final candle with no coverage check and no dedupe.

**Scenario:** the same final candle is dropped twice (redelivery, then a capacity drop) → two identical `open` gaps for the same minute → `recovery.py` backfills the same minute twice, forever, and `heartbeat.open_gaps` overstates the damage. Worse: the flush times out **after** the Postgres commit succeeded, the batch is retried and dropped by age, and a gap is opened for a candle that is already persisted — a permanent phantom gap.

**Fix (no migration):** inside the same `role_session`, before adding gaps, load in **one** query the `Candle.open_time` values already persisted for the affected `(market_id, timeframe)` in the range of the dropped candles, and in **one** query the existing `IngestionGap` rows for those markets with `status in ('open','failed')`. Skip a candle whose `open_time` is already persisted or already covered by an existing gap. Deduplicate the candles inside the batch itself first.
**Test:** dropping the same final candle twice creates exactly one `ingestion_gaps` row; dropping a candle that is already persisted creates none.

---

## D2 — the loss queue raises and kills the process when Postgres is down
`queues.py:134-138`. `drop()` raises `RuntimeError("persistence loss reporting queue exhausted")` once `losses` reaches `max_items` (5000). `_enqueue` in the ingest path only catches `QueueFull`.

**Scenario:** Postgres is unreachable. With H1 in place, `report_losses` now fails safely and never drains `losses`; every dropped item keeps appending. At the ingestion rate of 200 markets this reaches 5000 in roughly nine minutes, `drop()` raises out of the ingest path, `forever` treats it as fatal and the process dies — exactly the failure H1 exists to prevent. Losing the *report* of a loss must never be worse than the loss itself.

**Fix:** `self.losses` becomes `deque[Loss](maxlen=max_items)`; `drop()` **never raises**; when the deque is already full, the eviction is counted in `market_persistence_loss_reports_dropped_total` (compare `len(self.losses)` before and after the append, or check `len == maxlen` before appending) and logged once at warning level.
**Test:** `PersistQueues(max_items=4)`; five `drop()` calls do not raise, `len(queues.losses) == 4`, and `market_persistence_loss_reports_dropped_total` grew by 1.

Careful: `report_losses` at `persist.py:70-71` pops exactly as many items as it read (`for _ in losses: queues.losses.popleft()`). With a `maxlen` deque, items can be evicted from the **left**… they cannot: `append` evicts from the left when full. So a concurrent eviction during the awaited session could make `popleft()` remove items that were never reported, or raise `IndexError` on an empty deque. Make the drain robust: snapshot the reported items, then remove exactly those (e.g. pop up to `len(reported)` items but stop when the deque is empty) and never let it raise.

---

## D3 — no statement or command timeout anywhere; a cancelled flush hangs the drain loop forever
`packages/core/hunter_core/db/session.py:41-50` (`create_engine`) and `:90-114` (`_apply_context`). The server runs with `statement_timeout = 0` and `lock_timeout = 0`.

**Scenario:** `persist.py:115` cancels `flush_batch` after 10 s. `asyncio.wait_for` then awaits the task's cancellation, which awaits asyncpg's `ROLLBACK` and connection close **on a socket whose peer is gone** (a partition, a killed pooler). Without `command_timeout` that await never returns: `drain_loop` is stuck forever, `queues.persistence` keeps `/ready` false, and nothing restarts the container because the process is alive and the loop is not crashing. `wait_for` is only a backstop; the driver needs its own deadline.

**Fix:**
1. `create_engine`: add `"command_timeout": 30` to `connect_args` (asyncpg per-command deadline).
2. `_apply_context`: after the `SET LOCAL ROLE`, when `db_role == "hunter_worker"`, execute `SET LOCAL statement_timeout = '15s'`. Only for that role — the API's `hunter_app` transactions are not in scope for this task and must keep their current behaviour. Keep it a literal in the SQL text (a `SET LOCAL` value cannot be a bound parameter); it is a constant, not caller input.
3. Document both in the module docstring, in the same style as the existing prepared-statement note.

**Tests (`packages/core/tests/**`):** an integration test that opens `role_session(..., db_role="hunter_worker")` and asserts `SHOW statement_timeout` returns `15s`, and that a `hunter_app` session does not have it set to `15s`. The whole core suite must stay green: `uv run pytest packages/core -q -p no:cacheprovider` (it includes integration tests against the Docker Postgres, which is up).

---

## HIGH-3 — a missing partition aborts every write and nothing sees it coming
`infra/migrations/ddl/partitions.py:66-71` creates partitions only through **2026-12**, and nothing in M1 schedules `infra/scripts/create_partitions.py`.

**Scenario reproduced by the database-architect:** on 2027-01-01 the first candle insert fails with `no partition of relation "candles_1m" found for row`. That error aborts the **whole** transaction, so snapshots, funding, liquidations and candles in the same flush are all lost, the batch is retried and discarded by age, and `recovery.py` marks every gap `failed`. Today the operator learns about it from missing data, hours later.

**Fix (detection only — scheduling `create_partitions.py` is out of scope for T1.3 and is already recorded as a follow-up):** new module `services/market-worker/hunter_market_worker/partitions.py` with an async check that, for `candles_1m`, `market_snapshots` and `liquidations`, verifies a partition exists that would accept `utcnow() + 1 day`. Use the existing name helpers from `hunter_core.db.models` (`partition_name(table, year, month)`, `list_partition_name("candles", "1m")` — read `packages/core/hunter_core/db/models/_partitions.py` first) and `SELECT to_regclass(:name)`; do not hand-roll new naming rules.
- On startup (called from `main.py` before the `TaskGroup`, or as the first action of a task inside it) log the result and, when a partition is missing, emit a `system_event` with severity **CRITICAL** via `hunter_market_worker.heartbeat.record_system_event` (DATABASE.md §1.3) — import it, do **not** edit `heartbeat.py`.
- Register the check in `runtime.readiness_checks` (the same list `main.py:41` uses) so `/ready` returns 503 while a partition is missing, and remove it in the `finally` block like the two existing checks. Re-check periodically rather than caching a startup result forever — a cheap re-check every few minutes is enough; a missing partition must not require a restart to be noticed, and a present one must not cost a query per readiness probe.
- The check must **fail open on a database error** (return "ready" and log) — a Postgres blip already has its own signal; do not let this check add a second way to wedge readiness.

**Tests:** with the current test database (partitions exist through 2026-12) the check passes for `utcnow() + 1 day`; monkeypatch the clock (or the target date) to 2027-02 and the check fails, returns not-ready and records a CRITICAL `system_event` row.

---

## Explicitly NOT in scope (do not "fix" these)
- **M4 of the older brief (`spread_pct` × 100) is WRONG and must NOT be applied.** `docs/DATABASE.md:12` and `_common.py:23` define `NUMERIC(9,6)` percentages as a **fraction** (0.012 = 1.2%). `sampling.py` is correct; the domain helpers are the divergent ones, and fixing them is follow-up **T1.1c**, outside T1.3. It is A2's file anyway.
- `lock_timeout` in `infra/scripts/create_partitions.py` and UTC-explicit partition bounds (D4, D12) — out of T1.3, already recorded in the plan.
- Anything in `packages/exchange-adapters/**`.
- The loss of a `market.liquidations` publication when the process dies between the Postgres commit and the `XADD` — an accepted M1 limitation (transactional outbox is an M2 follow-up).
- Any Alembic migration.

## Verification you must run and paste verbatim in your report
```bash
export PATH="/c/Program Files/nodejs:/c/Users/evert/AppData/Roaming/npm:/c/Users/evert/AppData/Local/Microsoft/WinGet/Packages/astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe:/c/Users/evert/.local/bin:/c/Users/evert/AppData/Local/Programs/DockerDesktop/resources/bin:$PATH"
cd /c/dev/project-hunter
uv run pytest services/market-worker -q -p no:cacheprovider
uv run pytest packages/core -q -p no:cacheprovider
uv run ruff check services/market-worker packages/core && uv run ruff format --check services/market-worker packages/core
uv run pyright services/market-worker packages/core
uv run python infra/scripts/check_file_size.py
```
Docker Desktop is running; the integration tests have Postgres and Redis. Failures in `test_recovery*.py`, `test_sampling*.py`, `test_universe.py`, `test_funding.py` or the snapshot tests in `test_persist.py` are **A2's work in flight** — say so explicitly and report the result for your own files.

## Before you report DONE — mandatory second opinion (`.claude/rules/astra-second-opinion.md`)
```bash
bash infra/scripts/astra.sh ask T1.3-A1 "Review the current services/market-worker/hunter_market_worker/{persist,persist_rows,queues,partitions,main}.py and packages/core/hunter_core/db/session.py. Focus: multi-row ON CONFLICT DO NOTHING correctness and Python-side dedupe keeping the LAST row per key; the bounded loss deque never raising and report_losses draining it safely under concurrent eviction; statement_timeout/command_timeout side effects on existing sessions; the partition readiness check failing open. Rules: Decimal, UTC, no fake data, no file over 350 lines. Answer in Portuguese: must-fix with a concrete failure scenario, nice-to-have, what you would do differently, what you agree with."
```
Include her answer in your report under **"Segunda opinião (Astra)"**: what she flagged, what you fixed, what you rejected and why. If `codex` is unavailable, write "Astra indisponível: <erro>" and continue — never block, never invent her answer.

## Report format (final message; do not write a report file)
One line per finding ID (H1, CRITICAL-1/H6+D10, M1+D7, D11, MEDIUM-8, D2, D3, HIGH-3): FIXED / NOT FIXED + why, the `file:line` you changed, the name of the test that proves it. Then the verbatim command outputs. Then anything you found and did **not** change, with its failure scenario. Then "Segunda opinião (Astra)". **Do not commit.**
