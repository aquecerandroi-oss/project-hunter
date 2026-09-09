"""System/operations read payloads — ARCHITECTURE.md §5.3/§11.

**``hb:{role}:{instance}`` — HASH, TTL 30s (``hunter_core.redis.keys.heartbeat``,
written by ``hunter_core.runtime.WorkerRuntime.write_heartbeat``)**

- ``ts``: ISO-8601 UTC datetime string — when this hash was last written.
- ``last_success``: ISO-8601 UTC datetime string, or ``""`` if the process has
  never completed a unit of work yet.
- ``errors``: decimal-integer string — error count since process start.
- ``version``: the running package version string.

``GET /api/v1/system/workers`` ``SCAN``s every ``hb:*`` key (never ``KEYS`` —
this runs against the shared production Redis, and ``KEYS`` blocks it). The
role and instance are parsed back out of the key itself
(``hb:{role}:{instance}``, split once), and ``age_s``/``status`` are derived
here, not stored: ``alive`` at ``age_s <= 15``, ``late`` at ``<= 30``,
``dead`` otherwise (a row this old would usually have already expired via its
30s TTL — ``dead`` mostly guards the read racing the expiry, not a normal
steady state). A ``ts`` more than a small clock-skew tolerance ahead of "now"
is likewise reported ``dead`` rather than ``alive`` — a producer clock stuck
in the future is not a live heartbeat, whatever the naive age looks like.

**``instance`` anonymization (F5/G2).** Every authenticated member of any
organization can read this endpoint, and ``WorkerRuntime.instance`` defaults
to ``f"{socket.gethostname()}:{os.getpid()}"`` — so this field is replaced
with a stable, non-reversible 12-hex digest of ``sha256(f"{role}:{instance}")``
whenever ``instance`` is not a plain lowercase slug (contains ``:``, or any
character outside ``[a-z0-9-]``). The rule is keyed on the *shape* of
``instance``, never on ``role``: the market worker entrypoint constructs
``WorkerRuntime(role="market")`` without an explicit ``instance``, so it
still falls back to the generic ``hostname:pid`` default and writes it under
``hb:market:{hostname}:{pid}`` alongside the per-exchange
``hb:market:binance`` hash — a role-only exception would leak that one
verbatim. A plain slug like ``binance`` (``hb:market:binance``) is
meaningful, non-sensitive data the UI displays as-is. Two reads of the same
non-slug instance still correlate (the digest is deterministic), but the
hostname and PID this API's own ``os``/``socket`` calls would otherwise leak
never reach the response.

**Redis unavailable vs. genuinely empty (G4).** A ``hb:*`` scan or heartbeat
read that fails outright (Redis unreachable, or a key raising ``WRONGTYPE``)
is reported as ``503 application/problem+json`` — never as the same ``200``
shape a healthy, idle cluster would return — so a client (and the humans
reading its UI) can tell "the service can't tell you right now" from "there
is genuinely nothing to report". The problem ``detail`` never names the
Redis key, command or connection string. ``/system/market-status`` applies
the same rule only when *every* exchange's read failed wholesale; one
exchange's own heartbeat misbehaving still degrades just that row.

**Per-exchange market heartbeat extension.** M1.md: "Heartbeat por exchange em
``hb:market:{exchange}``" — the market worker calls ``WorkerRuntime`` with
``instance=<exchange code>`` (e.g. ``hb:market:binance``), so the generic
fields above already identify it. On the *same* hash, T1.3's worker
additionally writes:

- ``last_event_at``: ISO-8601 UTC datetime — last exchange event actually
  received (ticks/book/etc.), independent of the generic heartbeat tick.
- ``ws_state``: the adapter's own connection state — ``"connecting"``,
  ``"connected"``, ``"reconnecting"``, ``"disconnected"`` or ``"idle"``
  (empty universe); passed through verbatim, not validated against this
  list — **except** on ``/system/market-status``, where a ``last_event_at``
  more than ``CLOCK_SKEW_TOLERANCE_S`` ahead of "now" (G6) is not evidence
  of a live feed: that row's ``last_event_at``/``last_event_age_ms`` are
  reported absent and ``ws_state`` is forced to ``"unavailable"`` rather
  than trusting a timestamp that cannot be real.
- ``subscriptions``: decimal-integer string — symbols currently subscribed.
- ``reconnects``: decimal-integer string — reconnect count since start.
- ``markets_monitored``: decimal-integer string — the worker's own view of
  how many symbols it is watching (self-reported; ``/system/market-status``
  uses the Postgres ``is_monitored`` count instead, which stays correct even
  when this worker has never run).
- ``open_gaps``: decimal-integer string — the worker's own open-gap count.

These six are optional on every row (``None`` when absent, which is every
non-``market`` role) — this API never fabricates them.

``GET /api/v1/system/market-status`` reads ``hb:market:{exchange}`` for every
row in the (global, no-RLS) ``exchanges`` table, alongside
``markets.is_monitored`` counts and open ``ingestion_gaps`` counts from
Postgres. ``ws_state`` is reported ``"unavailable"`` — not one of the three
worker-written states — when the exchange has no heartbeat hash at all.

**Sharded collector (T2.5g).** With ``MARKET_SHARD=i/N`` and ``N > 1`` the
market worker writes ``hb:market:{exchange}:{i}of{N}`` instead, adding
``shard_index``/``shard_total`` (also present, as ``0``/``1``, on the solo
key). ``/system/market-status`` unions them
(``services/market_shards.py``): ``ws_state`` is the worst shard's, or
``"stale"`` — a fifth value, meaning the *cluster*, not one socket — whenever
``shards_reporting < shards_expected``; ``last_event_at`` is the **oldest**
shard's; ``reconnects`` is the sum. ``markets_monitored`` and ``open_gaps``
stay Postgres's, never a sum of self-reported shard fields, which would lose
exactly the shard that is missing. With nothing reporting,
``shards_expected`` is ``null`` (unknown topology), never ``1``. A sharded
collector does **not** publish ``rt:system`` at all: that message replaces a
whole exchange row on the System page, and one shard knows only its own 50
markets.

**Per-execution-worker heartbeat extension (T3.13).** The paper wallet
(``HUNTER_ROLE=execution``) writes its own hash,
``hb:execution:paper`` (``services/execution-worker/hunter_execution_worker/
heartbeat.py``), on the *same* ``hb:{role}:{instance}`` shape the generic scan
above already parses (``role="execution"``, ``instance="paper"``) — no
execution-specific code was needed in ``scan_heartbeats`` itself, exactly as
T2.6 already proved for the scanner role. On top of the four generic fields,
that hash carries:

- ``equity``: the last equity written, as a decimal string (never a float);
- ``kill_switch``: the kill switch state this process last read and is
  obeying (``ACTIVE``/``WARNING``/``TRADING_DISABLED``/``EMERGENCY``);
- ``open_positions``, ``pending_requests``, ``unreadable_requests``: counts,
  as decimal-integer strings;
- ``degraded_protections``: how many fired-but-unfilled protections are
  currently waiting for a book;
- ``protection_delay_s``: seconds the *oldest* of those has been waiting —
  ``0`` when none are degraded. This is the number ``docs/DEPLOYMENT.md``
  calls "atraso de proteção";
- ``last_mtm``, ``last_protection``, ``last_kill_switch_read``: ISO-8601 UTC
  timestamps of the last successful pass of each cycle, or ``""`` before the
  first one. The age of ``last_mtm`` against ``ts`` is "atraso do MTM" —
  reported here as the raw timestamp, not a pre-computed age, so a client
  reads it against its own clock the same way ``age_s`` already is for the
  generic fields;
- ``paper_autonomy``: ``"true"``/``"false"`` — whether ``ENABLE_PAPER_AUTONOMY``
  is set on this process (T3.14's gate; always ``false`` until that task
  lands).

These eleven are optional on every row (``None`` when absent, which is every
non-``execution`` role) — same rule as the market extension above: this API
never fabricates a field a worker did not publish.

**What is deliberately *not* here: outbox lag.** ``heartbeat.py`` does not
write an ``outbox_pending`` (or similar) field to ``hb:execution:paper`` —
only the worker's own ``/ready`` (``outbox_not_lagging``, on its
``HEALTH_PORT``, not reachable through this API) turns outbox lag into a
boolean. Adding a numeric field here would mean inventing one the worker does
not publish, which the brief for this task explicitly forbids; it is
registered as a gap for whoever next touches
``hunter_execution_worker/heartbeat.py`` (T3.14 is in flight there).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class WorkerLivenessStatus(StrEnum):
    ALIVE = "alive"
    LATE = "late"
    DEAD = "dead"


class WorkerHeartbeatOut(BaseModel):
    role: str
    instance: str
    ts: datetime
    last_success: datetime | None = None
    errors: int
    version: str | None = None
    age_s: float
    status: WorkerLivenessStatus
    last_event_at: datetime | None = None
    ws_state: str | None = None
    subscriptions: int | None = None
    reconnects: int | None = None
    markets_monitored: int | None = None
    open_gaps: int | None = None
    # T3.13 — hb:execution:paper only (schemas/system.py module docstring).
    equity: str | None = None
    kill_switch: str | None = None
    open_positions: int | None = None
    pending_requests: int | None = None
    unreadable_requests: int | None = None
    degraded_protections: int | None = None
    protection_delay_s: float | None = None
    last_mtm: datetime | None = None
    last_protection: datetime | None = None
    last_kill_switch_read: datetime | None = None
    paper_autonomy: bool | None = None


class MarketStatusExchangeOut(BaseModel):
    exchange: str
    ws_state: str
    last_event_at: datetime | None = None
    last_event_age_ms: int | None = None
    markets_monitored: int
    open_gaps: int
    reconnects: int | None = None
    shards_expected: int | None = None
    """T2.5g: how many collector shards this exchange declares
    (``shard_total`` in every ``hb:market:{exchange}:{i}of{N}`` hash), or
    ``None`` when no collector is reporting at all — the API never invents a
    topology it was not told about."""
    shards_reporting: int = 0
    """How many of them answered this read. Fewer than ``shards_expected``
    forces ``ws_state = "stale"``: a shard that is gone is its whole slice of
    the universe uncollected."""


class MarketStatusOut(BaseModel):
    exchanges: list[MarketStatusExchangeOut]
    markets_monitored_total: int
    updated_at: datetime
    exchanges_planned: list[str] = []
    """Venues catalogued with no collector deployed — ``exchanges.status =
    'planned'`` (DATABASE.md §28), by code, ordered.

    Additive, and deliberately *outside* ``exchanges``: those rows are the live
    feeds, reduced worst-of into one aggregate by the topbar, and a venue that
    cannot report is not a feed in trouble. Reporting Bybit there read
    ``2 exchanges · UNAVAILABLE`` while Binance was connected the whole time
    (T3.44b). Naming them here rather than dropping them is the other half: an
    exchange that simply vanished from the response would be a different lie.

    Defaults to ``[]`` so nothing that already parses this model has to change,
    and so the ``rt:system`` patch contract above — which carries one exchange
    row at a time and never this list — stays exactly as it was."""
