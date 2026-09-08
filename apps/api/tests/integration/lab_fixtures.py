"""Seeding helpers for the S3 Shadow Lab API suite.

New file rather than extending ``analysis_fixtures.py`` — T2.6 is in flight on
that module's routers, and this brief's file list does not include it. Every
row follows the real S0/S2 models exactly (``strategy_versions``,
``agent_signals``, ``signal_outcomes``): no field invented outside what
``services/strategy-worker`` actually writes (SHADOW-LAB.md §2-§6,
``services/strategy-worker/hunter_strategy_worker/record.py``).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from hunter_core.db.models.agents import AgentSignal, SignalOutcome, Strategy, StrategyVersion
from hunter_core.db.models.markets import Exchange, Market
from hunter_core.db.session import role_session
from hunter_core.domain.enums import (
    MarketType,
    OutcomeResult,
    ShadowTrackingState,
    SignalStatus,
    StrategyVersionStatus,
    TradeDirection,
)
from hunter_core.domain.types import uuid7

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

DEFAULT_PARAMETERS: dict[str, Any] = {
    "assumed_spread_bps": "2",
    "slippage_bps": "5",
    "fee_bps": "4",
    "max_entry_delay_s": "120",
}


async def seed_lab_market(session_factory: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    tag = uuid.uuid4().hex[:10]
    async with session_factory() as session:
        exchange = Exchange(code=f"labex{tag}", name=f"labex{tag}")
        session.add(exchange)
        await session.flush()
        market = Market(
            exchange_id=exchange.id,
            symbol=f"LAB{tag.upper()}USDT",
            market_type=MarketType.PERPETUAL,
            is_monitored=True,
        )
        session.add(market)
        await session.commit()
        return market.id


async def seed_strategy_version(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    strategy_id: uuid.UUID | None = None,
    key: str | None = None,
    version: str = "v1",
    status: StrategyVersionStatus = StrategyVersionStatus.ACTIVE,
    activated_at: datetime | None,
    deprecated_at: datetime | None = None,
    code_ref: str | None = "hunter_core.strategies.momentum_v1@sha256:test",
    default_parameters: dict[str, Any] | None = None,
    parameters_schema: dict[str, Any] | None = None,
    changelog: str | None = None,
    purpose: str = "research_only",
    replication_parent_id: uuid.UUID | None = None,
    replication_index: int | None = None,
    promising_at: datetime | None = None,
    promising_by: str | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Returns ``(strategy_id, strategy_version_id)``.

    Pass an existing ``strategy_id`` to add a second version to the same
    strategy (e.g. to test ``superseded_by`` resolution, which is scoped to
    one ``strategy_id``).
    """
    params = DEFAULT_PARAMETERS if default_parameters is None else default_parameters
    async with session_factory() as session:
        if strategy_id is None:
            tag = uuid.uuid4().hex[:10]
            strategy = Strategy(key=key or f"labstrat{tag}", name=key or f"labstrat{tag}")
            session.add(strategy)
            await session.flush()
            strategy_id = strategy.id
        sv = StrategyVersion(
            strategy_id=strategy_id,
            version=version,
            status=status,
            parameters_schema={} if parameters_schema is None else parameters_schema,
            default_parameters=params,
            code_ref=code_ref,
            activated_at=activated_at,
            deprecated_at=deprecated_at,
            changelog=changelog,
            purpose=purpose,
            replication_parent_id=replication_parent_id,
            replication_index=replication_index,
            promising_at=promising_at,
            promising_by=promising_by,
        )
        session.add(sv)
        await session.commit()
        return strategy_id, sv.id


def _envelope(*, decision_at: datetime, source_bar_close: datetime, cohort: str) -> dict[str, Any]:
    return {
        "observation_ts": source_bar_close.isoformat(),
        "decision_at": decision_at.isoformat(),
        "cohort": cohort,
        "timeframe": "15m",
        "strategy_key": "lab-fixture",
        "strategy_version": "v1",
        "purpose": "research_only",
        "params_format": 1,
    }


