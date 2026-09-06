"""Kill switch: escalation is automatic, de-escalation is an explicit act."""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest

from hunter_core.domain.enums import KillSwitchState
from hunter_risk.exposure import PortfolioState
from hunter_risk.kill_switch import (
    KillSwitchInputs,
    ResumeAuthorization,
    assess,
    most_restrictive,
    resume,
)
from hunter_risk.limits import PAPER_V1

from .factories import NOW, portfolio

pytestmark = pytest.mark.unit

PORTFOLIO_ID = uuid.UUID("00000000-0000-7000-8000-0000000000aa")


def _loss(pct: str) -> PortfolioState:
    equity = Decimal("20000")
    return portfolio(
        equity=equity * (Decimal(1) - Decimal(pct)),
        peak_equity=equity,
        cash=equity,
        daily_realized_pnl=-equity * Decimal(pct),
    )


class TestOrdering:
    def test_the_most_restrictive_scope_wins(self) -> None:
        assert (
            most_restrictive(
                KillSwitchState.ACTIVE, KillSwitchState.EMERGENCY, KillSwitchState.WARNING
            )
            is KillSwitchState.EMERGENCY
        )

    def test_ordering_is_by_restriction_not_by_the_string_value(self) -> None:
        # "WARNING" > "EMERGENCY" and > "TRADING_DISABLED" lexicographically; max() on the
        # StrEnum would pick WARNING and quietly let entries through under EMERGENCY.
        assert (
            most_restrictive(KillSwitchState.WARNING, KillSwitchState.EMERGENCY)
            is KillSwitchState.EMERGENCY
        )
        assert (
            most_restrictive(KillSwitchState.WARNING, KillSwitchState.TRADING_DISABLED)
            is KillSwitchState.TRADING_DISABLED
        )


class TestAutomaticEscalation:
    def test_a_quiet_day_stays_active(self) -> None:
        got = assess(portfolio(), PAPER_V1, KillSwitchInputs())
        assert got.effective is KillSwitchState.ACTIVE
        assert got.entry_size_multiplier == Decimal("1")
        assert got.blocks_entries is False
        assert got.cancel_pending is False

    def test_one_percent_daily_loss_raises_the_warning(self) -> None:
        got = assess(_loss("0.01"), PAPER_V1, KillSwitchInputs())
        assert got.effective is KillSwitchState.WARNING
        assert got.trigger == "daily_loss"
        assert got.entry_size_multiplier == Decimal("0.5")
        assert got.blocks_entries is False

    def test_four_percent_drawdown_raises_the_warning_on_its_own(self) -> None:
        state = portfolio(equity=Decimal("19200"), peak_equity=Decimal("20000"))
        got = assess(state, PAPER_V1, KillSwitchInputs())
        assert got.effective is KillSwitchState.WARNING
        assert got.trigger == "drawdown"

    def test_two_percent_daily_loss_blocks(self) -> None:
        got = assess(_loss("0.02"), PAPER_V1, KillSwitchInputs())
        assert got.effective is KillSwitchState.TRADING_DISABLED
        assert got.blocks_entries is True
        assert got.cancel_pending is True
        assert got.entry_size_multiplier == Decimal("0")

    def test_eight_percent_drawdown_blocks(self) -> None:
        state = portfolio(equity=Decimal("18400"), peak_equity=Decimal("20000"))
        got = assess(state, PAPER_V1, KillSwitchInputs())
        assert got.effective is KillSwitchState.TRADING_DISABLED
        assert got.trigger == "drawdown"

    def test_a_scope_latch_is_never_lowered_by_the_automatic_assessment(self) -> None:
        got = assess(
            portfolio(),
            PAPER_V1,
            KillSwitchInputs(portfolio=KillSwitchState.TRADING_DISABLED),
        )
        assert got.automatic is KillSwitchState.ACTIVE
        assert got.effective is KillSwitchState.TRADING_DISABLED

    def test_time_alone_never_clears_a_block(self) -> None:
        blocked = _loss("0.02")
        later = blocked.model_copy(update={"as_of": NOW + timedelta(hours=4)})
        assert (
            assess(
                later, PAPER_V1, KillSwitchInputs(portfolio=KillSwitchState.TRADING_DISABLED)
            ).effective
            is KillSwitchState.TRADING_DISABLED
        )


class TestResume:
    def _auth(self, **over: object) -> ResumeAuthorization:
        base: dict[str, object] = {
            "authorized_by": "everton",
            "portfolio_id": PORTFOLIO_ID,
            "from_state": KillSwitchState.TRADING_DISABLED,
            "to_state": KillSwitchState.ACTIVE,
            "reason": "revisao concluida",
        }
        return ResumeAuthorization.model_validate(base | over)

    def test_an_explicit_act_clears_the_latch(self) -> None:
        assessment = assess(portfolio(), PAPER_V1, KillSwitchInputs())
        assert (
            resume(KillSwitchState.TRADING_DISABLED, self._auth(), assessment, PORTFOLIO_ID)
            is KillSwitchState.ACTIVE
        )

    def test_an_empty_author_is_not_an_authorisation(self) -> None:
        with pytest.raises(ValueError, match="authorized_by"):
            self._auth(authorized_by="   ")

    def test_the_authorisation_must_name_the_portfolio_it_unlocks(self) -> None:
        assessment = assess(portfolio(), PAPER_V1, KillSwitchInputs())
        with pytest.raises(ValueError, match="portfolio"):
            resume(
                KillSwitchState.TRADING_DISABLED,
                self._auth(),
                assessment,
                uuid.UUID("00000000-0000-7000-8000-0000000000ff"),
            )

    def test_the_authorisation_must_match_the_state_it_was_written_for(self) -> None:
        assessment = assess(portfolio(), PAPER_V1, KillSwitchInputs())
        with pytest.raises(ValueError, match="from_state"):
            resume(KillSwitchState.EMERGENCY, self._auth(), assessment, PORTFOLIO_ID)

    def test_resume_never_escalates(self) -> None:
        assessment = assess(portfolio(), PAPER_V1, KillSwitchInputs())
        with pytest.raises(ValueError, match="de-escalate"):
            resume(
                KillSwitchState.WARNING,
                self._auth(from_state=KillSwitchState.WARNING, to_state=KillSwitchState.EMERGENCY),
                assessment,
                PORTFOLIO_ID,
            )

    def test_clearing_the_latch_does_not_override_a_breach_that_is_still_open(self) -> None:
        still_losing = _loss("0.02")
        assessment = assess(still_losing, PAPER_V1, KillSwitchInputs())
        cleared = resume(KillSwitchState.TRADING_DISABLED, self._auth(), assessment, PORTFOLIO_ID)
        assert cleared is KillSwitchState.ACTIVE
        after = assess(still_losing, PAPER_V1, KillSwitchInputs(portfolio=cleared))
        assert after.effective is KillSwitchState.TRADING_DISABLED
