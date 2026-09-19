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
    """The **derived** ``["bonding-curve", mint]`` PDA (``normalize.py``), never
    the frame's raw ``bondingCurveKey`` blindly — a Mayhem ``create`` frame
    carries the program's shared sol-vault there instead (R36,
    ``docs/PUMPFUN.md`` §9), and this field feeds ``meme_tokens.bonding_curve``,
    which the radar's ``reconcile_once`` used to read as an account address."""
    bonding_curve_raw: str | None = None
    """The frame's own ``bondingCurveKey``, kept only when it disagrees with
    :attr:`bonding_curve` — ``None`` means the frame already carried the
    correct PDA. Audit trail, never read to derive an address (T4.39)."""
    initial_virtual_sol_reserves: Decimal
    initial_virtual_token_reserves: Decimal
    creator_initial_tokens: Decimal | None = None
    """T4.45 - the creator's own buy in the ``create`` transaction, in **tokens**
    (the frame's ``initialBuy``), the same unit as
    ``meme_tokens.initial_real_token_reserves``. Verified against the live
    capture: ``1 073 000 000 - initialBuy == vTokensInBondingCurve`` to the last
    digit. ``0`` means *measured*: the dev bought nothing. ``None`` means the
    frame did not carry it - never a zero, because "bought nothing" and "we did
    not see" lead to opposite decisions on check 10."""
    creator_initial_sol: Decimal | None = None
    """What that buy cost, in SOL (``solAmount``). Kept beside the tokens for
    audit; the admission compares balances in tokens."""
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
    uri: str | None = None
    """``metadata_uri`` — off-chain JSON pointer (T4.26): the REST read fills
    this when the WS ``create`` event was missed, never overwriting a value
    already known (``meme_tokens.uri`` is write-once)."""
    twitter: str | None = None
    website: str | None = None
    telegram: str | None = None
    description: str | None = None
    """Truncated by the caller (``normalize.py``) before this model is built,
    never here — a model is a shape, not a policy."""
    twitter_kind: str | None = None
    """``profile`` | ``post`` | ``community`` | ``other`` — ``None`` exactly
    when ``twitter`` is (``hunter_exchanges.pumpfun.social.classify_twitter_url``)."""
    twitter_post_id: int | None = None
    twitter_post_at: datetime | None = None

    @field_validator("observed_at", mode="after")
    @classmethod
    def _observed_at_is_utc(cls, v: datetime) -> datetime:
        return ensure_utc(v)

    @field_validator("twitter_post_at", mode="after")
    @classmethod
    def _twitter_post_at_is_utc(cls, v: datetime | None) -> datetime | None:
        return None if v is None else ensure_utc(v)


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


class NormalizedCurveTrade(_ReceivedAtMixin):
    """A bonding-curve fill as the Solana RPC WebSocket reports it (T4.52b-1,
    ``rpc_ws.py`` + ``trade_event.py``'s ``normalized_curve_trade``): the exact
    on-chain ``TradeEvent`` the pump program emits, dated by the subscription
    envelope's ``slot``/``signature`` — never PumpPortal's paid trade channel
    (out of scope, see :class:`NormalizedMemeTrade`'s docstring) and never a
    REST poll's after-the-fact reconstruction. This is the shape T4.52b-2's
    in-memory event state is built from.
    """

    kind: Literal["meme_curve_trade"] = "meme_curve_trade"
    mint: str
    slot: int
    signature: str
    trader: str
    """``TradeEvent.user`` — the wallet that submitted the trade instruction."""
    side: Literal["buy", "sell"]
    lamports: Decimal
    """``TradeEvent.sol_amount`` untouched, in raw lamports — an audit trail
    against the event bytes, unlike every reserve field below, which *is*
    converted to human units at this boundary like the rest of this module."""
    token_amount: Decimal | None = None
    """``TradeEvent.token_amount`` untouched, in raw subunits (T4.66: what the
    crowd ledger sums per wallet — a ratio, so the unit never matters);
    ``None`` from a source that lacks the field."""
    virtual_sol_reserves: Decimal
    virtual_token_reserves: Decimal
    real_sol_reserves: Decimal
    real_token_reserves: Decimal
    """Post-trade reserves — the state the curve is in immediately after this
    fill, not before it."""
    creator: str
    mayhem: bool
    block_time: datetime | None
    """``TradeEvent.timestamp`` (the program's own clock read at emit time),
    converted to a UTC datetime — never ``None`` in practice since every
    ``TradeEvent`` carries it, but optional here because a caller building
    this model from a source that lacks the field (none exists yet) should
    not have to invent one."""
    source: str = "solana_rpc_ws"

    @field_validator("block_time", mode="after")
    @classmethod
    def _block_time_is_utc(cls, v: datetime | None) -> datetime | None:
        return None if v is None else ensure_utc(v)


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
    "NormalizedCurveTrade",
    "NormalizedMemeMigration",
    "NormalizedMemeTokenCreated",
    "NormalizedMemeTrade",
    "NormalizedModel",
    "NormalizedSolPrice",
    "ReceivedAtMixin",
]
