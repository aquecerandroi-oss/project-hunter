"""T4.74-5 — the ``spot1`` field of ``hb:meme:executor`` (design §7) and the
brake it rides: with ``SPOT1_ENABLED=false`` the mode is ``inert:disabled``
and ``spot1_fields`` makes no query and no quote; the open positions publish
R now, age and staleness; ``refused_by_reason`` is the top 8; ``refuted`` /
``cooldown`` replace ``on``; and an open spot position moves ``equity_sol``
and ``daily_loss_sol`` of the whole heartbeat (one brake, design §3)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest

from hunter_core.domain.enums import KillSwitchState
from hunter_meme_executor import heartbeat
from hunter_meme_executor.config import ExecutorConfig
from hunter_meme_executor.context import ExecutorState
from hunter_meme_executor.event_exits_stats import EventExitsStats
from hunter_meme_executor.kill_switch import DayAnchor
from hunter_meme_executor.launch_stats import LaunchStats
from hunter_meme_executor.spot_brake import as_brake_position
from hunter_meme_executor.spot_config import SpotConfig
from hunter_meme_executor.spot_exit_rules import LaneState
from hunter_meme_executor.spot_heartbeat import spot1_fields
from hunter_meme_executor.spot_repo import ClosedStats
from hunter_meme_executor.spot_stats import SpotStats
from hunter_risk_meme import MEME_PAPER_V0

from .spot_entries_rig import FakeInflow
from .spot_exits_rig import POSITION_ID, position

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 19, 15, 0, 1, tzinfo=UTC)
DAY_START = datetime(2026, 9, 19, 3, 0, tzinfo=UTC)
ON = SpotConfig(requested=True, live=True, signer_present=True)
OFF = SpotConfig()


@dataclass
class FakeKill:
    effective: KillSwitchState = KillSwitchState.ACTIVE
    anchor: DayAnchor | None = field(
        default_factory=lambda: DayAnchor(DAY_START, Decimal("0.5"), Decimal("0.5"), NOW)
    )

    def describe(self) -> dict[str, str]:
        return {"kill_switch": self.effective.value}


@dataclass
class FakeMode:
    gates: Any = None
    live: bool = False


class NoJupiter:
    def quote(self, **kwargs: Any) -> Any:
        raise AssertionError("no quote from the heartbeat")


@dataclass
class Ctx:
    config: ExecutorConfig
    state: ExecutorState = field(default_factory=ExecutorState)
    spot: SpotStats = field(default_factory=SpotStats)
    kill: FakeKill = field(default_factory=FakeKill)
    mode: FakeMode = field(default_factory=FakeMode)
    treasury_inflow: FakeInflow = field(default_factory=FakeInflow)
    event_exits: EventExitsStats = field(default_factory=EventExitsStats)
    launch: LaunchStats = field(default_factory=LaunchStats)
    treasury_client: NoJupiter = field(default_factory=NoJupiter)
    signer: Any = None
    priority_fees: Any = None
    session_factory: Any = None


def _config(spot: SpotConfig = OFF) -> ExecutorConfig:
    return ExecutorConfig(
        live=False,
        cluster="mainnet",
        rpc_url="http://rpc",
        limits=MEME_PAPER_V0,
        system_kill_switch=KillSwitchState.ACTIVE,
        kill_file=None,
        spot=spot,
    )


def _ctx(spot: SpotConfig = OFF) -> Any:
    def no_session(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("no query from spot1_fields")

    return Ctx(config=_config(spot), session_factory=no_session)


# ------------------------------------------------------------- spot1_fields
@pytest.mark.parametrize(
    "spot,expected",
    [
        (SpotConfig(), "inert:disabled"),
        (SpotConfig(requested=True), "inert:meme_live_disabled"),
        (SpotConfig(requested=True, live=True), "inert:signer_missing"),
        (ON, "on"),
    ],
)
def test_the_mode_names_why_the_lane_is_inert(spot: SpotConfig, expected: str) -> None:
    ctx = _ctx(spot)
    fields = spot1_fields(ctx, spot, NOW)
    assert fields["mode"] == expected
    assert fields["open"] == [] and fields["markets_enabled"] is None
    assert fields["closed"]["n"] == 0 and fields["refutation"]["state"] == "unknown"
    json.dumps(fields)  # Decimals are strings, every value serialisable


def test_refuted_and_cooldown_replace_on_but_never_an_inert_reason() -> None:
    ctx = _ctx(ON)
    ctx.spot.lane = LaneState("refuted", "n=20 expectancy_r_net=-0.1<=0", "spot1_refuted")
    ctx.spot.closed = ClosedStats(20, Decimal("-0.05"), Decimal("-2"), Decimal("-0.1"), 1, NOW)
    fields = spot1_fields(ctx, ON, NOW)
    assert fields["mode"] == "refuted" and fields["lane_reason"] == "n=20 expectancy_r_net=-0.1<=0"
    assert fields["closed"] == {
        "n": 20,
        "sum_r_gross": None,
        "sum_r_net": "-2",
        "sum_pnl_sol": "-0.05",
        "expectancy_r_net": "-0.1",
        "consecutive_stops": 1,
        "last_exit_at": NOW.isoformat(),
    }
    assert fields["refutation"]["trades"] == 20 and fields["refutation"]["threshold"] == 20
    ctx.spot.lane = LaneState("cooldown", "consecutive_stops=3", "spot1_cooldown", NOW)
    assert spot1_fields(ctx, ON, NOW)["mode"] == "cooldown"
    inert = _ctx(SpotConfig())
    inert.spot.lane = ctx.spot.lane
    assert spot1_fields(inert, SpotConfig(), NOW)["mode"] == "inert:disabled"


def test_open_positions_publish_r_now_age_and_staleness() -> None:
    ctx = _ctx(ON)
    ctx.spot.mark_failures[POSITION_ID] = 3
    ctx.spot.mark_ok_at[POSITION_ID] = NOW - timedelta(seconds=61)
    ctx.spot.blocked_exits[POSITION_ID] = "stop"
    p = as_brake_position(position(entry_at=NOW - timedelta(seconds=300)))
    fields = spot1_fields(ctx, ON, NOW, positions=[p], markets_enabled=40)
    (row,) = fields["open"]
    assert row["market"] == "UNIUSDT" and row["mint8"] == "EKpQGSJt"
    assert row["sol_spent"] == "0.05" and row["mark_sol"] == "0.0505"
    assert row["r_now"] == "0.667", "(0,0505 − 0,05) ÷ 0,00075"
    assert row["age_s"] == 300 and row["horizon_s"] == 14400
    assert row["mark_stale"] is True and row["mark_stale_s"] == 61 and row["mark_failures"] == 3
    assert row["blocked"] is True and row["exit_pending"] is False
    assert fields["mark_stale_s"] == 61 and fields["blocked_exits"] == {POSITION_ID: "stop"}
    assert fields["markets_enabled"] == 40
    assert fields["ticket_sol"] == "0.05", "min(SPOT1_TICKET_SOL, max_sol_per_trade)"


def test_refusals_publish_the_top_eight_by_count_then_name() -> None:
    ctx = _ctx(ON)
    for name, n in [(f"r{i}", 10 - i) for i in range(10)]:
        for _ in range(n):
            ctx.spot.record_refusal(name)
    ctx.spot.record_exit("target")
    ctx.spot.record_exit("stop")
    fields = spot1_fields(ctx, ON, NOW)
    assert list(fields["refused_by_reason"]) == [f"r{i}" for i in range(8)]
    assert fields["exits_by_reason"] == {"stop": 1, "target": 1}
    assert fields["last_refusal"] == "r9"


# ------------------------------------------------- the heartbeat, end to end
class _Session:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *_exc: object) -> None:
        return None


def _wire(monkeypatch: pytest.MonkeyPatch, positions: list[Any]) -> list[str]:
    queries: list[str] = []

    async def brake(_s: Any) -> list[Any]:
        queries.append("brake_positions")
        return list(positions)

    async def by_state(_s: Any) -> dict[str, int]:
        return {}

    async def zero(*_a: Any, **_k: Any) -> int:
        return 0

    async def empty(*_a: Any, **_k: Any) -> dict[str, int]:
        return {}

    async def markets(_s: Any) -> int:
        queries.append("enabled_market_count")
        return 40

    def session(*_a: Any, **_k: Any) -> _Session:
        return _Session()

    monkeypatch.setattr(heartbeat, "role_session", session)
    monkeypatch.setattr(heartbeat, "brake_positions", brake)
    monkeypatch.setattr(heartbeat, "orders_by_state", by_state)
    monkeypatch.setattr(heartbeat, "auto_approved_last_hour", zero)
    monkeypatch.setattr(heartbeat, "auto_refused_last_hour", empty)
    monkeypatch.setattr(heartbeat, "enabled_market_count", markets)
    monkeypatch.setattr(heartbeat, "utcnow", lambda: NOW)
    return queries


async def test_an_open_spot_position_moves_equity_and_daily_loss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spot = as_brake_position(position(mark_sol=Decimal("0.0505")))
    queries = _wire(monkeypatch, [spot])
    ctx = Ctx(config=_config(), session_factory=object())
    ctx.state.wallet_lamports = 400_000_000  # 0,40 SOL cash after the 0,05 buy
    ctx.state.wallet_read_at = NOW
    fields = await heartbeat.heartbeat_fields(cast(Any, ctx))
    assert fields["equity_sol"] == "0.4505", "cash + the spot mark"
    assert fields["daily_loss_sol"] == "0.0495", "day start 0,5 + inflow 0 − equity"
    assert fields["positions_open"] == "0", "memes only, as before"
    assert fields["spot1_positions_open"] == "1"
    spot1 = json.loads(fields["spot1"])
    assert spot1["mode"] == "inert:disabled" and spot1["markets_enabled"] is None
    assert spot1["open"][0]["r_now"] == "0.667"
    assert queries == ["brake_positions"], "inert: no other spot query"

    _wire(monkeypatch, [])
    without = await heartbeat.heartbeat_fields(cast(Any, Ctx(config=_config(), session_factory=1)))
    assert without["equity_sol"] == "" and without["spot1_positions_open"] == "0"


async def test_an_enabled_lane_publishes_the_market_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queries = _wire(monkeypatch, [])
    ctx = Ctx(config=_config(ON), session_factory=object())
    fields = await heartbeat.heartbeat_fields(cast(Any, ctx))
    assert json.loads(fields["spot1"])["markets_enabled"] == 40
    assert queries == ["brake_positions", "enabled_market_count"]
