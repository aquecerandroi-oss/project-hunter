"""One normalised swap, whichever venue it came from (wave 1a of H-030).

:class:`SwapRecord` is the shape the pump bonding-curve ``TradeEvent``, the PumpSwap ``BuyEvent``
and the PumpSwap ``SellEvent`` are all turned into by :func:`swap_record_from_event`; the log
reader (:mod:`hunter_exchanges.pumpfun.program_logs`) supplies the envelope (signature, slot,
program, ordinal, ``received_at``). Pure: no IO, no clock.

**The SOL leg is always gross of the fees the event declares**, so a buy costs ``sol_lamports +
fee_lamports`` and a sell nets ``sol_lamports - fee_lamports``. All values are ``int`` lamports /
base units, never ``float``.

* curve ``TradeEvent``: ``sol_amount``; fees = ``fee + creator_fee + cashback``; reserves are the
  curve's, reported by the event **after** the trade.
* PumpSwap ``BuyEvent``: the net quote that priced the base (:attr:`BuyEvent.net_quote_in`); fees =
  LP + protocol + creator + cashback.
* PumpSwap ``SellEvent``: ``quote_amount_out``; same fees (cashback is deducted on sells: 2 of 2 real
  events, lamport-exact).

**Reserves are always the state AFTER the trade** (what the tape's ``Fill`` carries). A PumpSwap
event reports the pool **before** its trade, so the record moves it by the exact vault flow: a buy
adds ``quote_amount_in_with_lp_fee`` and removes ``base_amount_out``; a sell removes ``quote_amount_out
- lp_fee`` and adds ``base_amount_in`` (the LP fee stays in the pool). ``reserves_source`` says which
of the two it is. The derivation matches the NEXT trade of the same pool, which reports exactly
that state as its own "before" (an ad-hoc sweep of 61 consecutive real pairs, buy and sell, base and
quote, found no exception; three pairs are pinned by fixtures in the tests).

An event whose own money does not close, or that is quoted in something other than SOL, raises
:class:`Refused` instead of becoming a record.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, NoReturn

from hunter_exchanges.pumpfun.decode import NATIVE_SOL_QUOTE_MINT, PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.trade_event_codec import (
    TRADE_EVENT_DISCRIMINATOR,
    TradeEvent,
    decode_trade_event,
)
from hunter_exchanges.pumpswap.buy_event import (
    BUY_EVENT_DISCRIMINATOR,
    BuyEvent,
    decode_buy_event,
)
from hunter_exchanges.pumpswap.decode import PUMPSWAP_PROGRAM_ID
from hunter_exchanges.pumpswap.sell_event import (
    SELL_EVENT_DISCRIMINATOR,
    SellEvent,
    decode_sell_event,
)

__all__ = ["Refused", "SwapRecord", "swap_record_from_event"]

Side = Literal["buy", "sell"]
Venue = Literal["curve", "pool"]
ReservesSource = Literal["event_after", "derived_after"]


@dataclass(frozen=True, slots=True)
class SwapRecord:
    signature: str
    slot: int
    program: str
    event_ordinal: int
    block_time: datetime
    """The event's own unix timestamp (the chain's clock), UTC."""
    received_at: datetime
    """When OUR collector had it, UTC (passed in by the caller)."""
    venue: Venue
    side: Side
    market: str
    """What the event itself names: the mint (curve) or the pool address (PumpSwap)."""
    mint: str | None
    pool: str | None
    wallet: str
    sol_lamports: int
    """The SOL leg gross of the declared fees (see the module docstring)."""
    token_atoms: int
    fee_lamports: int
    fee_bps: int
    """Sum of the declared fee rates in basis points (the rate a copy of this trade would pay)."""
    lp_fee_lamports: int
    """The part of ``fee_lamports`` that stays in a pool (PumpSwap LP fee); ``0`` on the curve."""
    sol_reserves: int
    """Quote reserve AFTER the trade (see the module docstring)."""
    token_reserves: int
    real_sol_reserves: int | None
    """The curve's real SOL (the ceiling of a sale); ``None`` for a pool (its quote reserve is real)."""
    reserves_source: ReservesSource
    layout: str
    ix_name: str | None
    quote_is_sol: bool | None
    """``True`` for a curve trade checked against its ``quote_mint``; ``None`` for a pool event,
    which carries no quote mint (the pool account does: resolve it with the pool)."""
    virtual_quote_reserves: int | None = None
    """PumpSwap only: the pool's virtual quote reserve at the event (``can_boost`` pools). A pool trade
    is priced against ``sol_reserves + virtual_quote_reserves``, not ``sol_reserves`` alone (the real
    reserve alone misprices a boosted pool: 32.47 M instead of 38.39 M lamports on a real buy, -15 %;
    the sum reproduces the chain to the lamport on ``buy`` and within one lamport on
    ``buy_exact_quote_in``).
    ``None`` on a curve record (its reserves are already virtual)."""

    @property
    def identity(self) -> tuple[str, str, int]:
        return (self.signature, self.program, self.event_ordinal)


class Refused(Exception):
    """An event that is not turned into a record: it did not decode (``undecodable``), decoded but its
    own money does not close (``unconserved``) or is not quoted in SOL (``non_sol_quote``)."""

    kind: Literal["undecodable", "unconserved", "non_sol_quote"]
    detail: str

    def __init__(self, kind: Literal["undecodable", "unconserved", "non_sol_quote"], detail: str):
        super().__init__(detail)
        self.kind = kind
        self.detail = detail


