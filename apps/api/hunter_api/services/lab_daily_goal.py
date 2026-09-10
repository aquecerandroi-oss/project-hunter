"""Assembles ``GET /api/v1/orgs/{org_id}/lab/daily-goal`` (brief T3.78).

Mirrors ``services/portfolio_queries.py``: a service that *does* read the
repository (unlike the Shadow Lab ``build_*`` functions, which are pure and
let the router hold the loop) because pricing a day's bets is itself a loop
of small, independent reads (one candle lookup per unique bet) that belongs
next to the arithmetic it feeds, not duplicated into the router.

Pure math lives in ``lab_daily_goal_bets.py`` (dedupe, the two R sums) and
``lab_daily_goal_sizing.py`` (value of 1R, percentiles) — this module is the
seam between them and the repository.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from hunter_api.schemas.lab_daily_goal import (
    AxisOut,
    DailyGoalOut,
    PortfolioReferenceOut,
    ProgressOut,
    SeriesPointOut,
    ValueOfOneROut,
)
from hunter_api.schemas.lab_scoreboard import RateWithCountsOut
from hunter_api.services.lab_daily_goal_bets import DedupedBet, dedupe_bets, sum_axis
from hunter_api.services.lab_daily_goal_sizing import (
    BetPricingInput,
    label_brl,
    percentile,
    price_bet,
)
from hunter_risk.exposure import SAO_PAULO, sao_paulo_day_start_utc

if TYPE_CHECKING:
    from hunter_api.repositories.lab_daily_goal import DailyOutcomeRow, LabDailyGoalRepository

__all__ = ["build_daily_goal", "resolve_day_window"]

_SERIES_DAYS = 30
_PERCENTILES = (Decimal("0.10"), Decimal("0.50"), Decimal("0.90"))
_ZERO = Decimal(0)


def resolve_day_window(day: date | None, as_of_utc: datetime) -> tuple[datetime, datetime, date]:
    """``[start, end)`` of one Sao Paulo calendar day, and the day itself.

    ``day is None`` -> today in Sao Paulo, from ``as_of_utc``. A caller-given
    ``day`` is anchored at local noon before the Sao Paulo day boundary is
    computed, so the choice of hour never crosses midnight either way.
    """
    if day is None:
        start = sao_paulo_day_start_utc(as_of_utc)
    else:
        noon_local = datetime.combine(day, time(12, 0), tzinfo=SAO_PAULO)
        start = sao_paulo_day_start_utc(noon_local)
    end = start + timedelta(days=1)
    return start, end, start.astimezone(SAO_PAULO).date()


async def _rows_in_window(
    repo: LabDailyGoalRepository, *, window_start: datetime, window_end: datetime
) -> list[DailyOutcomeRow]:
    versions = await repo.active_versions()
    rows: list[DailyOutcomeRow] = []
    for version in versions:
        rows.extend(
            await repo.outcomes_for_version(
                version, window_start=window_start, window_end=window_end
            )
        )
    return rows


async def _price_bets(
    repo: LabDailyGoalRepository, deduped: list[DedupedBet], *, equity_usdt: Decimal | None
) -> list[Decimal]:
    """Real-BRL value of 1R for every priceable bet — ``fx``/``equity``
    unavailable means nothing is priceable, never a guessed rate or capital.
    """
    if equity_usdt is None:
        return []
    priced: list[Decimal] = []
    for bet in deduped:
        winner = bet.winner
        volume = (
            await repo.entry_minute_quote_volume(winner.market_id, winner.entry_ts)
            if winner.entry_ts is not None
            else None
        )
        result = price_bet(
            BetPricingInput(
                virtual_entry=winner.virtual_entry,
                virtual_stop=winner.virtual_stop,
                assumed_costs_raw=winner.meta.get("assumed_costs"),
                quote_volume=volume,
            ),
            equity_usdt=equity_usdt,
        )
        if result.value_1r_usdt is not None:
            priced.append(result.value_1r_usdt)
    return priced


def _bucket_by_brt_day(rows: list[DailyOutcomeRow]) -> dict[date, list[DailyOutcomeRow]]:
    buckets: dict[date, list[DailyOutcomeRow]] = {}
    for row in rows:
        local_day = row.exit_ts.astimezone(SAO_PAULO).date()
        buckets.setdefault(local_day, []).append(row)
    return buckets


async def _series_30d(repo: LabDailyGoalRepository, *, target_day: date) -> list[SeriesPointOut]:
    series_end = sao_paulo_day_start_utc(
        datetime.combine(target_day, time(12, 0), tzinfo=SAO_PAULO)
    ) + timedelta(days=1)
    series_start = series_end - timedelta(days=_SERIES_DAYS)
    rows = await _rows_in_window(repo, window_start=series_start, window_end=series_end)
    buckets = _bucket_by_brt_day(rows)
    points: list[SeriesPointOut] = []
    for offset in range(_SERIES_DAYS - 1, -1, -1):
        day = target_day - timedelta(days=offset)
        day_rows = buckets.get(day, [])
        sums = sum_axis(day_rows, dedupe_bets(day_rows))
        points.append(SeriesPointOut(day=day, unique_r=sums.unique_r, pooled_r=sums.pooled_r))
    return points


def _value_of_1r(priced_brl: list[Decimal]) -> ValueOfOneROut:
    label = label_brl()
    if not priced_brl:
        return ValueOfOneROut(
            label_brl=label,
            real_brl_p10=None,
            real_brl_p50=None,
            real_brl_p90=None,
            sample_size=0,
            reason="no_priceable_bets",
        )
    p10, p50, p90 = (percentile(priced_brl, pct) for pct in _PERCENTILES)
    return ValueOfOneROut(
        label_brl=label,
        real_brl_p10=p10,
        real_brl_p50=p50,
        real_brl_p90=p90,
        sample_size=len(priced_brl),
    )


def _progress(*, unique_r: Decimal, value_of_1r: ValueOfOneROut, goal_brl: Decimal) -> ProgressOut:
    label_progress = unique_r * value_of_1r.label_brl
    real_progress = (
        None if value_of_1r.real_brl_p50 is None else unique_r * value_of_1r.real_brl_p50
    )
    required_1r = None if unique_r <= _ZERO else goal_brl / unique_r
    required_unique_r = (
        None
        if value_of_1r.real_brl_p50 is None or value_of_1r.real_brl_p50 <= _ZERO
        else goal_brl / value_of_1r.real_brl_p50
    )
    return ProgressOut(
        real_brl=real_progress,
        label_brl=label_progress,
        distance_to_goal_real_brl=None if real_progress is None else goal_brl - real_progress,
        distance_to_goal_label_brl=goal_brl - label_progress,
        required_1r_brl=required_1r,
        required_unique_r=required_unique_r,
    )


async def build_daily_goal(
    repo: LabDailyGoalRepository, *, day: date | None, as_of: datetime, goal_brl: Decimal
) -> DailyGoalOut:
    window_start, window_end, local_day = resolve_day_window(day, as_of)
    day_rows = await _rows_in_window(repo, window_start=window_start, window_end=window_end)
    deduped = dedupe_bets(day_rows)
    sums = sum_axis(day_rows, deduped)

    fx = await repo.latest_fx_brl(window_end)
    equity = await repo.principal_portfolio_equity_usdt(window_end)
    priced_usdt = await _price_bets(repo, deduped, equity_usdt=equity.equity_usdt)
    priced_brl = [value * fx.rate for value in priced_usdt] if fx is not None else []
    value_of_1r = _value_of_1r(priced_brl)
    if fx is None and priced_usdt:
        # Priceable in USDT but not convertible: still "no priceable bets" in
        # BRL terms, never a guessed rate (module docstring).
        value_of_1r = ValueOfOneROut(
            label_brl=value_of_1r.label_brl,
            real_brl_p10=None,
            real_brl_p50=None,
            real_brl_p90=None,
            sample_size=0,
            reason="no_fx_observation",
        )

    hit_rate = RateWithCountsOut(
        value=None if sums.unique_bets == 0 else Decimal(sums.unique_wins) / sums.unique_bets,
        reason=None if sums.unique_bets else "no_evaluable_unique_bets",
        numerator=sums.unique_wins,
        denominator=sums.unique_bets,
    )
    r_per_bet = None if len(deduped) == 0 else sums.unique_r / len(deduped)

    return DailyGoalOut(
        day=local_day,
        as_of=as_of,
        axis=AxisOut(
            pooled_funding_null=sums.pooled_funding_null,
            unique_funding_null=sums.unique_funding_null,
        ),
        unique_bets=len(deduped),
        pooled_bets=len(day_rows),
        unique_r=sums.unique_r,
        pooled_r=sums.pooled_r,
        hit_rate=hit_rate,
        r_per_unique_bet=r_per_bet,
        value_of_1r=value_of_1r,
        goal_brl=goal_brl,
        progress=_progress(unique_r=sums.unique_r, value_of_1r=value_of_1r, goal_brl=goal_brl),
        portfolio=PortfolioReferenceOut(equity_usdt=equity.equity_usdt, source=equity.source),
        fx_reason=None if fx is not None else "no_fx_observation",
        series_30d=await _series_30d(repo, target_day=local_day),
    )
