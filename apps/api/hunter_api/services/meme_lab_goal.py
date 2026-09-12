"""The arithmetic of ``GET /meme/lab``: the goal block and the reading of the
worker's heartbeat — pure functions, no IO, tested as a table.

The goal is the decision note's formula
(``obsidian/06-DECISIONS/2026-09-12-meta-7m-e-lab-meme.md`` §2/§4):
``r = (A / C) ^ (1 / d) − 1`` from the capital of **now** and the days still
left, labelled as arithmetic about the target — never a forecast. A field
without a real reading is ``None`` with a reason, never a zero.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal, localcontext
from typing import TYPE_CHECKING

from hunter_api.schemas.meme_lab import GoalOut, NullableDecimalOut, SolUsdOut, SourcesOut
from hunter_api.services.system_status import parse_heartbeat_datetime, parse_heartbeat_int
from hunter_core.strategies.numeric import CONTEXT

if TYPE_CHECKING:
    from hunter_api.repositories.meme_lab import BetQuoteRow

__all__ = ["build_goal", "read_sources", "required_daily_return", "resolve_sol_usd"]


def required_daily_return(
    capital_usd: Decimal, target_usd: Decimal, days_remaining: int
) -> Decimal | None:
    """``(target / capital) ^ (1 / days) − 1`` in ``Decimal``; ``None`` when undefined."""
    if capital_usd <= 0 or days_remaining <= 0:
        return None
    with localcontext(CONTEXT):
        ratio = target_usd / capital_usd
        return (ratio.ln() / Decimal(days_remaining)).exp() - Decimal(1)


def build_goal(
    *,
    today: date,
    clock_start: date,
    clock_start_source: str,
    capital_sol: Decimal,
    sol_usd: SolUsdOut | None,
    sol_usd_reason: str | None,
    pnl_today_sol: Decimal,
    closed_today: int,
    target_usd: Decimal,
    horizon_days: int,
) -> GoalOut:
    days_elapsed = max((today - clock_start).days, 0)
    days_remaining = max(horizon_days - days_elapsed, 0)
    if sol_usd is None:
        capital_usd = NullableDecimalOut(value=None, reason=sol_usd_reason or "no_sol_usd_quote")
        required = NullableDecimalOut(value=None, reason="no_sol_usd_quote")
    else:
        with localcontext(CONTEXT):
            capital = capital_sol * sol_usd.price_usd
        capital_usd = NullableDecimalOut(value=capital)
        rate = required_daily_return(capital, target_usd, days_remaining)
        required = (
            NullableDecimalOut(value=rate)
            if rate is not None
            else NullableDecimalOut(
                value=None,
                reason="horizon_elapsed" if days_remaining <= 0 else "capital_not_positive",
            )
        )
    with localcontext(CONTEXT):
        opening = capital_sol - pnl_today_sol
        measured = (
            NullableDecimalOut(value=pnl_today_sol / opening)
            if closed_today > 0 and opening > 0
            else NullableDecimalOut(
                value=None,
                reason="no_closed_bets_today" if closed_today == 0 else "capital_not_positive",
            )
        )
    return GoalOut(
        target_usd=target_usd,
        horizon_days=horizon_days,
        clock_start=clock_start,
        clock_start_source=clock_start_source,
        days_elapsed=days_elapsed,
        days_remaining=days_remaining,
        capital_sol=capital_sol,
        capital_usd=capital_usd,
        sol_usd=sol_usd,
        sol_usd_reason=sol_usd_reason,
        required_daily_return=required,
        measured_daily_return=measured,
        pnl_today_sol=pnl_today_sol,
    )


def resolve_sol_usd(
    heartbeat: Mapping[str, str] | None, last_bet: BetQuoteRow | None
) -> tuple[SolUsdOut | None, str | None]:
    """The worker's cached quote first (it is the one the loop prices with), the
    last bet's quote second, and a named absence third."""
    if heartbeat and heartbeat.get("lab_sol_usd"):
        observed = parse_heartbeat_datetime(heartbeat.get("lab_sol_usd_observed_at"))
        if observed is not None:
            return (
                SolUsdOut(
                    price_usd=Decimal(heartbeat["lab_sol_usd"]),
                    source=heartbeat.get("lab_sol_usd_source") or "unknown",
                    observed_at=observed,
                    origin="worker_heartbeat",
                ),
                None,
            )
    if last_bet is not None:
        return (
            SolUsdOut(
                price_usd=last_bet.price_usd,
                source=last_bet.source,
                observed_at=last_bet.observed_at,
                origin="last_bet",
            ),
            None,
        )
    return None, "no_sol_usd_quote"


def _refusals(raw: str | None) -> dict[str, dict[str, int]]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    out: dict[str, dict[str, int]] = {}
    for name, counts in parsed.items():  # type: ignore[reportUnknownVariableType]
        if isinstance(counts, dict):
            out[str(name)] = {str(k): int(v) for k, v in counts.items()}  # type: ignore[reportUnknownVariableType]
    return out


def read_sources(
    heartbeat: Mapping[str, str] | None,
    *,
    as_of: datetime,
    key: str,
    stalled_after_s: int,
    error: str | None,
) -> SourcesOut:
    """What the desk shows as "laço vivo" / "laço parado desde …"."""
    fields = heartbeat or {}
    ts = parse_heartbeat_datetime(fields.get("ts"))
    last_tick = parse_heartbeat_datetime(fields.get("lab_last_tick_at"))
    enabled_raw = fields.get("lab_enabled")
    enabled = None if enabled_raw is None else enabled_raw == "true"
    age = None if ts is None else int((as_of - ts).total_seconds())
    tick_age = None if last_tick is None else int((as_of - last_tick).total_seconds())
    if error is not None:
        status = "redis_unavailable"
    elif not fields:
        status = "heartbeat_missing"
    elif enabled is False:
        status = "disabled"
    elif last_tick is None:
        status = "never"
    elif tick_age is not None and tick_age > stalled_after_s:
        status = "stalled"
    else:
        status = "alive"
    return SourcesOut(
        heartbeat_key=key,
        heartbeat_ts=ts,
        heartbeat_age_s=age,
        lab_enabled=enabled,
        lab_last_tick_at=last_tick,
        lab_tick_age_s=tick_age,
        lab_status=status,  # type: ignore[arg-type]
        lab_alive=status == "alive",
        stalled_after_s=stalled_after_s,
        tick_minute=parse_heartbeat_datetime(fields.get("lab_tick_minute")),
        rule_sets_active=parse_heartbeat_int(fields.get("lab_rule_sets_active")),
        rows_evaluated=parse_heartbeat_int(fields.get("lab_rows_evaluated")),
        gate_refusals=_refusals(fields.get("lab_gate_refusals")),
        proposals_total=parse_heartbeat_int(fields.get("lab_proposals_total")),
        fills_total=parse_heartbeat_int(fields.get("lab_fills_total")),
        unfilled_total=parse_heartbeat_int(fields.get("lab_unfilled_total")),
        closes_total=parse_heartbeat_int(fields.get("lab_closes_total")),
        bets_open=parse_heartbeat_int(fields.get("lab_bets_open")),
        sol_usd_error=fields.get("lab_sol_usd_error") or None,
    )