def _block_time(timestamp: int) -> datetime:
    try:
        return datetime.fromtimestamp(timestamp, tz=UTC) if timestamp > 0 else _bad_time()
    except (OverflowError, OSError, ValueError):
        return _bad_time()


def _bad_time() -> NoReturn:
    raise Refused("undecodable", "event timestamp out of range")


def _curve(e: TradeEvent, common: dict[str, Any]) -> SwapRecord:
    # The mint decides, never an equality of amounts: a USDC-quoted trade can read ``quote_amount ==
    # sol_amount`` and would otherwise enter as lamports. Every real curve event read carries the
    # all-zero native mint; anything else is counted apart, not guessed.
    if e.quote_mint != NATIVE_SOL_QUOTE_MINT:
        raise Refused("non_sol_quote", f"quote_mint {e.quote_mint}")
    return SwapRecord(
        **common,
        block_time=_block_time(e.timestamp),
        venue="curve",
        side="buy" if e.is_buy else "sell",
        market=e.mint,
        mint=e.mint,
        pool=None,
        wallet=e.user,
        sol_lamports=e.sol_amount,
        token_atoms=e.token_amount,
        fee_lamports=e.fee + e.creator_fee + e.cashback,
        fee_bps=e.fee_basis_points + e.creator_fee_basis_points + e.cashback_fee_basis_points,
        lp_fee_lamports=0,
        sol_reserves=e.virtual_sol_reserves,
        token_reserves=e.virtual_token_reserves,
        real_sol_reserves=e.real_sol_reserves,
        reserves_source="event_after",
        layout=e.layout,
        ix_name=e.ix_name,
        quote_is_sol=True,
    )


def _pool_buy(e: BuyEvent, common: dict[str, Any]) -> SwapRecord:
    if not e.money_conserves:
        raise Refused(
            "unconserved",
            f"BuyEvent quote fields ({e.quote_amount_in}, {e.user_quote_amount_in}) are not "
            f"(net {e.net_quote_in}, paid {e.total_quote_paid})",
        )
    token_after = e.pool_base_token_reserves - e.base_amount_out
    if token_after < 0:
        raise Refused(
            "unconserved",
            f"BuyEvent takes {e.base_amount_out} from a pool of {e.pool_base_token_reserves}",
        )
    return SwapRecord(
        **common,
        block_time=_block_time(e.timestamp),
        venue="pool",
        side="buy",
        market=e.pool,
        mint=None,
        pool=e.pool,
        wallet=e.user,
        sol_lamports=e.net_quote_in,
        token_atoms=e.base_amount_out,
        fee_lamports=e.fee_total,
        fee_bps=(
            e.lp_fee_basis_points
            + e.protocol_fee_basis_points
            + e.coin_creator_fee_basis_points
            + e.cashback_fee_basis_points
        ),
        lp_fee_lamports=e.lp_fee,
        sol_reserves=e.pool_quote_token_reserves + e.quote_amount_in_with_lp_fee,
        token_reserves=token_after,
        real_sol_reserves=None,
        reserves_source="derived_after",
        virtual_quote_reserves=e.virtual_quote_reserves,
        layout=e.layout,
        ix_name=e.ix_name,
        quote_is_sol=None,
    )


def _pool_sell(e: SellEvent, common: dict[str, Any]) -> SwapRecord:
    fee = e.lp_fee + e.protocol_fee + e.coin_creator_fee + e.cashback
    if e.quote_amount_out - fee != e.user_quote_amount_out:
        raise Refused(
            "unconserved",
            f"SellEvent gross {e.quote_amount_out} - fees {fee} != net {e.user_quote_amount_out}",
        )
    sol_after = e.pool_quote_token_reserves - (e.quote_amount_out - e.lp_fee)
    if sol_after < 0:
        raise Refused(
            "unconserved",
            f"SellEvent pays {e.quote_amount_out} from a pool of {e.pool_quote_token_reserves}",
        )
    return SwapRecord(
        **common,
        block_time=_block_time(e.timestamp),
        venue="pool",
        side="sell",
        market=e.pool,
        mint=None,
        pool=e.pool,
        wallet=e.user,
        sol_lamports=e.quote_amount_out,
        token_atoms=e.base_amount_in,
        fee_lamports=fee,
        fee_bps=(
            e.lp_fee_basis_points
            + e.protocol_fee_basis_points
            + e.coin_creator_fee_basis_points
            + e.cashback_fee_basis_points
        ),
        lp_fee_lamports=e.lp_fee,
        sol_reserves=sol_after,
        token_reserves=e.pool_base_token_reserves + e.base_amount_in,
        real_sol_reserves=None,
        reserves_source="derived_after",
        virtual_quote_reserves=e.virtual_quote_reserves,
        layout=e.layout,
        ix_name=None,
        quote_is_sol=None,
    )


def swap_record_from_event(
    program: str, payload: bytes, common: dict[str, Any]
) -> SwapRecord | None:
    """The record of a swap event; ``None`` for an event this reader does not turn into one."""
    disc = payload[:8]
    try:
        if program == PUMP_PROGRAM_ID and disc == TRADE_EVENT_DISCRIMINATOR:
            return _curve(decode_trade_event(payload), common)
        if program == PUMPSWAP_PROGRAM_ID and disc == BUY_EVENT_DISCRIMINATOR:
            return _pool_buy(decode_buy_event(payload), common)
        if program == PUMPSWAP_PROGRAM_ID and disc == SELL_EVENT_DISCRIMINATOR:
            return _pool_sell(decode_sell_event(payload), common)
    except Refused:
        raise
    except (ValueError, struct.error) as exc:
        raise Refused("undecodable", str(exc)) from exc
    return None
