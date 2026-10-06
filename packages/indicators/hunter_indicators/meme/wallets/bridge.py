"""The pure bridge from the adapter's swap record to the engine's :class:`~.tape.Fill`.

``hunter_indicators`` does not depend on ``hunter_exchanges`` (``pyproject.toml``), so the
input is structural: :class:`SwapLike` names the fields of
``hunter_exchanges.pumpfun.swap_record.SwapRecord`` this bridge reads, and the real record
satisfies it as is. Same money semantics on both sides: the SOL leg gross of the declared
fees, ``int`` lamports/atoms, reserves AFTER the trade, UTC times.

What the record cannot say, the caller must — never guessed here:

- **A pool's mints.** A PumpSwap event names the pool, not its mints, so a pool record has
  ``quote_is_sol = None``. Only a :class:`PoolMints` resolved by the caller (pool account or
  the swap instruction's accounts) lets it in, and only when the **quote** is WSOL. Pools
  whose base is WSOL exist (3 of 13 swaps in the wave-1a fixtures): their "SOL leg" is atoms
  of another token and is refused as ``sol_is_base``.
- **The curve's completion flag** (migration, §3.1), absent from the record: without it a
  completed curve would stay executable, so a curve record needs ``curve_complete``. It must
  be the flag **as of this event** (the state the trade left), never today's flag applied
  back to older trades — that would be look-ahead; the bridge only sees the boolean, so
  this guarantee is the caller's.

A record whose own pre-trade state is impossible (the effective quote before it would not
be positive) is refused as ``pre_state_impossible``: the trade could not have priced on it.

A refusal of the DATA is a value with a name (:class:`BridgeRefusal`), never an exception
and never a fill. A caller bug (a :class:`PoolMints` for another pool, or for a curve
record) raises ``ValueError``. Refused events are holes in the mint's tape: the collector
must account for them as coverage gaps (§2), not drop them silently. Pure: no IO, no clock.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal, Protocol

from hunter_indicators.meme.wallets.pricing import pre_trade_state
from hunter_indicators.meme.wallets.tape import Fill, Reserves, Side, Venue

__all__ = ["WSOL_MINT", "BridgeRefusal", "PoolMints", "RefusalReason", "SwapLike", "fill_from_swap"]

WSOL_MINT: Final = "So11111111111111111111111111111111111111112"

RefusalReason = Literal[
    "pool_quote_unresolved",
    "non_sol_quote",
    "sol_is_base",
    "virtual_quote_missing",
    "non_positive_effective_quote",
    "curve_completion_unknown",
    "curve_mint_missing",
    "pre_state_impossible",
    "invalid_values",
]


class SwapLike(Protocol):
    """The ``SwapRecord`` fields the bridge reads (read-only)."""

    @property
    def signature(self) -> str: ...
    @property
    def slot(self) -> int: ...
    @property
    def program(self) -> str: ...
    @property
    def event_ordinal(self) -> int: ...
    @property
    def block_time(self) -> datetime: ...
    @property
    def received_at(self) -> datetime: ...
    @property
    def venue(self) -> Venue: ...
    @property
    def side(self) -> Side: ...
    @property
    def mint(self) -> str | None: ...
    @property
    def pool(self) -> str | None: ...
    @property
    def wallet(self) -> str: ...
    @property
    def sol_lamports(self) -> int: ...
    @property
    def token_atoms(self) -> int: ...
    @property
    def fee_lamports(self) -> int: ...
    @property
    def fee_bps(self) -> int: ...
    @property
    def lp_fee_lamports(self) -> int: ...
    @property
    def sol_reserves(self) -> int: ...
    @property
    def token_reserves(self) -> int: ...
    @property
    def real_sol_reserves(self) -> int | None: ...
    @property
    def quote_is_sol(self) -> bool | None: ...
    @property
    def virtual_quote_reserves(self) -> int | None: ...


@dataclass(frozen=True, slots=True)
class PoolMints:
    """A pool's base and quote mints, resolved by the caller."""

    pool: str
    base_mint: str
    quote_mint: str


