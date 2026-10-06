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
- **Pool:** its own constant product on (real + virtual quote, base) — the signed
  ``virtual_quote_reserves`` of PumpSwap, KB-0184 item 3 — with a sale never paying
  more than the real quote in the vault; the fee is the event's. The state before a
  trade is rebuilt from the exact vault flow, LP fee included (:func:`pre_trade_state`).
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
from functools import lru_cache
from typing import Final

from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.meme.curve import CurveReserves, quote_buy, sell_proceeds
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
    "pre_trade_state",
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


@lru_cache(maxsize=1 << 14)
def _curve_of(sol_lamports: int, token_atoms: int) -> CurveReserves:
    with localcontext(CONTEXT):
        return CurveReserves(Decimal(sol_lamports) / _SOL, Decimal(token_atoms) / _TOK)


def _curve(state: Reserves) -> CurveReserves:
    """The state in curve units. Memoized on its two integers (an immutable result, fixed
    context): every copy whose stop scan crosses an event converted it again (CPU plan step 2);
    16 384 entries hold 8.1 MB (measured) and cover a mint's hour of events."""
    return _curve_of(state.sol_lamports, state.token_atoms)


def buy_atoms(state: Reserves, budget_lamports: int, *, fee_bps: int) -> int | None:
    """Atoms a total spend of ``budget_lamports`` buys (fee on top); ``None`` if not executable.

    Pool: in integers. The net quote is floored to whole lamports so that net plus the
    ceiled fee never exceeds the budget, and the atoms are floored so that the program's
    ceiled exact-out cost of them never exceeds that net.
    """
    if not _executable(state) or budget_lamports <= 0:
        return None
    if state.venue == "curve":
        with localcontext(CONTEXT):
            fee_pct = Decimal(fee_bps) / 100
            tokens = quote_buy(_curve(state), Decimal(budget_lamports) / _SOL, fee_pct).tokens
            return _floor(tokens * _TOK)
    quote_in = budget_lamports * 10_000 // (10_000 + fee_bps)
    return state.token_atoms * quote_in // (state.effective_quote_lamports + quote_in)


