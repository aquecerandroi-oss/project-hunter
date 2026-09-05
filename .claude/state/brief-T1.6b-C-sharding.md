# Brief T1.6b-C — sharding do market-worker por símbolo (owner: backend-specialist)

## Why (measured, not guessed)
`.claude/state/t16b-profile.md`. At 200 markets one process is at **99.9% of one core** and the
transport layer alone (TLS + websockets frame parsing + permessage-deflate) is ~25% of a core at
50 markets and scales with bytes — so at 200 markets the transport **by itself** costs ~100% of a
core even if every line of our application code became free. Two other agents are making the
application code cheap in parallel; that decides *how many* shards we need, not *whether*.

**Sharding is the only path to the target** (200 markets, `markets_ok` >= 95%, **< 70% of one core
per shard**, zero dropped events).

## Files you may touch (nothing else)
- `services/market-worker/hunter_market_worker/{config.py,universe.py,heartbeat.py,main.py}`
- `services/market-worker/tests/**` (only files that do not exist yet, plus
  `test_config.py`, `test_universe.py`, `test_heartbeat.py`, `test_role_registration.py`)
- `packages/core/hunter_core/{settings.py,observability.py}`
- `infra/docker/**`
- `obsidian/09-OPERATIONS/Monitoring.md`

**Do NOT touch**: `services/market-worker/hunter_market_worker/{streaming.py,hot_state.py,ingest.py,persist.py,queues.py,recovery.py,funding.py}`
(another agent is in those right now), `packages/exchange-adapters/**` (a third agent),
`apps/**` (hard constraint — see C3), `packages/core/hunter_core/domain/**`, `.env`.

## The design to implement (challenge it in your report if you find a hole)

### C1 — `MARKET_SHARD` in Settings
`packages/core/hunter_core/settings.py`: add `market_shard: str = "0/1"` (env `MARKET_SHARD`),
format `"<index>/<total>"`. Validate: `total >= 1`, `0 <= index < total`, both integers — an invalid
value must fail at startup with a clear message, never silently fall back. Expose parsed
`shard_index` / `shard_total` properties. Default `"0/1"` means **exactly today's behaviour**
(single process, whole universe) so nothing changes for anyone who does not set it.

### C2 — stable symbol assignment, applied once in `universe.py`
`zlib.crc32(symbol.encode("ascii")) % shard_total == shard_index`. Stateless, restart-safe,
refresh-safe, no coordination. Apply it in **one** place: the list handed to
`MonitoredUniverse.set()`. Everything downstream — ingest subscriptions, `run_funding`,
`oi_poll_loop`, `snapshot_loop`, `run_recovery` (already scoped by `universe.symbols`, see
`recovery.py:304-309`) — inherits the scoping for free. Do not add a shard filter anywhere else.

Tests: with the real 200-symbol shape, every symbol lands on exactly one shard for N in {1,2,3,4};
the union over all shards is the full set; the assignment is stable across processes and restarts;
N=1 yields the whole universe unchanged.
Also **report the balance you measure** (symbols per shard for N=2,3,4). Load is proportional to
volume and volume is heavy-tailed, so a hash can put BTCUSDT and ETHUSDT on the same shard. We
accept that for now and will measure per-shard CPU in the proof — but say in your report what the
worst-case imbalance was, so the orchestrator can pick N with evidence.

### C3 — heartbeat: per-shard keys **plus** the canonical aggregate (the API must not change)
`apps/api/hunter_api/services/system_status.py` reads exactly one key per exchange,
`hb:market:{exchange}`, and `apps/**` is off-limits. So:
- each shard writes its own per-shard hash with the same fields as today, TTL 30 s. **Key name:
  `mktshard:{exchange}:{shard_index}` — deliberately NOT under `hb:*`.** Astra's finding, with a
  concrete failure: `/api/v1/system/workers` scans `hb:*` generically
  (`system_status.py:214`), so `hb:market:binance:{i}` keys would show up there as phantom
  "workers" the operator never deployed. Keep them out of that namespace.
- the canonical `hb:market:{exchange}` is recomputed **atomically in a single Lua script**
  (`EVALSHA`, with an `EVAL` fallback on `NOSCRIPT`) that reads the `shard_total` expected
  per-shard keys and writes the aggregate with its TTL in the same execution. N comes from config
  — **no `SCAN`**. Any shard may run it, every heartbeat tick.

  **Why Lua and not read-then-write in Python** (Astra, must-fix, real race): shard A reads all N
  hashes and finds them healthy, then its coroutine is descheduled; shard B reads, sees shard 2
  expired, and writes `disconnected`; A resumes and overwrites with `connected`, renewing the TTL
  on a stale conclusion. The operator sees green while a fifth of the universe is dark. Read and
  write must be one atomic step.

