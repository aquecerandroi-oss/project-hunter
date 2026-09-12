"""Normalized pump.fun domain models (``docs/plans/T4-MEME-RADAR.md`` §1, §5).

Mirrors the discipline of ``hunter_core.domain.market``'s ``Normalized*``
models (``docs/EXCHANGE_INTEGRATION.md`` §2) without depending on that
module: pump.fun is not an ``ExchangeAdapter`` (no orderbook, no symbol —
see T4-MEME-RADAR.md §0) so these types live in this package on purpose.
Every model is ``frozen=True, extra="forbid"``; every price/reserve is
``Decimal``; every timestamp is UTC-aware.

Units: reserves are always stored in **human units** (SOL, tokens with 6
decimals) regardless of the wire format the producer used — PumpPortal's WS
sends them already as floats in human units, ``frontend-api-v3.pump.fun``
and the Solana RPC send raw integer lamports/token-subunits. Converting once
at the normalize boundary (``normalize.py``) means every consumer of these
models reasons in one unit system, never lamports in one field and SOL in
the next.

``NormalizedMemeTrade`` is defined now with **no producer** in T4.1:
PumpPortal's ``subscribeTokenTrade``/``subscribeAccountTrade`` are paid
(0.01 SOL / 10,000 events, requires a funded API key — T4.0 §2, Astra's
correction in ``astra-review-t40-pumpfun.md``) and Everton has not decided
whether to pay for them. The model exists so a future trade producer (WS
paid channel, or an RPC/Geyser backfill) has a normalized shape to fill
without any caller-visible change.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from hunter_core.domain.types import ensure_utc, utcnow


class NormalizedModel(BaseModel):
    """Shared config for every model in this module (same as ``hunter_core.domain.market``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class _ReceivedAtMixin(NormalizedModel):
    """Local receive time — the only timestamp PumpPortal's WS payloads carry
    at all (see ``ws.py`` module docstring: no block time in the frame)."""

    received_at: datetime = Field(default_factory=utcnow)
    observed_at: datetime = Field(default_factory=utcnow)

    @field_validator("received_at", "observed_at", mode="after")
    @classmethod
    def _received_at_is_utc(cls, v: datetime) -> datetime:
        return ensure_utc(v)


ReceivedAtMixin = _ReceivedAtMixin
"""The public name of the mixin, for the T4.2c models in ``board_models.py``."""


class NormalizedMemeTokenCreated(_ReceivedAtMixin):
    """A pump.fun ``create`` instruction, from PumpPortal's ``subscribeNewToken``.

    ``created_at`` is **not** an on-chain block time: PumpPortal's real-time
    frame carries no timestamp field at all (confirmed against a live
    capture, ``tests/fixtures/pumpfun/pumpportal_ws_capture_raw.jsonl`` —
    every ``create``/``migrate`` message lacks one). It is set equal to
    ``received_at`` and documented here instead of being silently treated as
    exchange time (``EXCHANGE_INTEGRATION.md`` §2's ``ts``/``received_at``
    split assumes the source *has* an event time; pump.fun's WS source does
    not). The true block time is only available via an RPC/Geyser backfill
    keyed by ``signature``, out of scope for T4.1.
    """

    kind: Literal["meme_token_created"] = "meme_token_created"
    mint: str
    name: str
    symbol: str
    uri: str
    creator: str
    created_at: datetime
    bonding_curve: str
    initial_virtual_sol_reserves: Decimal
    initial_virtual_token_reserves: Decimal
    signature: str
    """Solana tx signature — the dedupe key together with ``mint`` (ws.py)."""
    pool: str = "pump"
    """Always ``"pump"`` for this model — PumpPortal's ``subscribeNewToken``
    also streams other launchpads (observed live: ``pool="bonk"`` for
    letsbonk.fun) under the same method; ``normalize.py`` refuses to build
    this model for any other pool instead of mislabelling a foreign program
    as pump.fun."""
    source: str = "pumpportal_ws"
    mayhem_enabled: bool | None = None
    mayhem_mode: str | None = None

    @field_validator("created_at", mode="after")
    @classmethod
    def _created_at_is_utc(cls, v: datetime) -> datetime:
        return ensure_utc(v)


class NormalizedMemeMigration(_ReceivedAtMixin):
    """A pump.fun bonding curve migrating to PumpSwap (``subscribeMigration``).

    ``migrated_at`` has the same caveat as ``NormalizedMemeTokenCreated.created_at``
    — PumpPortal's migration frame carries no block time either.
    """

    kind: Literal["meme_migration"] = "meme_migration"
    mint: str
    pool: str
    """Destination pool label as PumpPortal reports it (``"pump-amm"`` observed
    live for PumpSwap — T4-MEME-RADAR.md §3 confirms migration targets
    PumpSwap today, not Raydium)."""
    migrated_at: datetime
    signature: str
    source: str = "pumpportal_ws"

    @field_validator("migrated_at", mode="after")
    @classmethod
    def _migrated_at_is_utc(cls, v: datetime) -> datetime:
        return ensure_utc(v)


class NormalizedCurveState(_ReceivedAtMixin):
    """A point-in-time read of one bonding curve's reserves.

    ``source`` distinguishes the three producers this package has
    (``"pumpfun_rest"`` — ``rest.py``; ``"solana_rpc"`` — ``rpc.py``; a WS
    ``create`` event's own initial reserves are carried on
    ``NormalizedMemeTokenCreated`` instead, since PumpPortal never re-sends a
    curve snapshot for an existing token over the free channels) so a
    consumer can weigh RPC/on-chain truth over the best-effort REST mirror
    (T4-MEME-RADAR.md §2: never a single source of truth for anything the
    scanner decides on).
    """

    kind: Literal["meme_curve_state"] = "meme_curve_state"
    mint: str
    virtual_sol_reserves: Decimal
    virtual_token_reserves: Decimal
    real_sol_reserves: Decimal
    real_token_reserves: Decimal
    total_supply: Decimal
    complete: bool
    market_cap_sol: Decimal
    """Theoretical market cap in SOL — marginal price × total supply
    (``curve.py``), never a realizable sell-everything value
    (T4-MEME-RADAR.md §4)."""
    source: str
    mayhem_enabled: bool | None = None
    mayhem_state: str | None = None
    mayhem_mode: str | None = None
    slot: int | None = None
    commitment: str | None = None

    @field_validator("observed_at", mode="after")
    @classmethod
    def _observed_at_is_utc(cls, v: datetime) -> datetime:
        return ensure_utc(v)


class NormalizedMemeTrade(_ReceivedAtMixin):
    """A single buy/sell against a bonding curve. **No producer in T4.1** —
    PumpPortal's per-token/account trade channels are paid (see module
    docstring); this model exists only so a future producer has a target
    shape. Every field mirrors ``meme_trades`` (T4-MEME-RADAR.md §5)."""

    kind: Literal["meme_trade"] = "meme_trade"
    mint: str
    signature: str
    side: Literal["buy", "sell"]
    sol_amount: Decimal
    token_amount: Decimal
    price: Decimal
    """``sol_amount / token_amount`` at event time — never recalculated later."""
    wallet: str
    ts: datetime
    source: str

    @field_validator("ts", mode="after")
    @classmethod
    def _ts_is_utc(cls, v: datetime) -> datetime:
        return ensure_utc(v)


class NormalizedMayhemOverview(_ReceivedAtMixin):
    """Opaque upstream overview, explicitly labelled until its schema is stable."""

    source: str = "pumpfun_rest"
    metadata: dict[str, Any]


class NormalizedSolPrice(_ReceivedAtMixin):
    """``GET /sol-price`` of ``frontend-api-v3.pump.fun`` — the quote pump.fun's
    own site prices ``usd_market_cap`` with (``docs/PUMPFUN.md`` §1.1 route 4).

    ``as_of`` is the upstream ``asOfTimestamp`` (epoch ms), ``stale`` is the
    upstream's own word for it; ``observed_at`` is when we read it. A consumer
    stores all three next to any USD figure it derives, because a dollar number
    without the quote and its instant is a number nobody can check.
    """

    source: str = "pumpfun_rest:/sol-price"
    price_usd: Decimal
    as_of: datetime
    stale: bool

    @field_validator("as_of", mode="after")
    @classmethod
    def _as_of_is_utc(cls, v: datetime) -> datetime:
        return ensure_utc(v)

    @field_validator("price_usd", mode="after")
    @classmethod
    def _price_is_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("price_usd must be positive")
        return v


__all__ = [
    "NormalizedCurveState",
    "NormalizedMemeMigration",
    "NormalizedMemeTokenCreated",
    "NormalizedMemeTrade",
    "NormalizedModel",
    "NormalizedSolPrice",
    "ReceivedAtMixin",
]
