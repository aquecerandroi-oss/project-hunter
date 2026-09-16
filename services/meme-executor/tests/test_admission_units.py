"""T4.28e — the admission's curve-progress denominator is in the curve's unit.

Measured on 16/09/2026 11:46–11:48 BRT, first hour of stage 1 with real money:
four auto-approved buys of one mint refused ``progress_below_window`` with
``progress ≈ −541 546``. ``meme_tokens.initial_real_token_reserves`` is stored
in **tokens** (793 100 000 on a stock curve) and the bonding-curve account read
by RPC counts **sub-units** (6 decimals); the check divided one by the other.
These tests pin the conversion on the way into :class:`MemeContext` and the
window arithmetic with the real numbers of a curve.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_meme_executor.admission import context_from, denominator_subunits
from hunter_meme_executor.repo import TokenContext
from hunter_risk_meme import CurveState
from hunter_risk_meme.checks import curve_progress_check
from hunter_risk_meme.decision import CheckState
from hunter_risk_meme.limits import MEME_PAPER_V0

MINT = "FHcHh1ELbW6e9fMN6ErZnAmAM3y9qpNfMYDLPnfapump"
STOCK_DENOMINATOR_TOKENS = 793_100_000
STOCK_DENOMINATOR_SUBUNITS = 793_100_000_000_000


def _token(denominator: int | Decimal | None, *, now: datetime) -> TokenContext:
    return TokenContext(
        created_at=now - timedelta(seconds=160),
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


def _curve(real_token_reserves: int, *, now: datetime) -> CurveState:
    return CurveState(
        mint=MINT,
        virtual_sol_reserves=32_000_000_000,
        virtual_token_reserves=real_token_reserves + 279_900_000_000_000,
        real_sol_reserves=2_000_000_000,
        real_token_reserves=real_token_reserves,
        total_supply=1_000_000_000_000_000,
        complete=False,
        creator="AsRQHoHxfBYqvxJZxK9RtJUnRZcCwUoh9KNpVxH6Jhnd",
        is_mayhem_mode=False,
        slot=447_300_000,
        commitment="confirmed",
        observed_at=now,
        source="solana_rpc",
    )


class TestDenominatorSubunits:
    def test_tokens_become_subunits(self) -> None:
        assert denominator_subunits(STOCK_DENOMINATOR_TOKENS) == STOCK_DENOMINATOR_SUBUNITS

    def test_a_decimal_from_the_row_is_accepted(self) -> None:
        assert denominator_subunits(Decimal("800943943.6243800000")) == 800_943_943_624_380

    @pytest.mark.parametrize("raw", [None, 0, -1, Decimal("0")])
    def test_missing_or_non_positive_stays_missing(self, raw: int | Decimal | None) -> None:
        assert denominator_subunits(raw) is None


class TestContextFrom:
    def test_the_context_carries_the_denominator_in_the_curves_unit(self) -> None:
        now = datetime(2026, 9, 16, 14, 46, 36, tzinfo=UTC)
        context = context_from(
            MINT,
            _token(STOCK_DENOMINATOR_TOKENS, now=now),
            participation_used_sol=Decimal(0),
            now=now,
        )
        assert context.initial_real_token_reserves == STOCK_DENOMINATOR_SUBUNITS

    def test_no_denominator_refuses_by_name_not_by_arithmetic(self) -> None:
        now = datetime(2026, 9, 16, 14, 46, 36, tzinfo=UTC)
        context = context_from(
            MINT, _token(None, now=now), participation_used_sol=Decimal(0), now=now
        )
        result = curve_progress_check(_curve(700_000_000_000_000, now=now), context, MEME_PAPER_V0)
        assert result.state is CheckState.UNAVAILABLE
        assert result.refusal == "progress_denominator_missing"


class TestTheWindowWithRealCurveNumbers:
    """2–50 % of the real reserve sold (``MEME_PAPER_V0``): the numbers a coin
    shows a few minutes after creation, in sub-units as the chain reports them."""

    def test_eleven_percent_sold_is_inside_the_window(self) -> None:
        now = datetime(2026, 9, 16, 14, 46, 36, tzinfo=UTC)
        context = context_from(
            MINT,
            _token(STOCK_DENOMINATOR_TOKENS, now=now),
            participation_used_sol=Decimal(0),
            now=now,
        )
        result = curve_progress_check(_curve(700_000_000_000_000, now=now), context, MEME_PAPER_V0)
        assert result.state is CheckState.PASSED, result
        assert result.value is not None and Decimal("0.117") < result.value < Decimal("0.118")

    def test_one_percent_sold_is_below_the_window_with_a_value_between_zero_and_one(self) -> None:
        now = datetime(2026, 9, 16, 14, 46, 36, tzinfo=UTC)
        context = context_from(
            MINT,
            _token(STOCK_DENOMINATOR_TOKENS, now=now),
            participation_used_sol=Decimal(0),
            now=now,
        )
        result = curve_progress_check(_curve(785_000_000_000_000, now=now), context, MEME_PAPER_V0)
        assert result.refusal == "progress_below_window"
        assert result.value is not None and Decimal(0) <= result.value < Decimal("0.02")

    def test_the_raw_row_value_would_have_refused_everything(self) -> None:
        """The bug, kept as a fence: feeding the row's tokens straight in yields a
        negative progress of five orders of magnitude, never a window."""
        now = datetime(2026, 9, 16, 14, 46, 36, tzinfo=UTC)
        context = context_from(
            MINT,
            _token(STOCK_DENOMINATOR_TOKENS, now=now),
            participation_used_sol=Decimal(0),
            now=now,
        ).model_copy(update={"initial_real_token_reserves": STOCK_DENOMINATOR_TOKENS})
        result = curve_progress_check(_curve(429_000_000_000_000, now=now), context, MEME_PAPER_V0)
        assert result.refusal == "progress_below_window"
        assert result.value is not None and result.value < Decimal(-500_000)