Aggregation rules — correctness requirements, write a test for each:
- a per-shard key that is **missing, expired, or whose `last_event_at` is older than a 15 s
  freshness window** counts as a **failing shard**, never as "just exclude it from the max";
- `ws_state` = the worst state across the shards **and forced to `"disconnected"` if any expected
  shard is failing by the rule above. Failure scenario this closes: shard 2 dies, its key expires
  in 30 s, and the aggregate keeps saying `connected` with 150 subscriptions while 50 markets go
  dark;
- `last_event_at` = **minimum** across the shards, **not** the maximum. The maximum means "some
  shard saw an event", which proves nothing about the others; the API turns this field directly
  into the staleness the operator sees;
- `subscriptions` = **sum**. Do not conflate it with a count of monitored markets — they are
  different numbers (`heartbeat.py:76` vs `:162`) and the API treats them differently;
- `reconnects`, `dropped_events`, `open_gaps` = sum across the **live** shards, and the field
  comment/report must say plainly that this is a *transient* sum, not a durable total: a shard that
  restarts resets its own counter. The durable series stays in the Prometheus counters, per process;
- `last_error` = any non-empty error, prefixed with the shard index;
- an expected shard with an empty symbol set is a legitimate `idle`; a shard that never
  initialized is **not** the same thing — keep that distinction (it already exists at
  `heartbeat.py:206`);
- if a shard loses Redis it stops writing, its key expires and the aggregate degrades — correct.
  If **every** shard loses Redis, the canonical key must be allowed to expire too. Never publish an
  aggregate computed from a local cache;
- with `shard_total == 1` the canonical key must be **byte-for-byte what it is today** — prove it
  with a test. That is the no-regression guarantee for the current single-process deployment.

**`rt:system` pub/sub (Astra, must-fix):** `heartbeat.py:90` publishes the *local* status to
`rt:system` on every tick. With N shards the UI would flicker between shards' opinions. Publish the
**aggregate** on `rt:system`, computed by the same script, exactly once per tick per shard (the
payload is identical from every shard, so a duplicate is harmless; a contradictory one is not).

Note `WorkerRuntime.instance` already defaults to `hostname:pid`, so the generic
`hb:{role}:{instance}` keys are unique per shard container with no change.

### C4 — universe refresh: one leader, everyone else consumes
`refresh_universe` (`universe.py:108-168`) does REST + a global
`UPDATE markets SET is_monitored = false` + re-rank + `market.universe.changed`. N shards running
it concurrently would fight over the same rows every cycle and publish spurious change events, and
would burn N× the REST budget.

Implement: before refreshing, try `SET market:universe:leader:{exchange} <token> NX EX 60` where
`<token>` is a per-run random value (not the instance name).
- **Leader** (lock acquired): runs `refresh_universe` exactly as today, then publishes the full
  monitored list to `market:universe:{exchange}` (a Redis key with the sorted symbol list, a
  UTC ISO `computed_at` and a **monotonically increasing `version`**, TTL = 3 ×
  `market_universe_refresh_s`), and re-acquires/extends the lock well before expiry while it keeps
  running. **Release and extension must be token-checked** (a Lua compare-and-delete /
  compare-and-expire), and the snapshot write must **reject a lower `version`** than the one already
  stored. Astra's must-fix, concrete scenario: the leader's process is paused (GC, host stall) past
  the 60 s TTL, another shard takes the lock and publishes version 8; the old leader wakes up,
  believes it is still the leader, and overwrites with its stale version 7 — the whole fleet then
  subscribes to a universe that is one cycle old. `SET NX EX` alone does not prevent this; the
  version guard on the resource being written does.
- **Follower** (lock held by someone else): reads `market:universe:{exchange}`; if the key is
  missing or older than 3 × the refresh interval, falls back to reading `is_monitored` markets
  from Postgres; if that is empty too, it stays `idle` (the existing behaviour for an empty
  universe) and retries on the existing backoff — it must **not** call REST and must **not** write
  `is_monitored`.
- Both then apply the C2 filter and call `universe.set(...)`.

Failure scenarios to cover with tests: leader dies mid-cycle (lock expires, another shard takes it
within 60 s, no double refresh in the meantime); a paused leader waking up cannot overwrite a newer
version (see above); Redis is down (every shard falls back to Postgres and keeps its current
universe rather than emptying it — an empty universe means the worker stops collecting, which is
far worse than a stale one); the lock value is token-checked before release so a shard never
deletes a lock it no longer owns.

A restarted follower must load the **full snapshot**, never wait for the next `added/removed` diff
(`universe.py:148` publishes only a diff, and only after the DB transaction — a leader that dies
between commit and publish loses the notification entirely). The snapshot key is the source of
truth for followers; the `market.universe.changed` stream stays exactly as it is today, as a
notification. **Do not introduce a consumer group for it** — a group would hand each event to one
shard only, so the others would never learn about the change.

