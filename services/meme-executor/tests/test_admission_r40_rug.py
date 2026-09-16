"""R40 — a sub-2 % progress on a curve that had SOL 19 s ago is the rug, not a bug.

16/09/2026: 8 buys were refused ``progress_below_window`` while the 15 s series
still showed 11,6–23,2 real SOL on the curve. Five of them (INCEPT, CGRAM,
11:46–12:07 BRT) are the unit bug of T4.28e, already fenced by
``test_admission_units.py``. The other three (KYLE 18:42:41/42, BYFD 19:07:02)
are curves that emptied **between** the radar's photo and the executor's own RPC
read, and the numbers below are the chain's, copied from
``meme_curve_snapshots`` (tokens) and from ``meme_live_orders.admission``:

===============  ==========================  ===================
instant (UTC)    ``real_token_reserves``     real SOL on the curve
===============  ==========================  ===================
22:06:49         429 810 129,838366          15,3565
22:07:02 (read)  789 085 421,848878 (*)      —
22:07:07         789 085 421,848878          0,1127
===============  ==========================  ===================

(*) implied by the refusal's own ``value`` and recomputed here: the admission at
22:07:02 saw, to the last digit, the account state the radar photographed 5 s
later. The refusal is the truth of a curve that gave back 359,3 M tokens and
15,24 SOL in 13 s; the 45,8 % of the same admissor 19 s earlier was a different,
live curve. Progress is **not** monotonic in time: tokens come back.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_meme_executor.admission import context_from
from hunter_meme_executor.repo import TokenContext
from hunter_risk_meme import CurveState
from hunter_risk_meme.checks import curve_progress_check
from hunter_risk_meme.decision import CheckState
from hunter_risk_meme.limits import MEME_PAPER_V0

BYFD = "5RMJdDgwjNoGJJ9bZcq5TAGsQ6p5Jh4sZ4PT6XGzpump"
KYLE = "6w89UwMXiaFZ4VRrdXarLuRsa1FRKdSf4YXQhDrUpump"
DENOMINATOR_TOKENS = 793_100_000
"""``meme_tokens.initial_real_token_reserves`` of both mints, ``global_params``,
neither Mayhem — the stock curve, so no denominator of this study is in doubt."""

SUBUNITS = 10**6


def _tokens(value: str) -> int:
    return int(Decimal(value) * SUBUNITS)


def _context(mint: str, now: datetime, *, denominator: int | None = DENOMINATOR_TOKENS):
    token = TokenContext(
        created_at=now - timedelta(seconds=170),
        creator="AsRQHoHxfBYqvxJZxK9RtJUnRZcCwUoh9KNpVxH6Jhnd",
        initial_real_token_reserves=denominator,  # type: ignore[arg-type]  # the repo hands an int
        completed_at=None,
        migrated_at=None,
        curve_volume_1m_sol=Decimal("20"),
        features_end_time=now - timedelta(seconds=30),
        creator_sold=False,
        top10_share=Decimal("0.15"),
        bundled_share=Decimal("0.05"),
    )
    return context_from(mint, token, participation_used_sol=Decimal(0), now=now)


def _curve(mint: str, real_token_reserves: int, real_sol: str, now: datetime) -> CurveState:
    lamports = int(Decimal(real_sol) * 10**9)
    return CurveState(
        mint=mint,
        virtual_sol_reserves=30 * 10**9 + lamports,
        virtual_token_reserves=real_token_reserves + 279_900_000_000_000,
        real_sol_reserves=lamports,
        real_token_reserves=real_token_reserves,
        total_supply=1_000_000_000_000_000,
        complete=False,
        creator="AsRQHoHxfBYqvxJZxK9RtJUnRZcCwUoh9KNpVxH6Jhnd",
        is_mayhem_mode=False,
        slot=447_632_031,
        commitment="confirmed",
        observed_at=now,
        source="solana_rpc",
    )


class TestByfdTheSameMintNineteenSecondsApart:
    def test_the_full_curve_at_22_06_49_passes_the_window(self) -> None:
        now = datetime(2026, 9, 16, 22, 6, 49, tzinfo=UTC)
        result = curve_progress_check(
            _curve(BYFD, _tokens("429810129.838366"), "15.3565459590", now),
            _context(BYFD, now),
            MEME_PAPER_V0,
        )
        assert result.state is CheckState.PASSED, result
        assert result.value is not None
        assert Decimal("0.458") < result.value < Decimal("0.459")

    def test_the_emptied_curve_at_22_07_02_refuses_with_the_recorded_value(self) -> None:
        """``meme_live_orders`` id ``01a0ac42-50b4-76f0-b231-560a275a3f29``:
        ``value = 0.005061881416116504854368932039``, ``limit = 0.02``."""
        now = datetime(2026, 9, 16, 22, 7, 2, tzinfo=UTC)
        result = curve_progress_check(
            _curve(BYFD, _tokens("789085421.848878"), "0.1126652680", now),
            _context(BYFD, now),
            MEME_PAPER_V0,
        )
        assert result.refusal == "progress_below_window"
        assert result.value is not None
        assert result.value.quantize(Decimal("1e-27")) == Decimal("0.005061881416116504854368932")


class TestKyleTheDumpLandedBetweenTwoPhotos:
    @pytest.mark.parametrize(
        ("second", "reserves", "expected"),
        [
            (41, "779655422.656287", Decimal("0.01695193209395158239818433993")),
            (42, "779802975.890581", Decimal("0.01676588590268440297566511159")),
        ],
    )
    def test_the_refusal_values_of_18_42_are_the_arithmetic_of_a_rugged_curve(
        self, second: int, reserves: str, expected: Decimal
    ) -> None:
        now = datetime(2026, 9, 16, 21, 42, second, tzinfo=UTC)
        result = curve_progress_check(
            _curve(KYLE, _tokens(reserves), "0.3299540190", now),
            _context(KYLE, now),
            MEME_PAPER_V0,
        )
        assert result.refusal == "progress_below_window"
        assert result.value is not None
        assert abs(result.value - expected) < Decimal("1e-15")

    def test_the_reserves_sit_between_the_two_neighbouring_photos(self) -> None:
        """21:42:34 → 426 486 606,93 tokens; 21:42:48 → 781 427 035,29. The two
        reads of the admissor are inside that gap and monotone: one dump."""
        assert (
            _tokens("426486606.932710")
            < _tokens("779655422.656287")
            < _tokens("779802975.890581")
            < _tokens("781427035.292443")
        )


class TestADenominatorSmallerThanTheTruthCanPassALateCurve:
    """The check never asserts that the denominator and ``real_token_reserves``
    come from the same curve. Too **large** a denominator (the T4.28e direction,
    or a row in sub-units) only ever refuses; too **small** by ~4× turns a curve
    with 80 % of its reserve already sold into an apparent 20 % and **passes**.
    Nothing in today's data does this — every mint of R40 carries the stock
    793,1 M from ``global_params`` — but the fence is arithmetic, not policy."""

    def test_a_quarter_denominator_turns_eighty_percent_sold_into_a_pass(self) -> None:
        now = datetime(2026, 9, 16, 22, 7, 2, tzinfo=UTC)
        real = _tokens("158620000")  # 20 % of 793,1 M left: 80 % sold, far past the 50 % cap
        truthful = curve_progress_check(
            _curve(BYFD, real, "70", now), _context(BYFD, now), MEME_PAPER_V0
        )
        assert truthful.refusal == "progress_above_window"

        understated = curve_progress_check(
            _curve(BYFD, real, "70", now),
            _context(BYFD, now, denominator=DENOMINATOR_TOKENS // 4),
            MEME_PAPER_V0,
        )
        assert understated.state is CheckState.PASSED, understated
        assert Decimal("0.19") < (understated.value or Decimal(0)) < Decimal("0.21")
