"""CPU plan step 4 (09/10/2026), part 3: the stop index's own edges, chosen by hand.

The random differentials (``test_wallets_stops_scan``) let two mutants live (Astra, diff review):
``atoms <= limit`` turned into ``<`` and a block skipped without its ``min_safe`` guard. Each test
here pins one edge with a tiny known state and checks the index against the Decimal quote itself
(``stops.quote_stopped``, the rule). Synthetic (not data).
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

import pytest

from hunter_indicators.meme.wallets.pricing import sell_lamports
from hunter_indicators.meme.wallets.stops import (
    UNBOUNDED,
    StopIndex,
    _guess,  # pyright: ignore[reportPrivateUsage]
    quote_stopped,
    stop_limit,
)
from hunter_indicators.meme.wallets.tape import Fill, Reserves
from packages.indicators.tests.meme.test_wallets_builders import SOL, curve, fill, pool

pytestmark = pytest.mark.unit

_SMALL = pool(17, 23)
"""``S = 17, T = 23``, no virtual quote: a sale of 3 atoms yields exactly 1 lamport, 4 yield 2,
23 yield 8 (Astra's scenario)."""


def _tape(states: Sequence[Reserves], fee_bps: int = 0) -> list[Fill]:
    return [fill(wallet=f"W{i}", side="buy", slot=1_000 + i, sol=SOL // 5, atoms=1, reserves=s,
                 fee_bps=fee_bps) for i, s in enumerate(states)]  # fmt: skip


def _brute(fills: Sequence[Fill], start: int, end: int, atoms: int, floor: Decimal) -> int:
    return next((k for k in range(start, end) if quote_stopped(fills[k], atoms, floor)), end)


def test_the_index_stops_at_exactly_the_limit() -> None:
    """``atoms == limit``: the sale equals the floor, and ``≤`` stops (a ``<`` would not)."""
    assert [sell_lamports(_SMALL, a, fee_bps=0) for a in (3, 4)] == [1, 2]
    fills = _tape([_SMALL])
    index = StopIndex(fills, Decimal(1))
    assert index.stopped(0, 3) and not index.stopped(0, 4)
    assert index.first_stop(0, 1, 3) == 0 and index.first_stop(0, 1, 4) == 1


def test_a_block_with_an_unproven_event_is_not_skipped() -> None:
    """64 events that do not stop 23 atoms (limit 3 each), but event 31 is a curve outside the
    proven region (``sol = 10²⁸``: ``safe = 0``) whose real SOL of 0 makes every sale 0 — it
    stops. The block's largest limit (3) is below 23, so only ``min_safe`` (0) forbids the skip."""
    states = [_SMALL] * 64
    states[31] = Reserves("curve", 10**28, 1, 0)
    fills = _tape(states)
    assert sell_lamports(states[31], 23, fee_bps=0) == 0
    assert StopIndex(fills, Decimal(1)).first_stop(0, 64, 23) == 31 == _brute(fills, 0, 64, 23,
                                                                              Decimal(1))  # fmt: skip


def test_a_refusal_inside_a_block_is_not_skipped_either() -> None:
    """The same block with a refusing curve at 31 (negative real SOL): the scan must raise."""
    states = [_SMALL] * 64
    states[31] = curve(45 * SOL, real_sol=-1)
    with pytest.raises(ValueError, match="real_sol_reserves"):
        StopIndex(_tape(states), Decimal(1)).first_stop(0, 64, 23)


@pytest.mark.parametrize("floor", [Decimal("-0.1"), Decimal(0), Decimal(1), Decimal("1.9")])
def test_misaligned_starts_partial_tails_and_fractional_floors(floor: Decimal) -> None:
    """Starts inside a block, ends inside one, a tape whose last block is partial, and floors
    whose integer part differs from a truncation (``-0.1`` floors to −1, not 0)."""
    states = [pool(17 + i % 5, 23 + i % 7) for i in range(200)]
    states[150] = pool(1, 23)  # sells anything for 0 lamports: stops at any floor ≥ 0
    fills = _tape(states, fee_bps=125)
    index = StopIndex(fills, floor)
    for start, end in ((0, 200), (5, 200), (63, 129), (64, 128), (130, 199), (149, 151)):
        for atoms in (1, 2, 3, 4, 23, 10**6, UNBOUNDED + 1):
            assert index.first_stop(start, end, atoms) == _brute(fills, start, end, atoms, floor)


def test_atoms_beyond_the_sentinel_use_the_quote() -> None:
    """``UNBOUNDED`` is a finite sentinel: a larger position is checked by the quote (still exact)."""
    fills = _tape([pool(10**40, 23)])
    index = StopIndex(fills, Decimal(10**39))
    for atoms in (UNBOUNDED, UNBOUNDED + 1, 10**60):
        assert index.stopped(0, atoms) == quote_stopped(fills[0], atoms, Decimal(10**39))


def test_the_rounding_can_move_the_limit_below_the_integer_guess() -> None:
    """Found by a targeted search (09/10/2026), inside the proven region: the exact gross at the
    guess is a hair below the next lamport and the 28-digit quotient rounds it up to it, so the
    real limit is one atom below the integer guess — the certifying quotes are what make the limit
    exact, not the guess's algebra (the "trust the guess" mutant survived every other test)."""
    state = Reserves("curve", 17, 162_455_598_713_001_957_295_345_810, 16)
    guess = _guess(state, 125, 11)
    limit = stop_limit(state, 125, 11, 588_235_294_117_647_058_823_529_411)
    assert guess == 527_980_695_817_256_361_209_873_882 and limit == guess - 1
    assert sell_lamports(state, limit, fee_bps=125) == 11
    assert (sell_lamports(state, guess, fee_bps=125) or 0) > 11