async def seed_shadow_signal(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    strategy_version_id: uuid.UUID,
    market_id: uuid.UUID,
    decision_at: datetime,
    cohort: str = "prospective",
    tracking_state: ShadowTrackingState = ShadowTrackingState.TERMINAL,
    result: OutcomeResult = OutcomeResult.TARGET,
    no_entry_reason: str | None = None,
    censored_reason: str | None = None,
    entry_ts: datetime | None = None,
    exit_ts: datetime | None = None,
    exit_price: Decimal | None = None,
    r_multiple: Decimal | None = None,
    r_net_reason: str | None = None,
    r_ex_funding: Decimal | None = None,
    horizon_s: int = 14400,
    entry_bar_open: datetime | None = None,
    reference_price: Decimal = Decimal("100"),
    stop: Decimal = Decimal("99"),
    target1: Decimal = Decimal("103"),
    excursions: dict[str, Any] | None = None,
) -> uuid.UUID:
    """One ``agent_signals`` + ``signal_outcomes`` pair, shaped exactly like
    ``hunter_strategy_worker.record``/``persist`` would write it.
    """
    source_bar_close = decision_at - timedelta(seconds=5)
    entry_bar_open = entry_bar_open or (decision_at + timedelta(minutes=1)).replace(
        second=0, microsecond=0
    )
    signal_id = uuid.uuid4()
    meta: dict[str, Any] = {
        "entry_plan": {
            "source_bar_close": source_bar_close.isoformat(),
            "decision_at": decision_at.isoformat(),
            "entry_bar_open": entry_bar_open.isoformat(),
            "delay_s": int((entry_bar_open - source_bar_close).total_seconds()),
            "max_entry_delay_s": 120,
            "late_reason": no_entry_reason
            if no_entry_reason and no_entry_reason.startswith("late:")
            else None,
        },
        "horizon_s": horizon_s,
        "reference_price": str(reference_price),
        "purpose": "research_only",
        "cohort": cohort,
        "excursions": excursions
        if excursions is not None
        else {"unit": "price", "available": False},
        "r_net_reason": r_net_reason,
        "r_ex_funding": None if r_ex_funding is None else str(r_ex_funding),
    }
    async with session_factory() as session:
        session.add(
            AgentSignal(
                id=signal_id,
                strategy_version_id=strategy_version_id,
                market_id=market_id,
                params_hash="test-hash",
                direction=TradeDirection.LONG,
                confidence=Decimal("0.5"),
                stop=stop,
                targets=[str(target1)],
                supporting_features=_envelope(
                    decision_at=decision_at, source_bar_close=source_bar_close, cohort=cohort
                ),
                emitted_at=decision_at,
                status=SignalStatus.ACTIVE,
            )
        )
        session.add(
            SignalOutcome(
                signal_id=signal_id,
                virtual_stop=stop,
                virtual_targets=[str(target1)],
                virtual_entry=reference_price if entry_ts is not None else None,
                entry_ts=entry_ts,
                exit_price=exit_price,
                exit_ts=exit_ts,
                result=result,
                r_multiple=r_multiple,
                tracking_state=tracking_state,
                no_entry_reason=no_entry_reason,
                censored_reason=censored_reason,
                meta=meta,
            )
        )
        await session.commit()
        return signal_id


async def seed_replay_slice(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    run_id: uuid.UUID,
    strategy_version_id: uuid.UUID,
    window_from: datetime,
    window_to: datetime,
    markets: list[str],
    started_at: datetime,
    finished_at: datetime,
    bars_evaluated: int,
    signals: int,
    outcomes_resolved: int,
    outcomes_open: int,
    seconds: Decimal,
    decision_lag_s: int = 90,
    workers: int = 1,
    evaluations_by_state: dict[str, int] | None = None,
    errors: int = 0,
) -> uuid.UUID:
    """One ``replay_runs`` row (one slice), written as ``hunter_worker`` — the
    only role granted ``INSERT`` on it (DATABASE.md §25.4). Mirrors
    ``hunter_strategy_worker.replay.ledger.record_slice`` field for field; no
    ORM model is used here since ``ReplayRunRow`` carries no Python defaults
    for most of these columns.
    """
    slice_id = uuid7()
    async with role_session(session_factory, db_role="hunter_worker") as session:
        await session.execute(
            text(
                "INSERT INTO replay_runs (id, run_id, cohort, strategy_version_id, "
                "window_from, window_to, markets, started_at, finished_at, bars_evaluated, "
                "signals, outcomes_resolved, outcomes_open, seconds, decision_lag_s, workers, "
                "evaluations_by_state, errors) VALUES (:id, :run_id, :cohort, :version_id, "
                ":window_from, :window_to, :markets, :started_at, :finished_at, :bars_evaluated, "
                ":signals, :outcomes_resolved, :outcomes_open, :seconds, :decision_lag_s, "
                ":workers, CAST(:evaluations_by_state AS jsonb), :errors)"
            ),
            {
                "id": slice_id,
                "run_id": run_id,
                "cohort": f"replay:{run_id}",
                "version_id": strategy_version_id,
                "window_from": window_from,
                "window_to": window_to,
                "markets": markets,
                "started_at": started_at,
                "finished_at": finished_at,
                "bars_evaluated": bars_evaluated,
                "signals": signals,
                "outcomes_resolved": outcomes_resolved,
                "outcomes_open": outcomes_open,
                "seconds": str(seconds),
                "decision_lag_s": decision_lag_s,
                "workers": workers,
                "evaluations_by_state": (
                    "{}" if evaluations_by_state is None else _to_jsonb(evaluations_by_state)
                ),
                "errors": errors,
            },
        )
        await session.commit()
    return slice_id


def _to_jsonb(value: dict[str, int]) -> str:
    return json.dumps(value)
