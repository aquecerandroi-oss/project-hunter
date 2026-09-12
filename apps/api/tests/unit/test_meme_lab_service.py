"""``services/meme_lab.py`` and ``services/meme_lab_goal.py`` — pure assembly and
arithmetic, no DB, no Redis (T4.6).

What is proved: the goal block is the decision note's formula from the capital
of *now* and the days left, labelled as arithmetic and never a forecast; every
field without a real reading is ``None`` with a reason; the heartbeat reading
tells "alive" from "stalled", "never", "disabled", "heartbeat_missing" and
"redis_unavailable"; and the wallet is derived from the bets alone.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest

from hunter_api.repositories.meme_lab import (
    BetQuoteRow,
    DayScoreRow,
    MemeLabRepository,
    RuleSetRow,
    WalletRow,
)
from hunter_api.schemas.meme_lab import MEME_LAB_GOAL_LABEL, MEME_LAB_LABEL
from hunter_api.services.meme_lab import build_meme_lab, day_bounds_brt
from hunter_api.services.meme_lab_goal import read_sources, required_daily_return, resolve_sol_usd

pytestmark = pytest.mark.unit

AS_OF = datetime(2026, 9, 12, 15, 30, tzinfo=UTC)  # 12:30 BRT
TODAY = date(2026, 9, 12)
RESEARCH = "01994d00-6c1a-7000-8000-000000000001"
RETIRED = "01994d00-6c1a-7000-8000-0000000000aa"
PARAMS: dict[str, Any] = {
    "size_sol": "0.05",
    "target_x": "2",
    "trailing_pct": "30",
    "max_hold_s": 900,
    "wallet_max_sol": "2.0",
    "max_sol_per_bet": "0.05",
    "daily_loss_cap_sol": "0.20",
}


def _rule_set(**overrides: Any) -> RuleSetRow:
    base: dict[str, Any] = {
        "id": RESEARCH,
        "name": "meme_paper_v0",
        "version": "1",
        "kind": "research_only",
        "exp_ref": "EXP-M1",
        "status": "active",
        "code_ref": "hunter_indicators.meme.rules:evaluate_entry+evaluate_exit",
        "params": PARAMS,
        "created_at": datetime(2026, 9, 12, 8, 0, tzinfo=UTC),
    }
    base.update(overrides)
    return RuleSetRow(**base)


class FakeRepository:
    def __init__(
        self,
        rule_sets: list[RuleSetRow],
        wallets: dict[str, WalletRow],
        scores: list[DayScoreRow],
        quote: BetQuoteRow | None = None,
    ) -> None:
        self._rule_sets, self._wallets, self._scores, self._quote = (
            rule_sets,
            wallets,
            scores,
            quote,
        )

    async def rule_sets(self) -> list[RuleSetRow]:
        return self._rule_sets

    async def wallet(
        self, rule_set_id: str, *, day_start: datetime, day_end: datetime
    ) -> WalletRow:
        assert day_start < AS_OF < day_end
        return self._wallets[rule_set_id]

    async def scoreboard(self, *, since: date) -> list[DayScoreRow]:
        return [s for s in self._scores if s.day >= since]

    async def last_bet_quote(self) -> BetQuoteRow | None:
        return self._quote

    def as_repo(self) -> MemeLabRepository:
        return cast(MemeLabRepository, self)


WALLET = WalletRow(
    realized_total_sol=Decimal("0.10"),
    realized_today_sol=Decimal("0.10"),
    closed_today=2,
    open_positions=1,
    open_exposure_sol=Decimal("0.05"),
    open_marks_sol=Decimal("0.06"),
)
SCORE = DayScoreRow(
    rule_set_id=RESEARCH,
    day=TODAY,
    bets=3,
    closed=2,
    wins=1,
    pnl_sol=Decimal("0.10"),
    pnl_usd=Decimal("10.14"),
    unpriced_usd=0,
    r_sum=Decimal("2.0"),
    max_drawdown_sol=Decimal("0.03"),
    rugs=0,
)
HEARTBEAT = {
    "ts": AS_OF.isoformat(),
    "lab_enabled": "true",
    "lab_last_tick_at": (AS_OF - timedelta(seconds=40)).isoformat(),
    "lab_tick_minute": (AS_OF - timedelta(minutes=2)).isoformat(),
    "lab_rule_sets_active": "2",
    "lab_rows_evaluated": "117",
    "lab_gate_refusals": '{"meme_paper_v0": {"creator_net_seller_unknown": 117}}',
    "lab_proposals_total": "0",
    "lab_fills_total": "0",
    "lab_unfilled_total": "0",
    "lab_closes_total": "0",
    "lab_bets_open": "1",
    "lab_sol_usd": "101.4445",
    "lab_sol_usd_observed_at": (AS_OF - timedelta(seconds=30)).isoformat(),
    "lab_sol_usd_source": "pumpfun_rest:/sol-price",
    "lab_sol_usd_error": "",
}


def test_the_day_is_brasilia_and_its_bounds_are_utc() -> None:
    today, start, end = day_bounds_brt(
        datetime(2026, 9, 13, 2, 30, tzinfo=UTC)
    )  # 23:30 BRT of the 12th
    assert today == TODAY
    assert start == datetime(2026, 9, 12, 3, 0, tzinfo=UTC) and end == start + timedelta(days=1)


def test_required_daily_return_is_the_decision_notes_formula() -> None:
    """350x in 30 days is +21,6 %/day; 70x is +15,2 %/day (the note's own table)."""
    assert required_daily_return(Decimal(20_000), Decimal(7_000_000), 30) is not None
    r350 = required_daily_return(Decimal(20_000), Decimal(7_000_000), 30)
    r70 = required_daily_return(Decimal(100_000), Decimal(7_000_000), 30)
    assert r350 is not None and abs(r350 - Decimal("0.21563")) < Decimal("0.0001")
    assert r70 is not None and abs(r70 - Decimal("0.15213")) < Decimal("0.0001")
    assert required_daily_return(Decimal(0), Decimal(7_000_000), 30) is None
    assert required_daily_return(Decimal(20_000), Decimal(7_000_000), 0) is None


async def test_the_board_derives_the_wallet_from_the_bets_and_the_goal_from_now() -> None:
    repo = FakeRepository([_rule_set()], {RESEARCH: WALLET}, [SCORE]).as_repo()
    out = await build_meme_lab(
        repo, HEARTBEAT, as_of=AS_OF, heartbeat_key="hb:meme:radar", days_limit=30
    )
    assert out.label == MEME_LAB_LABEL and out.day == TODAY
    (board,) = out.rule_sets
    assert board.wallet.balance_sol == Decimal("2.05")  # 2.0 + 0.10 − 0.05
    assert board.wallet.equity_sol == Decimal("2.11")  # + 0.06 of marks
    assert board.today is not None and board.today.bets == 3
    assert board.today.win_rate.value == Decimal("0.5")
    assert board.today.avg_r.value == Decimal(1)
    assert board.ceilings.max_sol_per_bet == Decimal("0.05")
    goal = out.goal
    assert goal.label == MEME_LAB_GOAL_LABEL
    assert goal.clock_start == TODAY and goal.days_elapsed == 0 and goal.days_remaining == 30
    assert goal.capital_sol == Decimal("2.11")
    assert goal.sol_usd is not None and goal.sol_usd.origin == "worker_heartbeat"
    assert goal.capital_usd.value == Decimal("2.11") * Decimal("101.4445")
    expected = required_daily_return(Decimal("2.11") * Decimal("101.4445"), Decimal(7_000_000), 30)
    assert (
        goal.required_daily_return.value == expected
    )  # US$ 214 → US$ 7 M in 30 days ≈ +41,4 %/dia
    assert expected is not None and abs(expected - Decimal("0.41412")) < Decimal("0.0001")
    assert goal.measured_daily_return.value == Decimal("0.10") / Decimal("2.01")
    assert out.sources.lab_status == "alive" and out.sources.lab_alive
    assert out.sources.gate_refusals == {"meme_paper_v0": {"creator_net_seller_unknown": 117}}
    assert out.sources.rows_evaluated == 117 and out.sources.bets_open == 1


async def test_without_a_quote_or_bets_every_field_is_null_with_a_reason() -> None:
    empty = WalletRow(Decimal(0), Decimal(0), 0, 0, Decimal(0), Decimal(0))
    repo = FakeRepository([_rule_set()], {RESEARCH: empty}, []).as_repo()
    out = await build_meme_lab(repo, {}, as_of=AS_OF, heartbeat_key="hb:meme:radar")
    (board,) = out.rule_sets
    assert board.today is None and board.today_reason == "no_bets_today"
    assert board.wallet.equity_sol == Decimal("2.0")
    assert out.goal.capital_usd.value is None and out.goal.capital_usd.reason == "no_sol_usd_quote"
    assert out.goal.required_daily_return.reason == "no_sol_usd_quote"
    assert out.goal.measured_daily_return.reason == "no_closed_bets_today"
    assert out.sources.lab_status == "heartbeat_missing" and not out.sources.lab_alive


async def test_the_last_bet_quote_is_the_fallback_and_a_retired_set_does_not_count_as_capital() -> (
    None
):
    quote = BetQuoteRow(Decimal("99.5"), "pumpfun_rest:/sol-price", AS_OF - timedelta(hours=3))
    retired = _rule_set(id=RETIRED, name="old", status="retired", exp_ref="EXP-M0")
    repo = FakeRepository(
        [_rule_set(), retired], {RESEARCH: WALLET, RETIRED: WALLET}, [SCORE], quote=quote
    ).as_repo()
    out = await build_meme_lab(
        repo, {"ts": AS_OF.isoformat()}, as_of=AS_OF, heartbeat_key="hb:meme:radar"
    )
    assert out.goal.sol_usd is not None and out.goal.sol_usd.origin == "last_bet"
    assert out.goal.capital_sol == Decimal("2.11"), "the retired set's wallet is not capital"
    assert out.sources.lab_status == "never"


@pytest.mark.parametrize(
    ("fields", "error", "status"),
    [
        (None, "ConnectionError", "redis_unavailable"),
        ({}, None, "heartbeat_missing"),
        ({"ts": AS_OF.isoformat(), "lab_enabled": "false"}, None, "disabled"),
        ({"ts": AS_OF.isoformat()}, None, "never"),
        (
            {
                "ts": AS_OF.isoformat(),
                "lab_last_tick_at": (AS_OF - timedelta(seconds=181)).isoformat(),
            },
            None,
            "stalled",
        ),
        (
            {
                "ts": AS_OF.isoformat(),
                "lab_last_tick_at": (AS_OF - timedelta(seconds=179)).isoformat(),
            },
            None,
            "alive",
        ),
    ],
)
def test_the_loop_status_names_every_way_it_can_be_absent(
    fields: dict[str, str] | None, error: str | None, status: str
) -> None:
    sources = read_sources(
        fields, as_of=AS_OF, key="hb:meme:radar", stalled_after_s=180, error=error
    )
    assert sources.lab_status == status
    assert sources.lab_alive == (status == "alive")


def test_a_quote_without_its_instant_is_not_a_quote() -> None:
    assert resolve_sol_usd({"lab_sol_usd": "100"}, None) == (None, "no_sol_usd_quote")
