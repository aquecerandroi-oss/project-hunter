"""Assembles ``GET /api/v1/orgs/{org_id}/meme/lab`` (T4.6): the board per rule set,
the distance to the goal, and the sources — from the repository and from the
worker's heartbeat hash, never from a number this module made up.

Pure arithmetic lives in ``meme_lab_goal.py`` (the goal block and the heartbeat
reading); this module is the seam between it and the repository.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, localcontext
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from hunter_api.schemas.meme_lab import (
    DayScoreOut,
    MemeLabOut,
    NullableDecimalOut,
    RuleSetBoardOut,
    RuleSetCeilingsOut,
    WalletOut,
)
from hunter_api.services.meme_lab_goal import build_goal, read_sources, resolve_sol_usd
from hunter_core.strategies.numeric import CONTEXT

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hunter_api.repositories.meme_lab import (
        DayScoreRow,
        MemeLabRepository,
        RuleSetRow,
        WalletRow,
    )

__all__ = ["build_meme_lab", "day_bounds_brt"]

SAO_PAULO = ZoneInfo("America/Sao_Paulo")
DEFAULT_DAYS_LIMIT = 30
GOAL_TARGET_USD = Decimal(7_000_000)
GOAL_HORIZON_DAYS = 30


def day_bounds_brt(as_of: datetime) -> tuple[date, datetime, datetime]:
    """Today in Brasília, and its ``[start, end)`` in UTC."""
    local = as_of.astimezone(SAO_PAULO)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return (
        local.date(),
        start.astimezone(as_of.tzinfo),
        (start + timedelta(days=1)).astimezone(as_of.tzinfo),
    )


def _ratio(numerator: Decimal | None, denominator: int, *, zero_reason: str) -> NullableDecimalOut:
    if numerator is None or denominator == 0:
        return NullableDecimalOut(value=None, reason=zero_reason)
    with localcontext(CONTEXT):
        return NullableDecimalOut(value=numerator / Decimal(denominator))


def day_score_out(row: DayScoreRow) -> DayScoreOut:
    closed = row.closed
    return DayScoreOut(
        day=row.day,
        bets=row.bets,
        closed=closed,
        wins=row.wins,
        win_rate=_ratio(Decimal(row.wins), closed, zero_reason="no_closed_bets"),
        pnl_sol=NullableDecimalOut(value=row.pnl_sol, reason=None if closed else "no_closed_bets"),
        pnl_usd=NullableDecimalOut(
            value=row.pnl_usd,
            reason=None
            if row.pnl_usd is not None
            else ("no_closed_bets" if not closed else "no_sol_usd_quote"),
        ),
        unpriced_usd=row.unpriced_usd,
        r_sum=NullableDecimalOut(value=row.r_sum, reason=None if closed else "no_closed_bets"),
        avg_r=_ratio(row.r_sum, closed, zero_reason="no_closed_bets"),
        max_drawdown_sol=NullableDecimalOut(
            value=row.max_drawdown_sol, reason=None if closed else "no_closed_bets"
        ),
        rugs=row.rugs,
    )


def _ceilings(params: Mapping[str, object]) -> RuleSetCeilingsOut:
    def dec(key: str) -> Decimal:
        return Decimal(str(params[key]))

    return RuleSetCeilingsOut(
        size_sol=dec("size_sol"),
        target_x=dec("target_x"),
        trailing_pct=dec("trailing_pct"),
        max_hold_s=int(str(params["max_hold_s"])),
        wallet_max_sol=dec("wallet_max_sol"),
        max_sol_per_bet=dec("max_sol_per_bet"),
        daily_loss_cap_sol=dec("daily_loss_cap_sol"),
    )


def wallet_out(rule_set: RuleSetRow, wallet: WalletRow) -> WalletOut:
    wallet_max = Decimal(str(rule_set.params["wallet_max_sol"]))
    with localcontext(CONTEXT):
        balance = wallet_max + wallet.realized_total_sol - wallet.open_exposure_sol
        equity = balance + wallet.open_marks_sol
    return WalletOut(
        balance_sol=balance,
        open_positions=wallet.open_positions,
        open_exposure_sol=wallet.open_exposure_sol,
        open_marks_sol=wallet.open_marks_sol,
        equity_sol=equity,
        realized_total_sol=wallet.realized_total_sol,
        realized_today_sol=wallet.realized_today_sol,
    )


async def build_meme_lab(
    repo: MemeLabRepository,
    heartbeat: Mapping[str, str] | None,
    *,
    as_of: datetime,
    heartbeat_key: str,
    redis_error: str | None = None,
    days_limit: int = DEFAULT_DAYS_LIMIT,
    stalled_after_s: int = 180,
) -> MemeLabOut:
    today, day_start, day_end = day_bounds_brt(as_of)
    rule_sets = await repo.rule_sets()
    scores = await repo.scoreboard(since=today - timedelta(days=days_limit - 1))
    by_rule_set: dict[str, list[DayScoreRow]] = {}
    for row in scores:
        by_rule_set.setdefault(row.rule_set_id, []).append(row)
    boards: list[RuleSetBoardOut] = []
    capital_sol = Decimal(0)
    pnl_today = Decimal(0)
    closed_today = 0
    for rule_set in rule_sets:
        wallet = await repo.wallet(rule_set.id, day_start=day_start, day_end=day_end)
        wallet_view = wallet_out(rule_set, wallet)
        days = [day_score_out(r) for r in by_rule_set.get(rule_set.id, [])][:days_limit]
        today_row = next((d for d in days if d.day == today), None)
        if rule_set.status == "active":
            with localcontext(CONTEXT):
                capital_sol += wallet_view.equity_sol
                pnl_today += wallet.realized_today_sol
            closed_today += wallet.closed_today
        boards.append(
            RuleSetBoardOut(
                id=rule_set.id,  # type: ignore[arg-type]
                name=rule_set.name,
                version=rule_set.version,
                kind=rule_set.kind,  # type: ignore[arg-type]
                exp_ref=rule_set.exp_ref,
                status=rule_set.status,  # type: ignore[arg-type]
                code_ref=rule_set.code_ref,
                ceilings=_ceilings(rule_set.params),
                wallet=wallet_view,
                today=today_row,
                today_reason=None if today_row is not None else "no_bets_today",
                days=days,
            )
        )
    sources = read_sources(
        heartbeat,
        as_of=as_of,
        key=heartbeat_key,
        stalled_after_s=stalled_after_s,
        error=redis_error,
    )
    sol_usd, sol_usd_reason = resolve_sol_usd(heartbeat, await repo.last_bet_quote())
    clock_start = min((r.created_at for r in rule_sets), default=as_of).astimezone(SAO_PAULO).date()
    goal = build_goal(
        today=today,
        clock_start=clock_start,
        clock_start_source="meme_rule_sets.created_at mais antigo (seed da migração 0022 — o dia em que o Lab passou a existir)",
        capital_sol=capital_sol,
        sol_usd=sol_usd,
        sol_usd_reason=sol_usd_reason,
        pnl_today_sol=pnl_today,
        closed_today=closed_today,
        target_usd=GOAL_TARGET_USD,
        horizon_days=GOAL_HORIZON_DAYS,
    )
    return MemeLabOut(
        as_of=as_of, day=today, days_limit=days_limit, rule_sets=boards, goal=goal, sources=sources
    )
