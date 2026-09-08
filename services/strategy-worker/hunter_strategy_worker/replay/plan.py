"""What a replay run *is*, resolved before a single bar is evaluated — T3.19b.

Split from :mod:`.run` (which is the pool, the ledger and the CLI) along the
seam that matters: this module answers "which version, which markets, which
window, which cohort", and every one of those answers is a refusal when it
cannot be given honestly. A run that silently replayed two of the three markets
it was asked for, or a version whose code this build does not carry, would
publish a number about a population nobody requested.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from hunter_core.db.models.markets import Exchange, Market
from hunter_core.db.session import role_session
from hunter_core.domain.enums import MarketStatus, MarketType, ShadowCohort
from hunter_core.domain.types import ensure_utc
from hunter_strategy_worker.catalogue import ActiveVersion, load_active_versions
from hunter_strategy_worker.config import ShadowConfig, load_config
from hunter_strategy_worker.replay.simulate import ReplayWindow, bar_closes
from hunter_strategy_worker.repo import MarketRow, load_market

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

__all__ = ["RunPlan", "config_for", "day", "resolve_markets", "resolve_version"]


@dataclass(frozen=True, slots=True)
class RunPlan:
    """One resolved run, before a single bar is evaluated."""

    version: ActiveVersion
    markets: tuple[MarketRow, ...]
    window: ReplayWindow
    cohort: str
    lag_s: int

    @property
    def bars_planned(self) -> int:
        per_market = sum(1 for _ in bar_closes(self.window, self.version.timeframe))
        return per_market * len(self.markets)


def day(value: str) -> datetime:
    """``2026-08-08`` or a full ISO instant, always UTC.

    A naive instant is read as UTC rather than as the operator's local time: a
    window that shifted with the timezone of whoever typed it would make two
    runs of "the same" month two different experiments.
    """
    parsed = datetime.fromisoformat(value)
    return ensure_utc(parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC))


async def resolve_version(
    factory: async_sessionmaker[AsyncSession], selector: str
) -> ActiveVersion:
    """The runnable version named by a uuid or ``<strategies.key>:<version>``.

    Resolved through :func:`load_active_versions`, never by a query of its own:
    that function is what refuses a version this build cannot honestly run
    (``code_ref`` mismatch, missing code, ``purpose = live``), and a replay of a
    version this binary does not carry would attribute decisions to code that
    never produced them.
    """
    async with role_session(factory, db_role="hunter_worker") as session:
        versions = await load_active_versions(session)
    try:
        wanted = uuid.UUID(selector)
    except ValueError:
        key, _, label = selector.partition(":")
        matches = [v for v in versions if v.strategy_key == key and v.version == label]
    else:
        matches = [v for v in versions if v.id == wanted]
    if len(matches) != 1:
        available = ", ".join(f"{v.strategy_key}:{v.version}" for v in versions)
        raise SystemExit(
            f"version {selector!r} is not one runnable version (runnable: {available})"
        )
    return matches[0]


async def resolve_markets(
    factory: async_sessionmaker[AsyncSession], *, exchange: str, symbols: str
) -> tuple[MarketRow, ...]:
    """``all`` (every monitored active perpetual) or an explicit comma list.

    An explicitly named symbol that does not exist is a hard stop, not a skip.

    ``all`` reads ``markets.is_monitored`` **as of now**, which is the honest
    limit of a replay: the universe is overwritten in place and the schema keeps
    no per-bar membership history, so the set a replay covers is today's set,
    not the set of the window (``replay/environment.py``).
    """
    if symbols.strip().lower() != "all":
        rows: list[MarketRow] = []
        for symbol in (s.strip().upper() for s in symbols.split(",") if s.strip()):
            async with role_session(factory, db_role="hunter_worker") as session:
                market = await load_market(session, exchange, symbol)
            if market is None:
                raise SystemExit(f"market {exchange}:{symbol} does not exist")
            rows.append(market)
        return tuple(rows)
    async with role_session(factory, db_role="hunter_worker") as session:
        found: list[Any] = list(
            (
                await session.execute(
                    select(
                        Market.id, Market.symbol, Market.is_monitored, Market.status, Exchange.code
                    )
                    .join(Exchange, Exchange.id == Market.exchange_id)
                    .where(
                        Exchange.code == exchange,
                        Market.market_type == MarketType.PERPETUAL,
                        Market.status == MarketStatus.ACTIVE,
                        Market.is_monitored.is_(True),
                    )
                    .order_by(Market.symbol)
                )
            ).all()
        )
    return tuple(
        MarketRow(
            id=row.id,
            symbol=row.symbol,
            exchange=row.code,
            is_monitored=bool(row.is_monitored),
            status=row.status,
        )
        for row in found
    )


def config_for(cohort: str) -> ShadowConfig:
    """The deployment's operational config, with the cohort replaced by the run's.

    Everything else is read from the environment exactly as the live worker
    reads it (``SHADOW_*``): a replay with a different ``context_minutes`` or a
    different ``censor_after_s`` would not be the same experiment, and the point
    of the engine is that it is.
    """
    base = load_config()
    if not ShadowCohort.is_valid(cohort) or not cohort.startswith(ShadowCohort.REPLAY_PREFIX):
        raise SystemExit(f"{cohort!r} is not a replay cohort (replay:<uuid>)")
    return ShadowConfig(
        cohort=cohort,
        context_minutes=base.context_minutes,
        hot_state_tail=base.hot_state_tail,
        eligibility_max_lag_s=base.eligibility_max_lag_s,
        outcome_poll_s=base.outcome_poll_s,
        outbox_poll_s=base.outbox_poll_s,
        outbox_lag_alert_s=base.outbox_lag_alert_s,
        censor_after_s=base.censor_after_s,
        gap_recovery_max_s=base.gap_recovery_max_s,
        version_refresh_s=base.version_refresh_s,
        consumer_stall_s=base.consumer_stall_s,
    )