def _ceil_bps(amount: int, bps: int) -> int:
    return -(-amount * bps // 10_000)


def sell_lamports(state: Reserves, atoms: int, *, fee_bps: int) -> int | None:
    """Net lamports a sale of ``atoms`` yields; ``None`` if not executable.

    Gross is floored and the fee is ceiled separately (``pumpswap/quote.py``);
    with only the event's *total* bps the three program-side ceilings become
    one, so this can be at most 2 lamports more generous than the program (3 with
    the PumpSwap cashback as a fourth fee). A pool sale is quoted on the effective
    quote and its GROSS capped at the real quote of the vault, then the fee is taken.
    That cap is a research liquidation convention, like the curve's real-SOL ceiling:
    it neither shows the whole sale would execute on chain nor models the vault's exact
    limit (``gross − LP ≤ real quote``); it only binds when the virtual quote is
    positive and the sale is huge.
    """
    if not _executable(state):
        return None
    if atoms <= 0:
        return 0
    if state.venue == "curve":
        real = state.real_sol_lamports
        assert real is not None  # enforced by Reserves
        with localcontext(CONTEXT):
            # ``curve.quote_sell``'s gross leg only (its fee, after-state and marginal price were
            # built and discarded on every stop check — CPU plan step 2); same operations, same
            # context, same refusals, so the same lamport (test_wallets_cpu, wallets_golden).
            reserves, ceiling = _curve(state), Decimal(real) / _SOL
            if ceiling < 0:
                raise ValueError("real_sol_reserves cannot be negative")
            proceeds = min(sell_proceeds(reserves, Decimal(atoms) / _TOK), ceiling)
            if reserves.virtual_sol_reserves - proceeds <= 0:
                raise ValueError("virtual_sol_reserves must be positive")
            gross = _floor(proceeds * _SOL)
    else:
        gross = min(
            state.effective_quote_lamports * atoms // (state.token_atoms + atoms),
            state.sol_lamports,
        )
    return gross - _ceil_bps(gross, fee_bps)


def pre_trade_state(f: Fill) -> Reserves | None:
    """The reserves just before ``f`` (its own trade undone); ``None`` if impossible.

    Curve: the gross SOL leg moved the virtual and the real SOL. Pool: the vault moved
    by the exact flow — a buy added ``sol + lp`` (net quote plus the LP fee), a sale
    paid ``sol − lp`` (gross minus the LP fee, which stays in the pool); the virtual
    quote is a pool parameter the trade does not move. A pre-state whose effective
    quote would not be positive is impossible, never priced.
    """
    sign = 1 if f.side == "buy" else -1
    post = f.reserves
    flow = f.sol_lamports + sign * f.lp_fee_lamports
    sol = post.sol_lamports - sign * flow
    tokens = post.token_atoms + sign * f.token_atoms
    real = None if post.real_sol_lamports is None else post.real_sol_lamports - sign * flow
    virtual = post.virtual_quote_lamports
    if sol <= 0 or tokens <= 0 or (real is not None and real < 0) or sol + virtual <= 0:
        return None
    return Reserves(post.venue, sol, tokens, real, complete=False, virtual_quote_lamports=virtual)


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
        self._ids: frozenset[tuple[str, str, int]] | None = None
        self._by_wallet: dict[str, list[int]] | None = None

    def of_wallets(self, wallets: Iterable[str]) -> list[Fill]:
        """The events of ``wallets`` in tape order — the same subsequence a filter of
        :attr:`fills` yields (the position index is built once, on first use, CPU plan step 2)."""
        if self._by_wallet is None:
            self._by_wallet = {}
            for i, f in enumerate(self.fills):
                self._by_wallet.setdefault(f.wallet, []).append(i)
        at = sorted(i for w in set(wallets) for i in self._by_wallet.get(w, ()))
        return [self.fills[i] for i in at]

    def has(self, identity: tuple[str, str, int]) -> bool:
        """Whether an event of this identity is on the tape (the set is built once, on first
        use: every copy of the mint asks, CPU plan step 2)."""
        if self._ids is None:
            self._ids = frozenset(f.identity for f in self.fills)
        return identity in self._ids

    def _slot_at_or_before(self, slot: int) -> int | None:
        i = bisect_right(self._slots, slot)
        return self._slots[i - 1] if i else None

    def _slot_before(self, slot: int) -> int | None:
        i = bisect_left(self._slots, slot)
        return self._slots[i - 1] if i else None

    def landing_states(self, slot: int) -> tuple[tuple[Reserves, int], ...] | Censored:
        """``(state, fee_bps)`` a landing at ``slot`` may meet (§3.1).

        With trades in the slot: the previous slot's post-states, every post-state
        of the slot **and** every pre-state of the slot (the state before its first
        trade is one of them, whatever the unknown intra-slot order). A trade of the
        slot whose pre-state is impossible makes the worst state unknowable: the
        landing is :data:`CENSORED`, never priced on the states that remain. Without
        trades: the post-states of the last slot ≤ ``slot``.
        """
        if slot in self._by_slot:
            before = self._slot_before(slot)
            prior = self._by_slot[before] if before is not None else []
            here = self._by_slot[slot]
            pre = [(pre_trade_state(f), f.fee_bps) for f in here]
            if any(p is None for p, _ in pre):
                return CENSORED
            undone = [(p, b) for p, b in pre if p is not None]
            return (*((f.reserves, f.fee_bps) for f in (*prior, *here)), *undone)
        last = self._slot_at_or_before(slot)
        if last is None:
            return ()
        return tuple((f.reserves, f.fee_bps) for f in self._by_slot[last])

    def first_after(self, slot: int) -> int:
        """Position in :attr:`fills` of the first event with a slot above ``slot``."""
        return bisect_right(self._fill_slots, slot)

    def observed_through(self, slot: int) -> tuple[Fill, ...]:
        """Every event with slot ≤ ``slot`` (what a watcher had seen by then)."""
        return self.fills[: bisect_right(self._fill_slots, slot)]

    @staticmethod
    def _priceable(
        states: Sequence[tuple[Reserves, int]] | Censored,
    ) -> tuple[tuple[Reserves, int], ...] | Censored | None:
        if isinstance(states, Censored):
            return states
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
