"""CPU plan step 4 (09/10/2026), part 1: is the rounded net sale monotone in atoms? Prove first.

The stop threshold (``stops.stop_limit``) is only exact where ``sell_lamports`` is non-decreasing
in the atoms sold. The proof (``stops`` module docstring): the pool is integer arithmetic,
monotone everywhere; the curve is monotone where its 28-digit products and sums are exact
(``sol × atoms < 10²⁸`` and ``token + atoms < 10²⁸``) and refusal-free (``0 ≤ real < sol``).
Outside that region it is NOT monotone (counterexample pinned below), so beyond
``monotone_atoms`` the stop falls back to the Decimal quote. Synthetic grids (not data).
"""

from __future__ import annotations

import random
from collections.abc import Iterator
from decimal import Decimal

import pytest

from hunter_indicators.meme.wallets.pricing import sell_lamports
from hunter_indicators.meme.wallets.stops import UNBOUNDED, monotone_atoms, stop_limit
from hunter_indicators.meme.wallets.tape import Reserves
from packages.indicators.tests.meme.test_wallets_builders import SOL, TOKEN, curve, pool

pytestmark = pytest.mark.unit

_EXACT = 10**28
_BPS = (0, 1, 25, 30, 95, 100, 125, 130, 9_998, 9_999)
"""Total fee rates: none, LP only (25 / 30), curve 1 % / 1,25 %, LP + protocol + creator +
cashback summed (130), and the extremes of the range ``Fill`` accepts (0 ≤ bps < 10 000)."""


def _pools(rng: random.Random, n: int) -> Iterator[Reserves]:
    """Real quote from 1 lamport to 10⁸ SOL, base from 1 atom to 10²⁴, virtual quote negative
    (down to just above −real), zero or positive (up to 10⁶ SOL)."""
    for _ in range(n):
        real = rng.choice((1, rng.randrange(1, SOL), rng.randrange(SOL, 10**17)))
        base = rng.choice((1, rng.randrange(1, 10**9), rng.randrange(10**9, 10**24)))
        virtual = rng.choice((0, -real + 1, -rng.randrange(0, real), rng.randrange(0, 10**15)))
        yield pool(real, base, virtual=virtual)


def _curves(rng: random.Random, n: int) -> Iterator[Reserves]:
    """Virtual SOL from 1 lamport to 10¹⁴ (≈ 50 000× a live curve), tokens from 1 atom to
    10²¹, the real SOL anywhere in [0, sol) — cap binding or not."""
    for _ in range(n):
        sol = rng.choice((1 + rng.randrange(1, 9), rng.randrange(30 * SOL, 90 * SOL),
                          rng.randrange(10, 10**14)))  # fmt: skip
        tokens = rng.choice((1, rng.randrange(1, 10**12), rng.randrange(10**12, 10**21)))
        real = rng.choice((0, sol - 1, rng.randrange(0, sol), max(0, sol - 30 * SOL)))
        yield Reserves("curve", sol, tokens, real)


def _atoms(rng: random.Random, safe: int) -> int:
    top = min(safe, 10**24)
    return rng.choice((1, rng.randrange(1, min(top, 10**6) + 1), rng.randrange(1, top + 1)))


def _q(state: Reserves, atoms: int, bps: int) -> int:
    value = sell_lamports(state, atoms, fee_bps=bps)
    return 0 if value is None else value


def _monotone_around(state: Reserves, a: int, bps: int, safe: int, width: int = 6) -> None:
    lo, hi = max(0, a - width), min(safe, a + width)
    values = [sell_lamports(state, x, fee_bps=bps) for x in range(lo, hi + 1)]
    assert all(v is not None for v in values)
    assert values == sorted(values), (state, lo, bps, values)  # type: ignore[type-var]


def test_the_pool_sale_is_monotone_in_atoms_everywhere() -> None:
    rng = random.Random(41)
    for state in _pools(rng, 3_000):
        assert monotone_atoms(state) == UNBOUNDED
        bps = rng.choice(_BPS)
        a, b = sorted((_atoms(rng, 10**24), _atoms(rng, 10**24)))
        assert _q(state, a, bps) <= _q(state, b, bps)
        _monotone_around(state, _atoms(rng, 10**24), bps, 10**25)


