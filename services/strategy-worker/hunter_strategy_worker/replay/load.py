"""Reading the frozen record of the Lab — SELECT only.

Everything a replayed arm needs is already durable: the levels
(``virtual_stop``/``virtual_targets``), the entry plan, the cost hypothesis and
the horizon (``signal_outcomes.meta``), the frozen ATR
(``agent_signals.supporting_features.atr``) and the 1m candles. The tracking
plan is rebuilt by the production code — :class:`OpenTracking` from
:mod:`hunter_strategy_worker.tracking_repo` — so the replay uses the level that
was written, at the database's own scale, and not a level recomputed from the
strategy.

:func:`read_only_session` is the only session the replay ever opens: the
transaction is marked ``READ ONLY``, so "the replay never writes to a Lab
table" is enforced by Postgres and not by a code review.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import Select, func, select, text

from hunter_core.db.models.agents import AgentSignal, SignalOutcome, Strategy, StrategyVersion
from hunter_core.db.models.markets import Exchange, Market
from hunter_core.db.session import role_session
from hunter_core.domain.enums import MarketStatus, OutcomeResult, ShadowTrackingState
from hunter_core.domain.types import ensure_utc
from hunter_core.strategies.canonical import canonical_json
from hunter_strategy_worker.repo import MarketRow
from hunter_strategy_worker.tracking_repo import OpenTracking
from hunter_strategy_worker.walker import Progress, TrackingPlan

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

__all__ = [
    "ReplayCase",
    "StoredOutcome",
    "VersionRow",
    "input_digest",
    "load_cases",
    "load_manifest",
    "read_only_session",
]

_REPLAYABLE = (ShadowTrackingState.TERMINAL, ShadowTrackingState.NO_ENTRY)


@asynccontextmanager
async def read_only_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """A ``hunter_worker`` transaction Postgres itself will not let write.

    ``REPEATABLE READ`` as well as ``READ ONLY``: the Lab keeps writing while a
    replay runs, and under ``READ COMMITTED`` one arm could see a funding row
    or a candle that the arm before it did not — a difference produced by the
    order the arms were computed in, not by the policies (Astra, R1 diff
    review, must-fix 4). One snapshot for the whole run.
    """
    async with role_session(session_factory, db_role="hunter_worker") as session:
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        yield session


@dataclass(frozen=True, slots=True)
class VersionRow:
    """One frozen ``strategy_version`` of the manifest."""

    id: uuid.UUID
    strategy_key: str
    version: str
    params_hash: str | None
    """The frozen ``params_hash`` its signals carry. It lives on
    ``agent_signals`` (the version row keeps only ``params_format``), and a
    frozen version has exactly one — ``None`` means it emitted no signal."""
    params_format: int
    code_ref: str | None
    activated_at: datetime | None

    @property
    def label(self) -> str:
        return f"{self.strategy_key}_{self.version}"


@dataclass(frozen=True, slots=True)
class StoredOutcome:
    """What the Lab recorded for one signal — the audit reference of step 1."""

    tracking_state: ShadowTrackingState
    result: OutcomeResult
    virtual_entry: Decimal | None
    entry_ts: datetime | None
    exit_price: Decimal | None
    exit_ts: datetime | None
    r_multiple: Decimal | None
    r_ex_funding: Decimal | None
    funding_reason: str | None
    no_entry_reason: str | None
    progress: Progress


@dataclass(frozen=True, slots=True)
class ReplayCase:
    """One frozen entry, everything needed to replay any arm over it."""

    signal_id: uuid.UUID
    version: VersionRow
    market: MarketRow
    source_bar_close: datetime
    plan: TrackingPlan
    targets: tuple[Decimal, ...]
    atr0: Decimal | None
    stored: StoredOutcome

    @property
    def entry_bar_open(self) -> datetime:
        return self.plan.entry_bar_open

    @property
    def horizon_open(self) -> datetime:
        return self.plan.horizon_open


def _decimal(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _atr0(supporting_features: dict[str, Any]) -> Decimal | None:
    atr: Any = supporting_features.get("atr")
    if not isinstance(atr, dict):
        return None
    reading = cast("dict[str, Any]", atr)
    return _decimal(reading.get("value"))


def _manifest_query(keys: Sequence[str]) -> Select[Any]:
    return (
        select(
            StrategyVersion.id,
            Strategy.key,
            StrategyVersion.version,
            func.min(AgentSignal.params_hash).label("params_hash"),
            StrategyVersion.params_format,
            StrategyVersion.code_ref,
            StrategyVersion.activated_at,
        )
        .join(Strategy, Strategy.id == StrategyVersion.strategy_id)
        .join(AgentSignal, AgentSignal.strategy_version_id == StrategyVersion.id, isouter=True)
        .where(Strategy.key.in_(keys), StrategyVersion.activated_at.is_not(None))
        .group_by(
            StrategyVersion.id,
            Strategy.key,
            StrategyVersion.version,
            StrategyVersion.params_format,
            StrategyVersion.code_ref,
            StrategyVersion.activated_at,
        )
        .order_by(Strategy.key, StrategyVersion.version)
    )


async def load_manifest(session: AsyncSession, *, keys: Sequence[str]) -> list[VersionRow]:
    """Every activated version of ``keys``, oldest version first.

    Selected by frozen identity, not by ``status``: a superseded version keeps
    its population and is still part of the experiment (notes-S2.md §20).
    """
    rows = (await session.execute(_manifest_query(keys))).all()
    return [
        VersionRow(
            id=row.id,
            strategy_key=row.key,
            version=row.version,
            params_hash=row.params_hash,
            params_format=int(row.params_format),
            code_ref=row.code_ref,
            activated_at=None if row.activated_at is None else ensure_utc(row.activated_at),
        )
        for row in rows
    ]


_CASE_COLUMNS = (
    SignalOutcome.signal_id,
    SignalOutcome.tracking_state,
    SignalOutcome.result,
    SignalOutcome.virtual_entry,
    SignalOutcome.virtual_stop,
    SignalOutcome.virtual_targets,
    SignalOutcome.exit_price,
    SignalOutcome.exit_ts,
    SignalOutcome.entry_ts,
    SignalOutcome.r_multiple,
    SignalOutcome.no_entry_reason,
    SignalOutcome.meta,
    AgentSignal.strategy_version_id,
    AgentSignal.market_id,
    AgentSignal.supporting_features,
    Market.symbol,
    Market.is_monitored,
    Market.status,
    Exchange.code,
)


def _cases_query(version_ids: Sequence[uuid.UUID], as_of: datetime) -> Select[Any]:
    return (
        select(*_CASE_COLUMNS)
        .join(AgentSignal, AgentSignal.id == SignalOutcome.signal_id)
        .join(Market, Market.id == AgentSignal.market_id)
        .join(Exchange, Exchange.id == Market.exchange_id)
        .where(
            AgentSignal.strategy_version_id.in_(version_ids),
            SignalOutcome.tracking_state.in_(_REPLAYABLE),
            SignalOutcome.meta["entry_plan"]["source_bar_close"].astext <= as_of.isoformat(),
        )
        .order_by(SignalOutcome.signal_id)
    )


def _funding_reason(meta: dict[str, Any]) -> str | None:
    """The reason ``R_net`` is null, wherever the writer of the day put it."""
    reason: Any = meta.get("r_net_reason")
    if reason is not None:
        return str(reason)
    funding: Any = meta.get("funding")
    if not isinstance(funding, dict):
        return None
    reading = cast("dict[str, Any]", funding)
    nested: Any = reading.get("reason")
    return None if nested is None else str(nested)


def _targets(raw: Any) -> tuple[Decimal, ...]:
    """``virtual_targets`` as decimals — one entry for ``volume_anomaly``, three
    for ``momentum`` (target1 plus the two informational ones)."""
    values: list[Any] = list(raw or [])
    return tuple(Decimal(str(value)) for value in values if value is not None)


def _stored(row: Any, meta: dict[str, Any]) -> StoredOutcome:
    return StoredOutcome(
        tracking_state=row.tracking_state,
        result=row.result,
        virtual_entry=_decimal(row.virtual_entry),
        entry_ts=None if row.entry_ts is None else ensure_utc(row.entry_ts),
        exit_price=_decimal(row.exit_price),
        exit_ts=None if row.exit_ts is None else ensure_utc(row.exit_ts),
        r_multiple=_decimal(row.r_multiple),
        r_ex_funding=_decimal(meta.get("r_ex_funding")),
        funding_reason=_funding_reason(meta),
        no_entry_reason=row.no_entry_reason,
        progress=Progress.from_jsonable(meta["progress"]),
    )


async def load_cases(
    session: AsyncSession,
    *,
    versions: Sequence[VersionRow],
    as_of: datetime,
) -> list[ReplayCase]:
    """Every ``terminal``/``no_entry`` outcome of ``versions`` decided by ``as_of``.

    Ordered by ``signal_id`` so two runs over the same database produce the same
    file byte for byte.
    """
    by_id = {version.id: version for version in versions}
    if not by_id:
        return []
    rows = (await session.execute(_cases_query(list(by_id), as_of))).all()
    cases: list[ReplayCase] = []
    for row in rows:
        meta = dict(row.meta or {})
        tracking = OpenTracking(
            signal_id=row.signal_id,
            strategy_version_id=row.strategy_version_id,
            market_id=row.market_id,
            exchange=row.code,
            symbol=row.symbol,
            tracking_state=row.tracking_state,
            virtual_stop=row.virtual_stop,
            virtual_targets=list(row.virtual_targets or []),
            meta=meta,
        )
        cases.append(
            ReplayCase(
                signal_id=row.signal_id,
                version=by_id[row.strategy_version_id],
                market=MarketRow(
                    id=row.market_id,
                    symbol=row.symbol,
                    exchange=row.code,
                    is_monitored=bool(row.is_monitored),
                    status=MarketStatus(row.status),
                ),
                source_bar_close=ensure_utc(
                    datetime.fromisoformat(meta["entry_plan"]["source_bar_close"])
                ),
                plan=tracking.plan,
                targets=_targets(row.virtual_targets),
                atr0=_atr0(dict(row.supporting_features or {})),
                stored=_stored(row, meta),
            )
        )
    return cases


def input_digest(cases: Sequence[ReplayCase]) -> str:
    """A stable fingerprint of exactly which records this run read.

    The Lab keeps writing, so "the same database" is not a stable phrase. Two
    runs that produce the same digest read the same rows, and their numbers are
    comparable; two that do not, are not (Astra, R1 diff review)."""
    payload = [
        [
            str(case.signal_id),
            case.stored.tracking_state.value,
            case.stored.result.value,
            None if case.stored.exit_ts is None else case.stored.exit_ts.isoformat(),
            None if case.stored.r_multiple is None else format(case.stored.r_multiple, "f"),
        ]
        for case in sorted(cases, key=lambda c: str(c.signal_id))
    ]
    return hashlib.sha256(canonical_json(payload)).hexdigest()
