"""T4.74-3 — ``spot_repo``/``spot_repo_positions`` against a recording fake
session: one statement per call, parameters bound by name, the predicates the
design §2/§4/§5/§8 name, and ``Decimal`` arithmetic at the close."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest

from hunter_meme_executor import spot_repo

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 19, 15, 0, tzinfo=UTC)
MINT = "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"
SIGNAL = "01996e2a-0000-7000-8000-000000000001"


class _Result:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> _Result:
        return self

    def first(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def one(self) -> dict[str, Any]:
        return self._rows[0]

    def scalar(self) -> Any:
        return next(iter(self._rows[0].values())) if self._rows else None

    def __iter__(self) -> Any:
        return iter(self._rows)


@dataclass
class FakeSession:
    """Records every statement with its parameters; answers what the test set."""

    rows: list[dict[str, Any]] = field(default_factory=lambda: list[dict[str, Any]]())
    calls: list[tuple[str, dict[str, Any] | None]] = field(
        default_factory=lambda: list[tuple[str, dict[str, Any] | None]]()
    )

    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> _Result:
        self.calls.append((str(statement), params))
        return _Result(self.rows)


def _only(session: FakeSession) -> tuple[str, dict[str, Any]]:
    assert len(session.calls) == 1, "one statement per call"
    sql, params = session.calls[0]
    return sql, params or {}


def _session(rows: list[dict[str, Any]] | None = None) -> tuple[FakeSession, Any]:
    fake = FakeSession(rows=rows or [])
    return fake, cast(Any, fake)


def candidate_row() -> dict[str, Any]:
    return {
        "id": SIGNAL,
        "market_id": "01996e2a-0000-7000-8000-00000000000a",
        "market_symbol": "UNIUSDT",
        "exchange_id": "01996e2a-0000-7000-8000-00000000000e",
        "market_type": "perpetual",
        "emitted_at": NOW - timedelta(seconds=30),
        "expires_at": NOW + timedelta(hours=4),
        "reference_price": "7.5",
        "stop": Decimal("7.3875"),
        "target1": "7.66875",
        "expected_holding_s": 14_400,
        "mint": MINT,
        "units_per_binance_unit": Decimal(1),
        "decimals": 8,
        "kind": "ponte",
        "tier": "A",
    }


def position_row() -> dict[str, Any]:
    return {
        "id": "p1",
        "signal_id": SIGNAL,
        "market_symbol": "UNIUSDT",
        "mint": MINT,
        "entry_at": NOW - timedelta(minutes=5),
        "tokens": 660_000_000,
        "sol_spent_lamports": 50_000_000,
        "initial_risk_sol": Decimal("0.00075"),
        "params": {"stop_frac": "0.015", "target_frac": "0.0225", "horizon_s": 14400},
        "ata_rent_lamports": 2_039_280,
        "mark_sol": Decimal("0.0505"),
        "high_water_sol": Decimal("0.0506"),
        "exit_intent": None,
        "sell_requested_at": None,
        "sell_requested_by": None,
    }


PREDICATES = (
    "FROM agent_signals s",
    "JOIN strategy_versions v ON v.id = s.strategy_version_id",
    "JOIN strategies st ON st.id = v.strategy_id",
    "JOIN markets m ON m.id = s.market_id",
    "JOIN exchanges e ON e.id = m.exchange_id AND e.code = 'binance'",
    "JOIN spot_desk_markets d ON d.binance_symbol = m.symbol AND d.enabled",
    "LEFT JOIN signal_outcomes o ON o.signal_id = s.id",
    "st.key = 'mean_reversion'",
    "v.version = :version",
    "s.direction = 'long'",
    "s.status = 'active'",
    "s.emitted_at >= :since AND s.emitted_at <= :now",
    "s.expires_at > :now",
    "NOT EXISTS (SELECT 1 FROM spot_orders so WHERE so.signal_id = s.id AND so.side = 'buy')",
    "o.meta->>'reference_price'",
    "jsonb_array_elements(s.supporting_features->'features')",
    "f->>'name' = 'close_15m'",
    "ORDER BY s.emitted_at DESC",
    "LIMIT :limit",
)


async def test_candidate_signals_is_the_design_s_query() -> None:
    fake, session = _session([candidate_row()])
    got = await spot_repo.candidate_signals(session, version="v14", max_age_s=180, now=NOW, limit=5)
    sql, params = _only(fake)
    for predicate in PREDICATES:
        assert predicate in sql, predicate
    assert params == {
        "version": "v14",
        "since": NOW - timedelta(seconds=180),
        "now": NOW,
        "limit": 5,
    }
    [c] = got
    assert (c.signal_id, c.market_symbol, c.mint, c.decimals) == (SIGNAL, "UNIUSDT", MINT, 8)
    assert c.reference_price == Decimal("7.5") and c.stop == Decimal("7.3875")
    assert c.target1 == Decimal("7.66875") and c.units_per_binance_unit == Decimal(1)
    assert isinstance(c.reference_price, Decimal) and c.expected_holding_s == 14_400


async def test_insert_order_binds_every_column_and_is_idempotent_by_key() -> None:
    fake, session = _session([{"id": "x"}])
    order_id = await spot_repo.insert_order(
        session,
        signal_id=SIGNAL,
        market_symbol="UNIUSDT",
        mint=MINT,
        side="buy",
        client_order_id=f"spot:{SIGNAL}:buy:1",
        attempt=1,
        status="admitted",
        reason=None,
        intent={"lane": "spot", "max_sol_cost_sol": "0.05"},
        admission={"decided_by": "executor:spot1_auto"},
        quote={"outAmount": "1"},
        now=NOW,
    )
    sql, params = _only(fake)
    assert order_id is not None and params["id"] == order_id
    assert "INSERT INTO spot_orders" in sql and "ON CONFLICT (client_order_id) DO NOTHING" in sql
    assert params["position_id"] is None and json.loads(params["intent"])["lane"] == "spot"
    assert params["side"] == "buy" and params["status"] == "admitted"
    empty, session = _session([])
    sell = await spot_repo.insert_order(
        session, signal_id=SIGNAL, market_symbol="UNIUSDT", mint=MINT, side="sell",
        client_order_id="k", attempt=2, status="refused", reason="x", intent={}, admission={},
        quote=None, position_id="p1", now=NOW,
    )  # fmt: skip
    assert sell is None and _only(empty)[1]["position_id"] == "p1"


@pytest.mark.parametrize(
    "step,kwargs,status,keys",
    [
        ("mark_simulated", {}, "simulated", ()),
        ("mark_submitted", {"signature": "9" * 88, "last_valid_block_height": 7}, "submitted_unconfirmed", ("signature",)),
        ("mark_confirmed", {"fill": {"sol_delta_lamports": -50_000_000}}, "confirmed", ("fill",)),
        ("mark_failed", {"reason": "simulation_token_short"}, "failed", ("reason",)),
        ("mark_refused", {"reason": "priority_fee_above_cap"}, "refused", ("reason",)),
    ],
)  # fmt: skip
async def test_each_mark_is_one_update_that_names_its_status(
    step: str, kwargs: dict[str, Any], status: str, keys: tuple[str, ...]
) -> None:
    fake, session = _session([{"id": "o1"}])
    assert await getattr(spot_repo, step)(session, "o1", now=NOW, **kwargs) is True
    sql, params = _only(fake)
    assert sql.startswith("UPDATE spot_orders SET status = ") and f"'{status}'" in sql
    assert params["id"] == "o1" and params["now"] == NOW
    for key in keys:
        assert key in params


async def test_positions_insert_read_mark_and_close_with_the_signal_s_r() -> None:
    fake, session = _session([{"id": "p1"}])
    pid = await spot_repo.insert_position(
        session, signal_id=SIGNAL, entry_order_id="o1", market_symbol="UNIUSDT", mint=MINT,
        entry_at=NOW, entry={"signature": "9" * 88}, tokens=660_000_000,
        sol_spent_lamports=50_000_000, initial_risk_sol=Decimal("0.00075"),
        params={"lane": "spot"}, ata_rent_lamports=2_039_280, now=NOW,
    )  # fmt: skip
    sql, params = _only(fake)
    assert pid is not None and "INSERT INTO spot_positions" in sql
    assert "ON CONFLICT (signal_id) DO NOTHING" in sql and params["risk"] == Decimal("0.00075")
    fake, session = _session([position_row()])
    [p] = await spot_repo.open_spot_positions(session)
    assert "status = 'open'" in _only(fake)[0] and p.market_symbol == "UNIUSDT"
    assert p.mark_sol == Decimal("0.0505") and p.initial_risk_sol == Decimal("0.00075")
    fake, session = _session()
    await spot_repo.set_mark(session, "p1", mark_sol=Decimal("0.051"), reason=None, now=NOW)
    sql, params = _only(fake)
    assert "mark_source = 'jupiter_quote'" in sql and params["mark"] == Decimal("0.051")
    fake, session = _session()
    await spot_repo.set_mark(session, "p1", mark_sol=None, reason="quote_failed:timeout", now=NOW)
    sql, params = _only(fake)
    assert "mark_sol" not in sql and "mark_at" not in sql, "the old mark stays (design §4)"
    assert sql.startswith("UPDATE spot_positions SET mark_reason = :reason")
    assert params["reason"] == "quote_failed:timeout"
    fake, session = _session([{"id": "p1"}])
    closed = await spot_repo.close_position(
        session, "p1", exit_order_id="o2", exit_at=NOW, exit_payload={"reason": "target"},
        sol_received_lamports=50_600_000, sol_spent_lamports=50_000_000,
        initial_risk_sol=Decimal("0.00075"), now=NOW,
    )  # fmt: skip
    sql, params = _only(fake)
    assert closed is True and "status = 'closed'" in sql
    assert params["pnl"] == Decimal("0.0006") and params["r"] == Decimal("0.8")


async def test_closed_stats_counts_the_streak_of_stops_from_the_latest_exit() -> None:
    row = {
        "n": 4,
        "sum_pnl_sol": Decimal("-0.0012"),
        "sum_r_net": Decimal("-1.6"),
        "recent_reasons": ["stop", "stop", "target", "stop"],
        "last_exit_at": NOW,
    }
    fake, session = _session([row])
    stats = await spot_repo.closed_stats(session, since=NOW - timedelta(days=30))
    sql, params = _only(fake)
    assert "status = 'closed'" in sql and "exit_at >= :since" in sql
    assert params["since"] == NOW - timedelta(days=30)
    assert (stats.n, stats.sum_pnl_sol, stats.sum_r_net) == (4, Decimal("-0.0012"), Decimal("-1.6"))
    assert stats.expectancy_r_net == Decimal("-0.4") and stats.consecutive_stops == 2
    none = {"n": 0, "sum_pnl_sol": 0, "sum_r_net": 0, "recent_reasons": None, "last_exit_at": None}
    _, session = _session([none])
    empty = await spot_repo.closed_stats(session, since=NOW)
    assert empty.expectancy_r_net is None and empty.consecutive_stops == 0 and empty.n == 0


async def test_market_decimals_are_read_once_and_written_back_only_when_null() -> None:
    fake, session = _session([{"decimals": None}])
    assert await spot_repo.market_decimals(session, "UNIUSDT") is None
    assert "FROM spot_desk_markets WHERE binance_symbol = :symbol" in _only(fake)[0]
    fake, session = _session([{"binance_symbol": "UNIUSDT"}])
    assert await spot_repo.set_market_decimals(session, "UNIUSDT", 8, now=NOW) is True
    sql, params = _only(fake)
    assert "decimals IS NULL" in sql and params["decimals"] == 8
    assert "updated_by = 'executor:spot1'" in sql


async def test_pending_spot_markets_reads_buys_in_flight_with_their_reservation() -> None:
    rows: list[dict[str, Any]] = [
        {"signal_id": SIGNAL, "market_symbol": "UNIUSDT", "mint": MINT, "intent": {"max_sol_cost_sol": "0.05"}},
        {"signal_id": "s2", "market_symbol": "WIFUSDT", "mint": MINT, "intent": {}},
    ]  # fmt: skip
    fake, session = _session(rows)
    got = await spot_repo.pending_spot_markets(session)
    sql, _ = _only(fake)
    assert "side = 'buy'" in sql
    assert "status IN ('admitted', 'simulated', 'submitted_unconfirmed')" in sql
    assert [(p.market_symbol, p.reserved_sol) for p in got] == [("UNIUSDT", Decimal("0.05"))]