def test_the_curve_sale_is_monotone_inside_the_exact_region() -> None:
    rng = random.Random(42)
    for state in _curves(rng, 3_000):
        safe = monotone_atoms(state)
        assert safe == min((_EXACT - 1) // state.sol_lamports, _EXACT - 1 - state.token_atoms)
        bps = rng.choice(_BPS)
        a, b = sorted((_atoms(rng, safe), _atoms(rng, safe)))
        assert _q(state, a, bps) <= _q(state, b, bps)
        _monotone_around(state, _atoms(rng, safe), bps, safe)
        _monotone_around(state, safe, bps, safe)  # the region's own edge


def test_the_curve_sale_is_not_monotone_outside_the_region() -> None:
    """Found by a targeted search (09/10/2026): deep saturation, ``sol × atoms`` with 44 digits.
    The 28-digit product rounds and the quote steps DOWN one lamport between consecutive atoms —
    so a threshold there would be wrong, and ``monotone_atoms`` must stop before it."""
    sol, tokens = 5_726_728_952_428_415_334_803, 2_324
    state = Reserves("curve", sol, tokens, sol - 1)
    a = 5_726_728_952_428_415_332_479
    values = [sell_lamports(state, a + j, fee_bps=0) for j in range(5)]
    up, down = 5_726_728_952_428_415_332_479, 5_726_728_952_428_415_332_478
    assert values == [up, up, down, down, up]  # down at a + 2, up at a + 4 (Astra reproduced it)
    assert monotone_atoms(state) < a


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (curve(40 * SOL), min((_EXACT - 1) // (40 * SOL), _EXACT - 1 - 1_073_000_000 * TOKEN)),
        (curve(40 * SOL, real_sol=40 * SOL), 0),  # real = virtual: the refusal is reachable
        (curve(40 * SOL, real_sol=-1), 0),  # negative real: every sale refuses
        (curve(40 * SOL, complete=True), UNBOUNDED),  # never quotable, never a stop
        (pool(40 * SOL, 10**15, virtual=-39 * SOL), UNBOUNDED),
        (Reserves("curve", 2, 10**28, 1), 0),  # Astra must-fix 1: the formula gave −1
    ],
)
def test_the_monotone_bound_of_a_state(state: Reserves, expected: int) -> None:
    assert monotone_atoms(state) == expected


def _floors(rng: random.Random) -> int:
    return rng.choice((-1, 0, 1, rng.randrange(0, 10**6), rng.randrange(0, 10**12), 25_000_000))


def _check_limit(state: Reserves, bps: int, floor: int, rng: random.Random) -> None:
    safe = monotone_atoms(state)
    limit = stop_limit(state, bps, floor, safe)
    if floor < 0 or (state.venue == "curve" and state.complete):
        assert limit == -1
        return
    assert 0 <= limit <= safe
    assert (sell_lamports(state, limit, fee_bps=bps) or 0) <= floor
    if limit < safe:
        assert (sell_lamports(state, limit + 1, fee_bps=bps) or 0) > floor
    for _ in range(4):  # the threshold decides like the quote, for atoms in the region
        atoms = _atoms(rng, max(1, safe)) if safe else 1
        if 1 <= atoms <= safe:
            quote = sell_lamports(state, atoms, fee_bps=bps)
            assert (atoms <= limit) == (Decimal(quote or 0) <= floor)


def test_the_limit_is_the_largest_atom_count_whose_sale_stays_at_or_below_the_floor() -> None:
    rng = random.Random(43)
    states = [*_pools(rng, 1_500), *_curves(rng, 1_500)]
    for state in states:
        _check_limit(state, rng.choice(_BPS), _floors(rng), rng)


def test_the_limit_on_live_shaped_states_and_edges() -> None:
    """The stop's own scale (floor = 0,5 × 0,05 SOL), a cap that binds below the floor (every
    sale stops: the limit is the whole region), a complete curve and a negative floor."""
    rng = random.Random(44)
    floor = 25_000_000
    for state in (curve(31 * SOL), curve(84 * SOL), curve(45 * SOL, real_sol=SOL // 100),
                  pool(45 * SOL, 10**15), pool(45 * SOL, 10**15, virtual=-44 * SOL),
                  pool(SOL // 100, 10**15, virtual=20 * SOL), curve(45 * SOL, complete=True)):  # fmt: skip
        for bps in (0, 100, 125, 9_999):
            _check_limit(state, bps, floor, rng)
            _check_limit(state, bps, -1, rng)
    capped = curve(45 * SOL, real_sol=SOL // 100)
    assert stop_limit(capped, 125, floor, monotone_atoms(capped)) == monotone_atoms(capped)


def test_every_atom_count_stops_without_a_transition() -> None:
    """Astra must-fix 2: pool ``Q = 2, T = 1, S = 2``, no fee, floor 1 — every positive sale nets
    1 lamport, so the limit is the whole region; the inverse would divide by zero there and a
    certificate ``net(c) ≤ F < net(c + 1)`` does not exist."""
    state = pool(2, 1)
    assert {sell_lamports(state, a, fee_bps=0) for a in (1, 2, 10**6, 10**30)} == {1}
    assert stop_limit(state, 0, 1, UNBOUNDED) == UNBOUNDED
    assert stop_limit(state, 0, 0, UNBOUNDED) == 0


def test_a_pool_flagged_complete_is_still_quoted_and_can_stop() -> None:
    """Only a completed CURVE is unquotable (``pricing._executable``); ``Reserves`` does not forbid
    the flag on a pool, whose sale is still quoted — so it must still be able to stop."""
    state = Reserves("pool", 45 * SOL, 10**15, None, complete=True)
    assert sell_lamports(state, 1, fee_bps=0) == 0  # quoted (the old stop would compare it)
    limit = stop_limit(state, 0, 25_000_000, monotone_atoms(state))
    assert limit > 0 and (sell_lamports(state, limit, fee_bps=0) or 0) <= 25_000_000
    _check_limit(state, 125, 25_000_000, random.Random(45))
