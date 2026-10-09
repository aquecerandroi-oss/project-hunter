"""The copy stop as an integer comparison (CPU plan step 4, 09/10/2026). Same rule, same lamport.

The rule (``policy``): a copy holding ``atoms`` stops at an observed event when
``sell_lamports(event.reserves, atoms, fee_bps=event.fee_bps) ≤ floor`` (``floor = stop_fraction ×
budget``, a finite Decimal; a completed curve quotes ``None`` and never stops; a refusal raises).
Quoting that sale in Decimal for every (copy, event) of the exit window made the cost of a mint
≈ copies × events — superlinear on the hot keys (KB-0187). Here each event is solved once per
floor: the largest atom count whose sale stays ≤ the floor (:func:`stop_limit`), after which a
copy's check is ``atoms ≤ limit``.

**That is exact only where the net sale is non-decreasing in atoms. Proof** (tests in
``test_wallets_stops_monotone``):

- **Pool** (integers): ``gross = min(Q·a // (T + a), S)`` with ``Q`` = effective quote > 0 and
  ``T`` > 0 — the exact rational is increasing in ``a``, its floor and the cap are non-decreasing
  (whatever the sign of the virtual quote). ``net = g − ⌈g·b/10⁴⌉ = ⌊g·(10⁴ − b)/10⁴⌋`` is
  non-decreasing in ``g`` for ``0 ≤ b < 10⁴`` (enforced by ``Fill``). No refusal. Monotone for
  every atom count.
- **Curve** (Decimal, 28 digits, HALF_EVEN): ``Sv = sol/10⁹``, ``t = atoms/10⁶``, ``Tv =
  token/10⁶`` are exact (their coefficients are at most ``sol``, ``atoms``, ``token``). When
  ``sol·atoms < 10²⁸`` and ``token + atoms < 10²⁸``, ``Sv·t`` and ``Tv + t`` are exact too, so the
  quotient is the correctly rounded value of an increasing rational — non-decreasing. ``min``
  with the real-SOL ceiling keeps it; ``× 10⁹`` only appends zeros to a ≤ 28-digit coefficient,
  so its rounding changes nothing; the floor and the fee keep it. Refusals: a negative real SOL
  refuses every sale, and ``virtual − proceeds ≤ 0`` is impossible when ``real < sol`` (proceeds
  ≤ ceiling < ``Sv``). So the region is ``0 ≤ real < sol`` and ``atoms ≤`` :func:`monotone_atoms`.
- **Outside it the sale is NOT monotone**: a targeted search found consecutive atom counts whose
  quote drops a lamport (``sol ≈ 5,7·10²¹``, ``sol·atoms`` with 44 digits; pinned in the tests).

So a copy with ``atoms > monotone_atoms(state)`` is checked by the Decimal quote, refusals
included, exactly as before. A limit is found by an integer guess **certified by quotes of
``sell_lamports`` itself** (``net(c) ≤ F < net(c + 1)``) and repaired by search when the guess
is off: its correctness rests on the monotonicity alone, not on the guess's algebra.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from decimal import ROUND_FLOOR, Decimal, localcontext
from typing import Final

from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.meme.wallets.pricing import MintTape, sell_lamports
from hunter_indicators.meme.wallets.tape import Fill, Reserves

__all__ = ["UNBOUNDED", "StopIndex", "monotone_atoms", "quote_stopped", "stop_index", "stop_limit"]

UNBOUNDED: Final = 1 << 128
"""A bound no copy reaches; beyond it a copy is checked by the quote anyway (still exact)."""
_EXACT: Final = 10**28  # 10 ** CONTEXT.prec
_BLOCK: Final = 64


def monotone_atoms(state: Reserves) -> int:
    """A sufficient bound: up to this atom count the state's net sale is proven monotone and
    refusal-free (0 = none; the region is conservative, the sale may be monotone beyond it).
    A completed curve never quotes (never stops): unbounded. Clamped at 0 (Astra: ``sol = 2,
    token = 10²⁸`` gave −1)."""
    if state.venue == "pool" or state.complete:
        return UNBOUNDED
    real = state.real_sol_lamports
    if real is None or not 0 <= real < state.sol_lamports:
        return 0
    return max(0, min((_EXACT - 1) // state.sol_lamports, _EXACT - 1 - state.token_atoms))


def _guess(state: Reserves, fee_bps: int, floor: int) -> int:
    """Where the exact gross first exceeds the largest gross whose net is ≤ ``floor``; minus one.
    A starting point only — :func:`stop_limit` certifies or repairs it with real quotes."""
    keep = 10_000 - fee_bps
    gross_max = ((floor + 1) * 10_000 + keep - 1) // keep - 1
    if state.venue == "pool":
        q, cap = state.effective_quote_lamports, state.sol_lamports
    else:
        q, cap = state.sol_lamports, state.real_sol_lamports
    if (cap is not None and cap <= gross_max) or q <= gross_max + 1:
        return UNBOUNDED
    over = gross_max + 1
    return -(-over * state.token_atoms // (q - over)) - 1


def _bracket(net: Callable[[int], int], floor: int, c: int, safe: int) -> tuple[int, int | None]:
    """Gallop from the guess ``c`` (in ``[0, safe]``) to ``(lo, hi)`` with ``net(lo) ≤ floor <
    net(hi)``, every probe in ``[0, safe]``; ``hi = None`` when the whole ``[lo, safe]`` stays at
    or below the floor (no transition: the limit is ``safe``, Astra must-fix 2)."""
    if c > 0 and net(c) > floor:
        hi, step = c, 1
        while True:
            probe = max(0, hi - step)
            if probe == 0 or net(probe) <= floor:  # net(0) = 0 ≤ floor
                return probe, hi
            hi, step = probe, step * 2
    lo, step = c, 1
    while lo < safe:
        probe = min(safe, lo + step)
        if net(probe) > floor:
            return lo, probe
        lo, step = probe, step * 2
    return lo, None


def stop_limit(state: Reserves, fee_bps: int, floor: int, safe: int) -> int:
    """The largest ``a`` in ``[0, safe]`` with ``sell_lamports(state, a) ≤ floor``; −1 when no
    atom count stops (a negative floor, or a completed curve). ``safe`` ≤ :func:`monotone_atoms`.
    Only a completed CURVE is unquotable (``pricing``); a pool carrying the flag is still quoted."""
    if floor < 0 or (state.venue == "curve" and state.complete):
        return -1

    def net(a: int) -> int:
        value = sell_lamports(state, a, fee_bps=fee_bps)
        assert value is not None  # executable: a completed curve returned above
        return value

    lo, hi = _bracket(net, floor, min(max(_guess(state, fee_bps, floor), 0), safe), safe)
    if hi is None:
        return lo
    while hi - lo > 1:
        mid = (lo + hi) // 2
        lo, hi = (mid, hi) if net(mid) <= floor else (lo, mid)
    return lo


def quote_stopped(event: Fill, atoms: int, floor: Decimal) -> bool:
    """The rule itself, in Decimal: what every check was before step 4 (and the fallback now)."""
    quote = sell_lamports(event.reserves, atoms, fee_bps=event.fee_bps)
    if quote is None:  # a completed curve cannot be quoted; the timer/censor decide
        return False
    with localcontext(CONTEXT):  # same context as before step 2, whatever the caller's traps
        return Decimal(quote) <= floor


class StopIndex:
    """One tape's events solved for one floor, lazily (an event is solved the first time a copy
    reaches it, once), with per-block summaries so a copy skips blocks that cannot stop it."""

    def __init__(self, fills: Sequence[Fill], floor: Decimal) -> None:
        self._fills, self._floor = fills, floor
        self._int_floor = int(floor.to_integral_value(rounding=ROUND_FLOOR))
        self._limit: list[int | None] = [None] * len(fills)
        self._safe: list[int] = [0] * len(fills)
        blocks = -(-len(fills) // _BLOCK)
        self._block_max: list[int | None] = [None] * blocks  # largest limit of the block
        self._block_safe: list[int] = [0] * blocks  # smallest monotone bound of the block

    def _solve(self, k: int) -> int:
        limit = self._limit[k]
        if limit is None:
            event = self._fills[k]
            safe = monotone_atoms(event.reserves)
            limit = stop_limit(event.reserves, event.fee_bps, self._int_floor, safe)
            self._limit[k], self._safe[k] = limit, safe
        return limit

    def stopped(self, k: int, atoms: int) -> bool:
        """Whether event ``k`` stops a copy of ``atoms`` — the quote's answer, refusals included."""
        limit = self._solve(k)
        if 1 <= atoms <= self._safe[k]:
            return atoms <= limit
        return quote_stopped(self._fills[k], atoms, self._floor)

    def _skippable(self, b: int, atoms: int) -> bool:
        top = self._block_max[b]
        if top is None:
            first = b * _BLOCK
            span = range(first, first + _BLOCK)
            top = max(self._solve(k) for k in span)
            self._block_max[b], self._block_safe[b] = top, min(self._safe[k] for k in span)
        return top < atoms <= self._block_safe[b]

    def first_stop(self, start: int, end: int, atoms: int) -> int:
        """The first ``k`` in ``[start, end)`` whose event stops a copy of ``atoms``; ``end`` if
        none. Visiting events in order, so a refusal raises where the old scan raised."""
        k = start
        while k < end:
            if (
                k % _BLOCK == 0
                and k + _BLOCK <= end
                and atoms >= 1
                and self._skippable(k // _BLOCK, atoms)
            ):
                k += _BLOCK
                continue
            if self.stopped(k, atoms):
                return k
            k += 1
        return end


def stop_index(tape: MintTape, floor: Decimal) -> StopIndex:
    """The tape's index for ``floor`` (one per distinct floor value, shared by every copy)."""
    index = tape.stop_indexes.get(floor)
    if index is None:
        index = tape.stop_indexes[floor] = StopIndex(tape.fills, floor)
    return index
