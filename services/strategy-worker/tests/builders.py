"""Fixtures for the shadow integration tests: a market, an activated version,
and a 1-minute candle series that makes ``volume_anomaly_v1`` fire.

Everything here is labelled test data and lives only in tests (CLAUDE.md: no
fake data outside them). The series is built the way the strategy reads it —
288 quiet 5m bars and one bar with four times the volume closing above its own
midpoint — so the decision under test is a real decision of the real frozen
strategy, not a hand-written ``Decision`` that could drift from it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from hunter_core.db.models.agents import Strategy as StrategyRow
from hunter_core.db.models.agents import StrategyVersion
from hunter_core.db.models.market_data import Candle
from hunter_core.db.models.markets import Asset, Exchange, Market
from hunter_core.domain.enums import (
    MarketStatus,
    MarketType,
    StrategyVersionStatus,
    Timeframe,
)
from hunter_core.domain.types import utcnow, uuid7
from hunter_core.strategies.canonical import canonical_json
from hunter_core.strategies.registry import StrategyRegistry
from hunter_core.strategies.volume_anomaly_v1 import VOLUME_ANOMALY_V1
from hunter_strategy_worker.code_ref import version_code_ref
from hunter_strategy_worker.context_budget import WINDOWS
from hunter_strategy_worker.context_budget import declare as declare_context_windows

MINUTE = timedelta(minutes=1)
EXCHANGE = "binance"
SYMBOL = "BTCUSDT"
SERIES_MINUTES = 1600
"""Enough 1m history for the 289 5m bars *and* the 97 15m ATR bars."""

_RUNNING_CODE_REF = version_code_ref("volume_anomaly_v1")
"""The per-version digest of the code this process is running (every fixture
here carries the real ``volume_anomaly_v1`` contract): the worker refuses an
activated version whose frozen ``code_ref`` is anything else."""


@dataclass(frozen=True, slots=True)
class Fixture:
    """Ids of everything one integration test needs."""

    exchange_id: uuid.UUID
    market_id: uuid.UUID
    strategy_id: uuid.UUID
    version_id: uuid.UUID
    params: dict[str, Any]
    cut: datetime


def canonical_params() -> dict[str, Any]:
    """``default_parameters`` in the exact JSONB shape the activation writes."""
    import json

    parsed: dict[str, Any] = json.loads(canonical_json(dict(VOLUME_ANOMALY_V1.default_parameters)))
    return parsed


async def ensure_partitions(session: AsyncSession, around: datetime) -> None:
    """The monthly ``candles_1m`` partitions the series falls into.

    Must run as the *owner*, not as ``hunter_worker``: creating a partition is
    DDL, and the worker role deliberately has no ``CREATE`` on ``public``. In
    production this is ``infra/scripts/create_partitions.py``'s job.
    """
    months = {(around.year, around.month)}
    earlier = around - timedelta(days=40)
    months.add((earlier.year, earlier.month))
    later = around + timedelta(days=40)
    months.add((later.year, later.month))
    for year, month in sorted(months):
        start = datetime(year, month, 1, tzinfo=UTC)
        end = datetime(year + (month // 12), (month % 12) + 1, 1, tzinfo=UTC)
        name = f"candles_1m_{year}_{month:02d}"
        await session.execute(
            text(
                f"CREATE TABLE IF NOT EXISTS {name} PARTITION OF candles_1m "
                f"FOR VALUES FROM ('{start.isoformat()}') TO ('{end.isoformat()}')"
            )
        )


async def seed_market(
    session: AsyncSession,
    *,
    monitored: bool = True,
    symbol: str = SYMBOL,
    base_asset: str = "BTC",
) -> tuple[uuid.UUID, uuid.UUID]:
    """An exchange and one active, monitored perpetual.

    ``symbol``/``base_asset`` default to the single market every test before
    T3.52 used. A second one exists so that a gate scoped to ``btc`` can be shown
    gating a market that is **not** BTC (``test_regime_gate.py``)."""
    exchange_id = uuid7()
    await session.execute(
        text(
            "INSERT INTO exchanges (id, code, name, status) "
            "VALUES (:id, :code, :name, 'active') ON CONFLICT (code) DO NOTHING"
        ),
        {"id": exchange_id, "code": EXCHANGE, "name": "Binance"},
    )
    exchange_id = await session.scalar(
        text("SELECT id FROM exchanges WHERE code = :code"), {"code": EXCHANGE}
    )
    base, quote = uuid7(), uuid7()
    for asset_id, asset_symbol in ((base, base_asset), (quote, "USDT")):
        await session.execute(
            text(
                "INSERT INTO assets (id, symbol) VALUES (:id, :symbol) "
                "ON CONFLICT (symbol) DO NOTHING"
            ),
            {"id": asset_id, "symbol": asset_symbol},
        )
    market_id = uuid7()
    await session.execute(
        text(
            "INSERT INTO markets (id, exchange_id, symbol, market_type, status, "
            "is_monitored, monitor_rank, volume_24h_usd, last_seen_at) "
            "VALUES (:id, :exchange_id, :symbol, 'perpetual', 'active', :monitored, 1, "
            "1000000, now()) "
            "ON CONFLICT (exchange_id, symbol, market_type) DO NOTHING"
        ),
        {
            "id": market_id,
            "exchange_id": exchange_id,
            "symbol": symbol,
            "monitored": monitored,
        },
    )
    market_id = await session.scalar(
        text(
            "SELECT id FROM markets WHERE exchange_id = :exchange_id AND symbol = :symbol "
            "AND market_type = 'perpetual'"
        ),
        {"exchange_id": exchange_id, "symbol": symbol},
    )
    return exchange_id, market_id


async def activate_version(
    session: AsyncSession,
    *,
    key: str = "volume_anomaly",
    version: str = "v1",
    code_ref: str | None = _RUNNING_CODE_REF,
    active: bool = True,
    purpose: str = "research_only",
    policy: dict[str, Any] | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    """A ``strategy`` and an already-activated ``strategy_version``.

    Inserted activated rather than updated into activation: the freeze trigger
    fires on ``UPDATE``/``DELETE`` of an already-activated row, which is exactly
    what the ops script has to respect and what this fixture must not fight.

    ``0011_strategy_activation_owner`` (T3.15c) went further than the column and
    revoked ``INSERT`` on ``strategy_versions`` from ``hunter_worker`` outright
    — nothing that runs as the worker ever inserts here — so the whole
    statement below runs with the role reset to the session owner and
    ``SET LOCAL ROLE`` restored right after, the same path the ops script and
    ``paper_line.py`` actually take, not a grant the tests pretend the worker
    has. ``purpose`` is still named in the INSERT only when it is not the
    default, to keep the statement itself unchanged from before ``0011``.
    """
    strategy_id, version_id = uuid7(), uuid7()
    await session.execute(
        text(
            "INSERT INTO strategies (id, key, name) VALUES (:id, :key, :name) "
            "ON CONFLICT (key) DO NOTHING"
        ),
        {"id": strategy_id, "key": key, "name": key},
    )
    strategy_id = await session.scalar(
        text("SELECT id FROM strategies WHERE key = :key"), {"key": key}
    )
    existing = await session.scalar(
        text(
            "SELECT id FROM strategy_versions WHERE strategy_id = :strategy_id "
            "AND version = :version"
        ),
        {"strategy_id": strategy_id, "version": version},
    )
    if existing is not None:
        # Reused on purpose: the freeze trigger refuses to delete an activated
        # version (that is the point of it), so tests share one frozen row.
        return strategy_id, existing
    import json

    names_purpose = purpose != "research_only"
    params: dict[str, Any] = {
        "id": version_id,
        "strategy_id": strategy_id,
        "version": version,
        "status": (
            StrategyVersionStatus.ACTIVE.value if active else StrategyVersionStatus.DRAFT.value
        ),
        "schema": json.dumps(dict(VOLUME_ANOMALY_V1.parameters_schema)),
        "params": canonical_json(dict(VOLUME_ANOMALY_V1.default_parameters)).decode(),
        "code_ref": code_ref,
        "activated_at": utcnow() if active else None,
    }
    columns = [
        "id",
        "strategy_id",
        "version",
        "status",
        "parameters_schema",
        "default_parameters",
        "code_ref",
        "params_format",
        "activated_at",
    ]
    values = [
        ":id",
        ":strategy_id",
        ":version",
        ":status",
        "CAST(:schema AS jsonb)",
        "CAST(:params AS jsonb)",
        ":code_ref",
        "1",
        ":activated_at",
    ]
    if names_purpose:
        params["purpose"] = purpose
        columns.append("purpose")
        values.append(":purpose")
    if policy is not None:
        # T3.52: named only when there is one, so the statement of every test
        # written before 0017 is byte for byte the statement it always was — and
        # it has to be written *here*, at insert: the freeze trigger refuses to
        # UPDATE ``eligibility_policy`` on an activated row, which is the point.
        # ``json.dumps`` e não ``canonical_json``: a forma canônica emite número
        # como string (``params_format = 1``), e a janela de horas da T3.59 é de
        # inteiros — gravá-la por ali faria o roster recusar a versão inteira com
        # ``policy_unreadable``. É o mesmo JSON que ``variant.stored_policy``
        # grava em produção, e é por isso que este fixture prova o que ela grava.
        params["policy"] = json.dumps(policy, separators=(",", ":"), sort_keys=True)
        columns.append("eligibility_policy")
        values.append("CAST(:policy AS jsonb)")
    named = ", ".join(columns)
    placeholders = ", ".join(values)
    # Every fragment is a literal of this module; the values travel as bind
    # parameters exactly as they did before T3.52.
    statement = f"INSERT INTO strategy_versions ({named}) VALUES ({placeholders})"  # noqa: S608
    current_role = await session.scalar(text("SELECT current_user"))
    await session.execute(text("RESET ROLE"))
    await session.execute(text(statement), params)
    if current_role is not None:
        await session.execute(text(f"SET LOCAL ROLE {current_role}"))
    return strategy_id, version_id


async def seed_paper_exposure(
    session: AsyncSession, *, org: uuid.UUID, version_id: uuid.UUID, market_id: uuid.UUID
) -> None:
    """Org, workspace, portfolio, agent, a proposal, an order and one open
    position — the *real* production link (T3.39b review, ALTA-1), not a
    shortcut through a column production never writes.

    ``execution-worker/positions.py``'s ``open_position`` never sets
    ``positions.agent_id`` — read, not assumed, and left out of this fixture on
    purpose. What it *does* write is ``positions.metadata->>'proposal_id'``,
    the same value the entry order's ``proposal_id`` carries; the chain a
    ``--deprecate``/``--supersede`` guard has to walk is therefore
    ``positions.metadata->>'proposal_id' -> orders.proposal_id ->
    trade_proposals.agent_id -> agents.strategy_version_id`` — the same three
    tables ``ddl/paper.py``'s own consistency check joins. A guard seeded
    through ``positions.agent_id`` instead would pass every test and refuse
    nothing on the VPS.

    ``organizations``/``workspaces``/``portfolios``/``agents``/``trade_proposals``/
    ``orders`` are ``hunter_app``/engine territory, not ``hunter_worker``'s — the
    same reason ``activate_version`` resets the role for ``strategy_versions``.
    The role is *not* restored afterwards (unlike that helper): opening a
    ``portfolios`` row carries a deferred, COMMIT-time audit trigger
    (``paper_roles_2``'s birth guard) that reads ``current_user`` at commit, not
    at the ``INSERT`` — restoring ``hunter_worker`` here would make the session
    look, at commit, like "only the engine" opening a wallet with no
    ``audit_logs`` row in the same transaction, which is exactly what that
    trigger refuses. This helper is always the last write of its transaction.
    """
    import json

    workspace_id, portfolio_id, agent_id = uuid7(), uuid7(), uuid7()
    proposal_id, order_id, position_id = uuid7(), uuid7(), uuid7()
    await session.execute(text("RESET ROLE"))
    await session.execute(
        text("INSERT INTO organizations (id, slug, name) VALUES (:id, :slug, :slug)"),
        {"id": org, "slug": f"t-{org.hex[:8]}"},
    )
    await session.execute(
        text(
            "INSERT INTO workspaces (id, organization_id, name, objective) "
            "VALUES (:id, :org, 'w', 'paper_trading')"
        ),
        {"id": workspace_id, "org": org},
    )
    await session.execute(
        text(
            "INSERT INTO portfolios (id, organization_id, workspace_id, name, initial_capital) "
            "VALUES (:id, :org, :ws, 'paper wallet', 1000)"
        ),
        {"id": portfolio_id, "org": org, "ws": workspace_id},
    )
    await session.execute(
        text(
            "INSERT INTO agents (id, organization_id, workspace_id, portfolio_id, name, "
            "strategy_version_id, status) "
            "VALUES (:id, :org, :ws, :pf, 'agent', :version, 'enabled')"
        ),
        {"id": agent_id, "org": org, "ws": workspace_id, "pf": portfolio_id, "version": version_id},
    )
    await session.execute(
        text(
            "INSERT INTO trade_proposals (id, organization_id, portfolio_id, agent_id, "
            "market_id, direction, idempotency_key) VALUES "
            "(:id, :org, :pf, :agent, :market, 'long', :key)"
        ),
        {
            "id": proposal_id,
            "org": org,
            "pf": portfolio_id,
            "agent": agent_id,
            "market": market_id,
            "key": f"t39b-{proposal_id.hex[:16]}",
        },
    )
    await session.execute(
        text(
            "INSERT INTO orders (id, organization_id, portfolio_id, proposal_id, market_id, "
            "client_order_id, side, type, purpose, qty) VALUES "
            "(:id, :org, :pf, :proposal, :market, :coid, 'buy', 'market', 'entry', 1)"
        ),
        {
            "id": order_id,
            "org": org,
            "pf": portfolio_id,
            "proposal": proposal_id,
            "market": market_id,
            "coid": f"t39b-{order_id.hex[:16]}",
        },
    )
    await session.execute(
        text(
            "INSERT INTO positions (id, organization_id, portfolio_id, market_id, direction, "
            "qty, avg_entry_price, status, metadata) VALUES (:id, :org, :pf, :market, 'long', "
            "1, 100, 'open', CAST(:meta AS jsonb))"
        ),
        {
            "id": position_id,
            "org": org,
            "pf": portfolio_id,
            "market": market_id,
            "meta": json.dumps({"proposal_id": str(proposal_id)}),
        },
    )


async def seed_shadow_exposure(
    session: AsyncSession, *, version_id: uuid.UUID, market_id: uuid.UUID
) -> None:
    """A ``shadow_episodes`` slot still tracking an open outcome (T3.39b review,
    BAIXA-7): the *other* half of the paper guard, independent of any wallet —
    a research row with a signal in flight. Worker territory (unlike
    ``seed_paper_exposure``'s onboarding tables): the shadow lab writes
    ``agent_signals``/``signal_outcomes``/``shadow_episodes`` itself, so no role
    reset is needed here.
    """
    signal_id, episode_id = uuid7(), uuid7()
    await session.execute(
        text(
            "INSERT INTO agent_signals (id, strategy_version_id, market_id, params_hash, "
            "direction, confidence) VALUES (:id, :version, :market, 'test', 'long', 0.5)"
        ),
        {"id": signal_id, "version": version_id, "market": market_id},
    )
    await session.execute(
        text("INSERT INTO signal_outcomes (signal_id) VALUES (:id)"), {"id": signal_id}
    )
    await session.execute(
        text(
            "INSERT INTO shadow_episodes (id, strategy_version_id, market_id, cohort, "
            "episode_id, last_bar_close, open_outcome_signal_id) VALUES "
            "(:id, :version, :market, 'prospective', :episode, now(), :signal)"
        ),
        {
            "id": uuid7(),
            "version": version_id,
            "market": market_id,
            "episode": episode_id,
            "signal": signal_id,
        },
    )


class NamedStrategy:
    """A registry entry under a test-only key, carrying the real v1 contract.

    Labelled test data (CLAUDE.md): the registry is keyed by
    ``strategies.key + "_" + version``, and every real key is a frozen row that
    the migration's trigger will not let a later test delete. Giving each
    scenario its own key is what keeps them independent; the *schema*, the
    *parameters* and the *module* are the genuine frozen ones, so what is being
    validated is real — in particular ``__module__``, because that is the name
    the per-version ``code_ref`` carries and the name a superseded row is bound
    back to code by.
    """

    __module__ = "hunter_core.strategies.volume_anomaly_v1"

    def __init__(self, key: str) -> None:
        self.key = key
        self.version = "v1"
        self.timeframe = VOLUME_ANOMALY_V1.timeframe
        self.parameters_schema = VOLUME_ANOMALY_V1.parameters_schema
        self.default_parameters = VOLUME_ANOMALY_V1.default_parameters
        # T3.54c: this throwaway key carries the real volume_anomaly_v1
        # contract, so it needs that contract's real context windows — the
        # activation-time budget check (context_budget.py) refuses a strategy
        # it cannot size, and a synthetic key is never in the frozen WINDOWS
        # table by construction.
        declare_context_windows(
            self.key, self.version, WINDOWS[(VOLUME_ANOMALY_V1.key, VOLUME_ANOMALY_V1.version)]
        )

    def evaluate(self, ctx: Any, params: Any) -> Any:
        return VOLUME_ANOMALY_V1.evaluate(ctx, params)

    def explain(self, ctx: Any, params: Any) -> Any:
        return VOLUME_ANOMALY_V1.explain(ctx, params)


def registry_for(db_key: str) -> StrategyRegistry:
    """A one-entry registry binding ``<db_key>_v1`` to the real v1 contract."""
    return StrategyRegistry([NamedStrategy(f"{db_key}_v1")])


def series(cut: datetime, *, trigger: bool = True) -> list[dict[str, Any]]:
    """``SERIES_MINUTES`` quiet 1m candles ending at ``cut``, optionally with a
    volume anomaly in the last five minutes."""
    rows: list[dict[str, Any]] = []
    for index in range(SERIES_MINUTES):
        open_time = cut - MINUTE * (SERIES_MINUTES - index)
        spike = trigger and index >= SERIES_MINUTES - 5
        rows.append(
            {
                "open_time": open_time,
                "open": Decimal("100"),
                "high": Decimal("100.4") if spike else Decimal("100.2"),
                "low": Decimal("100.0") if spike else Decimal("99.8"),
                "close": Decimal("100.3") if spike else Decimal("100"),
                "volume": Decimal("60") if spike else Decimal("10"),
            }
        )
    return rows


async def insert_candles(
    session: AsyncSession,
    market_id: uuid.UUID,
    rows: list[dict[str, Any]],
    *,
    skip: set[datetime] | None = None,
) -> None:
    """Persist 1m candles, optionally leaving holes (``skip``) for gap tests."""
    skip = skip or set()
    for row in rows:
        if row["open_time"] in skip:
            continue
        session.add(
            Candle(
                market_id=market_id,
                timeframe=Timeframe.M1,
                open_time=row["open_time"],
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
                is_final=True,
                source="test",
            )
        )
    await session.flush()


__all__ = [
    "EXCHANGE",
    "MINUTE",
    "SERIES_MINUTES",
    "SYMBOL",
    "Asset",
    "Exchange",
    "Fixture",
    "Market",
    "MarketStatus",
    "MarketType",
    "StrategyRow",
    "StrategyVersion",
    "activate_version",
    "canonical_params",
    "ensure_partitions",
    "NamedStrategy",
    "insert_candles",
    "insert_funding_rate",
    "insert_open_interest",
    "insert_regime",
    "isolate_catalogue",
    "only_version",
    "register_gap",
    "registry_for",
    "seed_market",
    "seed_paper_exposure",
    "seed_shadow_exposure",
    "series",
]


def only_version(versions: list[Any], key: str = "volume_anomaly") -> Any:
    """The one active version under ``key``.

    Tests share one database and one catalogue, so ``versions[0]`` silently
    depends on which other test activated something first. Naming the version
    keeps each scenario independent of the file order.
    """
    matching = [v for v in versions if v.strategy_key == key]
    assert len(matching) == 1, (
        f"expected one {key} version, got {[v.strategy_key for v in versions]}"
    )
    return matching[0]


async def register_gap(
    session: AsyncSession,
    market_id: uuid.UUID,
    *,
    start: datetime,
    end: datetime,
    status: str = "open",
    detected_at: datetime | None = None,
) -> None:
    """An ``ingestion_gaps`` row like the market-worker's detector writes."""
    await session.execute(
        text(
            "INSERT INTO ingestion_gaps (id, market_id, timeframe, gap_start, gap_end, "
            "status, attempts, detected_at) VALUES (:id, :market_id, '1m', :start, :end, "
            ":status, 0, :detected_at)"
        ),
        {
            "id": uuid7(),
            "market_id": market_id,
            "start": start,
            "end": end,
            "status": status,
            "detected_at": detected_at or utcnow(),
        },
    )


async def insert_funding_rate(
    session: AsyncSession,
    market_id: uuid.UUID,
    *,
    funding_time: datetime,
    rate: Decimal,
    mark_price: Decimal | None,
) -> None:
    """One durable ``funding_rates`` settlement row."""
    await session.execute(
        text(
            "INSERT INTO funding_rates (market_id, funding_time, rate, mark_price) "
            "VALUES (:market_id, :funding_time, :rate, :mark_price)"
        ),
        {
            "market_id": market_id,
            "funding_time": funding_time,
            "rate": rate,
            "mark_price": mark_price,
        },
    )
    await session.flush()


async def insert_open_interest(
    session: AsyncSession,
    market_id: uuid.UUID,
    *,
    ts: datetime,
    open_interest: Decimal | None,
    open_interest_value: Decimal | None = None,
) -> None:
    """One durable ``open_interest_history`` sample row."""
    await session.execute(
        text(
            "INSERT INTO open_interest_history (market_id, ts, open_interest, open_interest_value) "
            "VALUES (:market_id, :ts, :open_interest, :open_interest_value)"
        ),
        {
            "market_id": market_id,
            "ts": ts,
            "open_interest": open_interest,
            "open_interest_value": open_interest_value,
        },
    )
    await session.flush()


async def insert_regime(
    session: AsyncSession,
    *,
    start_time: datetime,
    end_time: datetime | None = None,
    regime: str = "SIDEWAYS",
    scope: str = "global",
    classifier_version: str | None = None,
) -> uuid.UUID:
    """One ``market_regimes`` row, like ``hunter_scanner_worker.writers.write_regime``."""
    regime_id = uuid7()
    await session.execute(
        text(
            "INSERT INTO market_regimes (id, scope, regime, start_time, end_time, "
            "classifier_version) "
            "VALUES (:id, :scope, :regime, :start_time, :end_time, :classifier_version)"
        ),
        {
            "id": regime_id,
            "scope": scope,
            "regime": regime,
            "start_time": start_time,
            "end_time": end_time,
            "classifier_version": classifier_version,
        },
    )
    await session.flush()
    return regime_id


async def insert_hourly_regime(
    session: AsyncSession, *, hour: datetime, regime: str = "SIDEWAYS"
) -> uuid.UUID:
    """One row of the T3.43 hourly series: ``scope = 'btc'``,
    ``classifier_version = 'regime_hourly_v1'``, closed on ``[hour, hour + 1h)``.

    Exactly what ``hunter_scanner_worker.regime_writer`` writes, and the shape
    ``hunter_strategy_worker.regime_gate`` reads — a test that seeded an open
    interval, or the ``global`` scope, would be testing another series.
    """
    return await insert_regime(
        session,
        start_time=hour,
        end_time=hour + timedelta(hours=1),
        regime=regime,
        scope="btc",
        classifier_version="regime_hourly_v1",
    )


async def isolate_catalogue(session: AsyncSession, *, keep: str = "volume_anomaly") -> None:
    """Leave exactly one strategy key ``active`` in the shared catalogue.

    The tests share one database and the freeze trigger refuses to delete an
    activated version — on purpose — so every scenario that activates something
    leaves it behind for the next one. Scenarios that assert *how many* versions
    ran have to state which catalogue they expect instead of inheriting it.
    ``status`` is the one lifecycle field the trigger leaves mutable
    (DATABASE.md §16.1), which is exactly what makes this possible.

    Since ``0011_strategy_activation_owner`` the worker role cannot write
    ``status`` either (only the activation script, as the owner, may): this
    fixture switches to the session owner for its two statements and puts the
    role back, the same way ``activate_version`` does.
    """
    current_role = await session.scalar(text("SELECT current_user"))
    await session.execute(text("RESET ROLE"))
    await session.execute(
        text(
            "UPDATE strategy_versions v SET status = 'deprecated' FROM strategies s "
            "WHERE s.id = v.strategy_id AND v.status = 'active' AND s.key <> :keep"
        ),
        {"keep": keep},
    )
    await session.execute(
        text(
            "UPDATE strategy_versions v SET status = 'active' FROM strategies s "
            "WHERE s.id = v.strategy_id AND s.key = :keep AND v.activated_at IS NOT NULL"
        ),
        {"keep": keep},
    )
    await session.execute(text(f"SET LOCAL ROLE {current_role}"))
