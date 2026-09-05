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


class MarketStatusExchangeOut(BaseModel):
    exchange: str
    ws_state: str
    last_event_at: datetime | None = None
    last_event_age_ms: int | None = None
    markets_monitored: int
    open_gaps: int
    reconnects: int | None = None


class MarketStatusOut(BaseModel):
    exchanges: list[MarketStatusExchangeOut]
    markets_monitored_total: int
    updated_at: datetime