### C4b — per-shard recovery budget
`recovery.py:38` caps a cycle at 50 gaps. With N shards each owning ~1/N of the symbols, the
aggregate rate becomes up to 50 × N gaps per cycle against a REST budget that did not grow. Scale
the per-shard cap so the global budget is preserved (`max(1, ceil(cap / shard_total))`) and say in
your report what value each shard gets for N = 1..4. Do **not** edit `recovery.py` (another agent
owns it) — if the cap cannot be injected from `config.py`/`main.py`/settings without touching that
file, say so in your report and leave it as a documented follow-up rather than reaching into
someone else's file.

### C5 — Compose topology
Do **not** use `deploy: replicas` — Compose gives replicas no stable ordinal to derive
`MARKET_SHARD` from, and deriving it from a container hostname is fragile.

Instead: keep `market-worker` in `docker-compose.yml` exactly as it is today (implicitly shard
`0/1` — the default, nothing changes for anyone), and add a **new committed file**
`infra/docker/docker-compose.shards.yml` that redefines `market-worker` as `MARKET_SHARD: "0/N"`
and adds `market-worker-1` … `market-worker-{N-1}` from a YAML anchor carrying the shared config
(image, env, `depends_on`, `restart: unless-stopped`, the measured healthcheck budgets). Start with
**N = 4** — the orchestrator will change it after measuring, so make changing N a matter of editing
one anchor plus adding/removing a block, and say in your report exactly which lines to touch.
Also check and report: the Postgres `max_connections` budget against N shards × the per-process
pool (`packages/core/hunter_core/settings.py:51`) — N processes each open their own pool, and
running out of connections at shard 4 is a silent, late failure. Usage, documented in a comment at
the top of the file:
```
docker compose -f infra/docker/docker-compose.yml \
               -f infra/docker/docker-compose.override.yml \
               -f infra/docker/docker-compose.shards.yml up -d
```
Every shard keeps its own `/ready` on port 8001 (no published ports, so no conflict) and its own
healthcheck. A shard is ready when **its own** symbols are ready — that follows from
`readiness_checks` reading `universe.symbols`. Verify and say so.

**Known limitation you must state, not fix here** (Astra): `IngestionHealth`
(`supervision.py:43,60`) judges readiness from the connection state and a single `last_data`
timestamp, so one recent event from one symbol keeps a shard "ready" while many of its markets are
dark. Per-symbol coverage in readiness is a real gap — but `supervision.py` belongs to another
agent this wave and the operator is not blind to it (`markets_ok` in `/system/market-status` is
computed per market). Record it in your report as a follow-up with this scenario; do not implement it.
A shard whose assigned set is legitimately empty may be ready **after** it has initialized and
validated its assignment; a misconfiguration that yields an empty list must never look like a
healthy `idle`.

`entrypoint.sh` needs no change (`HUNTER_ROLE=market` already dispatches). Confirm, do not touch it
unnecessarily.

