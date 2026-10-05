"""The §3.1 price contract of the wallet engine.

- **Slot without trades:** the state of the last event with slot ≤ the landing
  slot. A curve does not move without a trade. **Never** the next trade.
- **Slot with trades:** the worst quote among the previous slot's states and the
  states before and after *each* trade of the slot. The feed does not give the
  intra-slot order, so "before and after all trades" is read as "every state the
  slot went through" (the pre-trade state of the slot's first trade included,
  Astra must-fix 3) — at least as adverse as the design's reading, and
  order-free. Used only to resolve a fill, never to decide.
- **Curve:** ``hunter_indicators.meme.curve`` quotes, with the real-SOL ceiling
  **always** passed (``curve.py`` lets it be omitted; here it cannot be).
- **Pool:** its own constant product on (quote, base); the fee is the event's.
- **Migration:** a completed curve is not executable. A position then follows
  in the pool **only** if a decoded pool event exists at or before the landing;
  otherwise the landing is :data:`CENSORED`.

What we receive is floored to the lamport/atom and fees are ceiled (adverse rounding).
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Iterable, Sequence
from datetime import datetime
from decimal import ROUND_FLOOR, Decimal, localcontext
from typing import Final

from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.meme.curve import CurveReserves, quote_buy, quote_sell
from hunter_indicators.meme.wallets.tape import (
    LAMPORTS_PER_SOL,
    TOKEN_ATOMS_PER_TOKEN,
    Fill,
    Reserves,
    event_order,
)

__all__ = [
    "CENSORED",
    "Censored",
    "MintTape",
    "buy_atoms",
    "liquidation_lamports",
    "liquidation_or_none",
    "sell_lamports",
]

_SOL = Decimal(LAMPORTS_PER_SOL)
_TOK = Decimal(TOKEN_ATOMS_PER_TOKEN)
_BPS = Decimal(10_000)


class Censored:
    """The landing cannot be priced: migrated curve, no decoded pool event."""

    _instance: Censored | None = None

    def __new__(cls) -> Censored:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "CENSORED"


CENSORED: Final = Censored()


def _floor(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_FLOOR))


def _executable(state: Reserves) -> bool:
    return not (state.venue == "curve" and state.complete)


def _curve(state: Reserves) -> CurveReserves:
    with localcontext(CONTEXT):
        return CurveReserves(Decimal(state.sol_lamports) / _SOL, Decimal(state.token_atoms) / _TOK)


def buy_atoms(state: Reserves, budget_lamports: int, *, fee_bps: int) -> int | None:
    """Atoms a total spend of ``budget_lamports`` buys (fee on top); ``None`` if not executable."""
    if not _executable(state) or budget_lamports <= 0:
        return None
    with localcontext(CONTEXT):
        if state.venue == "curve":
            fee_pct = Decimal(fee_bps) / 100
            tokens = quote_buy(_curve(state), Decimal(budget_lamports) / _SOL, fee_pct).tokens
            return _floor(tokens * _TOK)
        quote_in = Decimal(budget_lamports) / (1 + Decimal(fee_bps) / _BPS)
        return _floor(
            Decimal(state.token_atoms) * quote_in / (Decimal(state.sol_lamports) + quote_in)
        )


def _ceil_bps(amount: int, bps: int) -> int:
    return -(-amount * bps // 10_000)


def sell_lamports(state: Reserves, atoms: int, *, fee_bps: int) -> int | None:
    """Net lamports a sale of ``atoms`` yields; ``None`` if not executable.

    Gross is floored and the fee is ceiled separately (``pumpswap/quote.py``);
    with only the event's *total* bps the three program-side ceilings become
    one, so this can be at most 2 lamports more generous than the program.
    """
    if not _executable(state):
        return None
    if atoms <= 0:
        return 0
    if state.venue == "curve":
        real = state.real_sol_lamports
        assert real is not None  # enforced by Reserves
        with localcontext(CONTEXT):
            quote = quote_sell(
                _curve(state),
                Decimal(atoms) / _TOK,
                Decimal(0),
                real_sol_reserves=Decimal(real) / _SOL,
            )
            gross = _floor(quote.curve_proceeds_sol * _SOL)
    else:
        gross = state.sol_lamports * atoms // (state.token_atoms + atoms)
    return gross - _ceil_bps(gross, fee_bps)


def _pre_state(f: Fill) -> Reserves | None:
    """The reserves just before ``f`` (its own trade undone); ``None`` if impossible."""
    sign = 1 if f.side == "buy" else -1
    post = f.reserves
    sol = post.sol_lamports - sign * f.sol_lamports
    tokens = post.token_atoms + sign * f.token_atoms
    real = (
        None if post.real_sol_lamports is None else post.real_sol_lamports - sign * f.sol_lamports
    )
    if sol <= 0 or tokens <= 0 or (real is not None and real < 0):
        return None
    return Reserves(post.venue, sol, tokens, real, complete=False)


class MintTape:
    """One mint's events in slot order, with the lookups the contract needs."""

    def __init__(self, fills: Iterable[Fill]) -> None:
        self.fills: tuple[Fill, ...] = tuple(sorted(fills, key=event_order))
        self._slots: list[int] = sorted({f.slot for f in self.fills})
        self._by_slot: dict[int, list[Fill]] = {}
        for f in self.fills:
            self._by_slot.setdefault(f.slot, []).append(f)
        self._fill_slots = [f.slot for f in self.fills]
        self._valid: dict[datetime, tuple[Fill, ...]] = {}

    def _slot_at_or_before(self, slot: int) -> int | None:
        i = bisect_right(self._slots, slot)
        return self._slots[i - 1] if i else None

    def _slot_before(self, slot: int) -> int | None:
        i = bisect_left(self._slots, slot)
        return self._slots[i - 1] if i else None

    def landing_states(self, slot: int) -> tuple[tuple[Reserves, int], ...]:
        """``(state, fee_bps)`` a landing at ``slot`` may meet (§3.1).

        With trades in the slot: the previous slot's post-states, every post-state
        of the slot **and** every pre-state of the slot (the state before its first
        trade is one of them, whatever the unknown intra-slot order). Without
        trades: the post-states of the last slot ≤ ``slot``.
        """
        if slot in self._by_slot:
            before = self._slot_before(slot)
            prior = self._by_slot[before] if before is not None else []
            here = self._by_slot[slot]
            pre = [(p, f.fee_bps) for f in here if (p := _pre_state(f)) is not None]
            return (*((f.reserves, f.fee_bps) for f in (*prior, *here)), *pre)
        last = self._slot_at_or_before(slot)
        if last is None:
            return ()
        return tuple((f.reserves, f.fee_bps) for f in self._by_slot[last])

    def observed_through(self, slot: int) -> tuple[Fill, ...]:
        """Every event with slot ≤ ``slot`` (what a watcher had seen by then)."""
        return self.fills[: bisect_right(self._fill_slots, slot)]

    @staticmethod
    def _priceable(
        states: Sequence[tuple[Reserves, int]],
    ) -> tuple[tuple[Reserves, int], ...] | Censored | None:
        if not states:
            return None
        if any(r.venue == "pool" for r, _ in states):
            states = [(r, b) for r, b in states if _executable(r)]
        if any(not _executable(r) for r, _ in states):
            return CENSORED
        return tuple(states)

    def landing_sell(self, slot: int, atoms: int) -> int | Censored | None:
        """Worst net lamports for selling ``atoms`` at ``slot``; ``None`` = no state at all."""
        states = self._priceable(self.landing_states(slot))
        if states is None or isinstance(states, Censored):
            return states
        return min(sell_lamports(r, atoms, fee_bps=b) or 0 for r, b in states)

    def landing_buy(self, slot: int, budget_lamports: int) -> int | Censored | None:
        """Worst atoms for spending ``budget_lamports`` at ``slot``; ``None`` = no state at all."""
        states = self._priceable(self.landing_states(slot))
        if states is None or isinstance(states, Censored):
            return states
        return min(buy_atoms(r, budget_lamports, fee_bps=b) or 0 for r, b in states)

    def events_before(self, instant: datetime) -> tuple[Fill, ...]:
        """Events mined **and** received strictly before ``instant``."""
        return tuple(f for f in self.fills if f.block_time < instant and f.received_at < instant)

    def valid_states_at(self, instant: datetime) -> tuple[Fill, ...]:
        """The events of the last slot among those mined and received before ``instant``.

        Memoized per instant: the window boundaries are shared by every holder of
        the mint, so the scan runs once per boundary, not once per holder.
        """
        cached = self._valid.get(instant)
        if cached is None:
            seen = self.events_before(instant)
            cached = tuple(f for f in seen if f.slot == seen[-1].slot) if seen else ()
            self._valid[instant] = cached
        return cached


def liquidation_or_none(tape: MintTape, instant: datetime, atoms: int) -> int | None:
    """Value of selling **all** ``atoms`` against the valid state at ``instant``, or
    ``None`` when there is no valid state (no event before it, or a migrated curve
    without a pool event). The worst of the last slot's states is used."""
    if atoms <= 0:
        return 0
    events = tape.valid_states_at(instant)
    if not events:
        return None
    values = [sell_lamports(e.reserves, atoms, fee_bps=e.fee_bps) for e in events]
    if any(v is None for v in values):
        return None
    return min(v for v in values if v is not None)


def liquidation_lamports(tape: MintTape, instant: datetime, atoms: int) -> int:
    """:func:`liquidation_or_none` with **0** for "no valid state" (design §1: never
    the last mark). At the window start the caller must also flag the episode
    incomplete — 0 there would turn a dead bag's later sale into pure gain."""
    value = liquidation_or_none(tape, instant, atoms)
    return 0 if value is None else value