@dataclass(frozen=True, slots=True)
class BridgeRefusal:
    """A record that does not become a fill, and why."""

    reason: RefusalReason
    identity: tuple[str, str, int]
    slot: int
    detail: str


def _refuse(record: SwapLike, reason: RefusalReason, detail: str) -> BridgeRefusal:
    identity = (record.signature, record.program, record.event_ordinal)
    return BridgeRefusal(reason, identity, record.slot, detail)


def _pool_state(record: SwapLike, pool: PoolMints | None) -> tuple[str, Reserves] | BridgeRefusal:
    if pool is None:
        return _refuse(record, "pool_quote_unresolved", f"pool {record.pool}: mints not resolved")
    if pool.quote_mint != WSOL_MINT or record.quote_is_sol is False:
        reason: RefusalReason = "sol_is_base" if pool.base_mint == WSOL_MINT else "non_sol_quote"
        return _refuse(record, reason, f"pool {pool.pool}: quote {pool.quote_mint}")
    virtual = record.virtual_quote_reserves
    if virtual is None:
        return _refuse(record, "virtual_quote_missing", f"pool {pool.pool}")
    if record.sol_reserves + virtual <= 0:
        detail = f"real {record.sol_reserves} + virtual {virtual} <= 0"
        return _refuse(record, "non_positive_effective_quote", detail)
    state = Reserves(
        "pool", record.sol_reserves, record.token_reserves, None, virtual_quote_lamports=virtual
    )
    return pool.base_mint, state


def _curve_state(
    record: SwapLike, curve_complete: bool | None
) -> tuple[str, Reserves] | BridgeRefusal:
    if record.quote_is_sol is not True:
        return _refuse(record, "non_sol_quote", f"curve quote_is_sol={record.quote_is_sol}")
    if record.mint is None:
        return _refuse(record, "curve_mint_missing", "curve record without its mint")
    if curve_complete is None:
        return _refuse(record, "curve_completion_unknown", f"mint {record.mint}")
    state = Reserves(
        "curve",
        record.sol_reserves,
        record.token_reserves,
        record.real_sol_reserves,
        complete=curve_complete,
    )
    return record.mint, state


def fill_from_swap(
    record: SwapLike,
    *,
    pool: PoolMints | None = None,
    curve_complete: bool | None = None,
) -> Fill | BridgeRefusal:
    """The engine's fill of ``record``, or the named reason it is not one."""
    if pool is not None and (record.venue == "curve" or pool.pool != record.pool):
        raise ValueError(f"pool lookup {pool.pool} is not the {record.venue} record's pool")
    try:
        resolved = (
            _pool_state(record, pool)
            if record.venue == "pool"
            else _curve_state(record, curve_complete)
        )
        if isinstance(resolved, BridgeRefusal):
            return resolved
        mint, reserves = resolved
        fill = Fill(
            signature=record.signature,
            program=record.program,
            event_ordinal=record.event_ordinal,
            slot=record.slot,
            block_time=record.block_time,
            received_at=record.received_at,
            wallet=record.wallet,
            mint=mint,
            venue=record.venue,
            side=record.side,
            sol_lamports=record.sol_lamports,
            token_atoms=record.token_atoms,
            fee_lamports=record.fee_lamports,
            fee_bps=record.fee_bps,
            reserves=reserves,
            lp_fee_lamports=record.lp_fee_lamports,
        )
    except ValueError as exc:  # Reserves/Fill validation: zero reserves, no real SOL, ...
        return _refuse(record, "invalid_values", str(exc))
    if pre_trade_state(fill) is None:  # the trade could not have priced on its own pre-state
        return _refuse(record, "pre_state_impossible", f"undoing slot {record.slot} trade")
    return fill