### C6 — the saturation metric the operator was promised
`packages/core/hunter_core/observability.py`, both sampled in the **heartbeat loop (every 5 s)**,
never in the hot path:
- `market_ws_queue_depth` — Gauge, labels `("exchange", "shard")`: current
  `len(consumer.queue)` (the adapter's `BoundedEventQueue`). A queue sitting near `maxsize` is the
  earliest, cheapest signal of "this shard cannot keep up".
- `market_ws_receive_event_age_seconds` — Gauge, labels `("exchange", "shard")`: `now -` the
  exchange event time of the last frame **read off the socket**, from the adapter's existing
  per-connection `ConnectionState`. Report the **worst** connection. This measures silence on the
  wire.
  **Must-fix (Astra):** do not treat `ConnectionState.last_data_event_ts` as if it were always the
  frame's `E`. `ws.py:250` (`_frame_ts`) prefers `event.ts` and falls back to `close_time`, which
  for a partial candle is in the **future** — a clock-skewed or future timestamp would show up as a
  healthy zero lag. Clamp at 0 and, when the value is ahead of now by more than the clock-skew
  tolerance, report it as skew (a separate log/field), never as "fresh".
  Name it after what it measures — this is the *reader's* age, and the whole point of T1.6b is that
  a fresh reader can sit in front of a starved consumer. Do not call it the consumer's lag.
- `market_event_lag_seconds` — Gauge, labels `("exchange", "shard")`: `now -` the event time of the
  **oldest event still waiting in the queue** (queue head; `deque[0]` is O(1)). This is the
  consumer's real backlog and is the number that would have caught T1.6's failure early.
  If exposing the queue head cheaply requires a change in the adapter package, say so and leave the
  gauge unregistered rather than guessing — do not reach into another agent's file.
Labels must stay bounded — `exchange` and `shard` only, never a symbol. Add both fields to the
per-shard heartbeat hash too (`queue_depth`, `event_lag_s`) so an operator can read them with
`redis-cli HGETALL hb:market:binance:0` without Prometheus. Do **not** add them to the canonical
aggregate hash if that risks changing what the API already parses — check
`apps/api/hunter_api/schemas/system.py` (read-only) and say what you found.
Document both in `obsidian/09-OPERATIONS/Monitoring.md`: name, type, what value means trouble, and
the command to read it.

Ask the adapter for the queue depth through a small public accessor rather than reaching into a
private attribute — but the adapter package is owned by another agent right now, so if no public
accessor exists, read `BinanceWsClient._consumer.queue` defensively (`getattr` chain, `None`-safe)
and leave a `# TODO(T1.7)` naming the accessor you want. Never let a missing attribute raise in the
heartbeat loop.

## Verification you must run and paste (real output, not a claim)
```
uv run pytest services/market-worker -q -p no:cacheprovider
uv run pytest packages/core/tests/unit -q -p no:cacheprovider
uv run ruff check services/market-worker packages/core
uv run ruff format --check services/market-worker packages/core
uv run pyright services/market-worker packages/core
uv run python infra/scripts/check_file_size.py
docker compose -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.shards.yml config
```
The last one must render without error — that is the proof the compose file is valid; do not start
the shards yourself (the orchestrator runs the 200-market proof).

## Hard rules (CLAUDE.md)
Money is `Decimal`, never `float`. Every timestamp is timezone-aware UTC. No local state files —
Postgres + Redis only. No file over 350 lines. No secrets, never read `.env`, never log a key name
or a connection string. No fake data: if a shard has no data, the aggregate must say so, not
invent a healthy state. `structlog` only, no `print`.
**Do not commit** — Sexta-feira commits per task.

## Report format
`## Segunda opinião (Astra)` is mandatory. Before reporting, run (note the `< /dev/null`, without
it `codex` hangs on stdin):
`bash infra/scripts/astra.sh ask t16b-C-diff "<your question about your own diff>" < /dev/null`
and say what she flagged, what you fixed, what you rejected and why. If Astra is unavailable, say
"Astra indisponível: <erro>" and continue — never fake her answer.
Then: what changed per file · the symbol-balance table for N=2,3,4 · the real output of every
verification command · every failure scenario you tested and the test that proves it · what you
did NOT do and why · what you would need from `apps/**` if the constraint were lifted.

---

## Segunda opinião (Astra) — já absorvida neste brief
Full answer: `.claude/state/astra-review-t16b-sharding.md` (asked before implementation).

**Absorbed above** (each with its failure scenario): the aggregate must be written by an atomic Lua
script, not read-then-write (interleaving race); a missing/expired/stale shard is a failure, never
an exclusion; `last_event_at` = min with a 15 s freshness window; `subscriptions` is not a market
count; the summed counters are transient, not durable totals; `rt:system` must carry the aggregate,
not each shard's local opinion; per-shard hashes go outside the `hb:*` namespace so
`/system/workers` does not grow phantom workers; the leader lock needs a token and the snapshot
needs a version guard (a paused leader waking up must not overwrite a newer universe); a restarted
follower loads the full snapshot, never waits for a diff; no consumer group for
`market.universe.changed`; the recovery cap must be divided by N; Postgres `max_connections` vs
N pools; the receiver's age is not the consumer's lag, and `_frame_ts` can be in the future.

**Recorded, deliberately not done in this task** (say so again in your report):
- Per-symbol coverage in readiness (`supervision.py`) — real gap, other agent's file, and
  `markets_ok` already exposes it to the operator.
- The per-IP `Retry-After` cooldown in `rate_limit.py:114` is **not** distributed: shard A gets a
  429 and backs off while shard B keeps calling from the same IP, which is how an IP earns a 418
  ban. Being handled separately by the agent that owns `packages/exchange-adapters/**` — do not
  touch it, but do not run N shards against the real exchange until it lands.
- Dynamic rebalancing, autoscaling, automatic ownership failover: out of scope.

**Where the orchestrator differs from Astra, and why:**
- Astra budgets **6 shards**; this brief starts at **4**. Her arithmetic deliberately removed only
  pydantic and JSON from the 50-market run, leaving in the O(n) queue eviction (17.8% of a core at
  200 markets), the `@depth20@500ms` halving of a 23% cost, the two-round-trip Redis writes and the
  per-event task/timer — all of which are being removed this wave. N is a **measured** result: the
  proof run decides it, and the file is written so changing N is one anchor plus one block.
