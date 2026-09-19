"""T4.74-3 — the ``spot/1`` lane's foundations, with fakes only: the ``SPOT1_*``
table (defaults, percent -> fraction, nothing enabled without live + signer),
the parity and geometry arithmetic in ``Decimal`` with a reason for every
missing number, and the brake mapping (a spot position is a position of
``lane = spot`` in the same wallet). The repository's SQL shape is in
``test_spot_repo.py``."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest
from structlog.testing import capture_logs

from hunter_meme_executor import spot_brake, spot_repo, spot_signals
from hunter_meme_executor.repo_positions import OpenPosition
from hunter_meme_executor.spot_config import SpotConfig
from hunter_risk_meme import MEME_PAPER_V0
from hunter_risk_meme.spot_profile import SPOT_LANE

from .test_spot_repo import MINT, NOW, SIGNAL, FakeSession, candidate_row, position_row

pytestmark = pytest.mark.unit

LIVE = {"ENABLE_MEME_LIVE_TRADING": "true", "SPOT1_ENABLED": "true"}
PARITY: dict[str, Any] = {
    "ticket_sol": Decimal("0.05"),
    "sol_usd": Decimal("200"),
    "out_amount_atoms": 12_345_678,
    "decimals": 6,
    "units_per_binance_unit": Decimal(1),
    "bin_usd": Decimal("0.80"),
}
GEOMETRY: dict[str, Any] = {
    "reference_price": Decimal("100"),
    "stop": Decimal("98.5"),
    "target1": Decimal("102.25"),
    "expected_holding_s": 14_400,
    "max_hold_s": 14_400,
}


# ------------------------------------------------------------------ config
def test_the_defaults_are_the_design_s_table_and_nothing_is_enabled() -> None:
    cfg = SpotConfig.from_env({})
    assert cfg.enabled is False and cfg.inert_reason == "disabled"
    assert cfg.strategy_version == "v14"
    assert (cfg.ticket_sol, cfg.max_open) == (Decimal("0.05"), 3)
    assert (cfg.max_signal_age_s, cfg.max_hold_s) == (180, 14_400)
    assert cfg.max_parity_pct == Decimal("0.03"), "3 % as a fraction, like MemeLimits"
    assert cfg.max_impact_pct == Decimal("0.005") and cfg.max_cost_r == Decimal("0.5")
    assert (cfg.mark_s, cfg.exit_slippage_bps, cfg.panic_slippage_bps) == (20, 50, 300)
    assert cfg.priority_fee_max_lamports == 100_000
    assert (cfg.refute_min_trades, cfg.refute_max_loss_sol) == (20, Decimal("0.15"))
    assert cfg.consecutive_stops_pause_s == 7_200 and cfg.refutation_reset_at is None
    assert cfg.as_json()["mode"] == "inert:disabled"


def test_enabled_needs_the_flag_the_live_switch_and_a_signer() -> None:
    assert SpotConfig.from_env({"SPOT1_ENABLED": "true"}).inert_reason == "meme_live_disabled"
    assert SpotConfig.from_env(LIVE).inert_reason == "signer_missing"
    assert SpotConfig.from_env({"ENABLE_MEME_LIVE_TRADING": "true"}).inert_reason == "disabled"
    on = SpotConfig.from_env(LIVE, signer_present=True)
    assert on.enabled is True and on.inert_reason is None and on.as_json()["mode"] == "on"


def test_percents_become_fractions_and_reach_the_profile() -> None:
    cfg = SpotConfig.from_env({"SPOT1_MAX_PARITY_PCT": "2", "SPOT1_MAX_IMPACT_PCT": "0.25"})
    assert cfg.max_parity_pct == Decimal("0.02") and cfg.max_impact_pct == Decimal("0.0025")
    profile = cfg.profile(MEME_PAPER_V0)
    assert (profile.max_parity_pct, profile.max_impact_pct) == (Decimal("0.02"), Decimal("0.0025"))
    limits = MEME_PAPER_V0.model_copy(update={"max_sol_per_trade": Decimal("0.02")})
    assert cfg.ticket(limits) == Decimal("0.02") == cfg.profile(limits).ticket_sol
    assert cfg.as_json(limits)["ticket_sol"] == "0.02"


@pytest.mark.parametrize(
    "variable,value",
    [
        ("SPOT1_TICKET_SOL", "abc"),
        ("SPOT1_TICKET_SOL", "0"),
        ("SPOT1_MAX_OPEN", "0"),
        ("SPOT1_MAX_PARITY_PCT", "150"),
        ("SPOT1_PRIORITY_FEE_MAX_LAMPORTS", "-5"),
        ("SPOT1_MAX_COST_R", "NaN"),
        ("SPOT1_STRATEGY_VERSION", "v14; drop"),
        ("SPOT1_REFUTATION_RESET_AT", "2026-09-19T10:00:00"),
        ("SPOT1_REFUTATION_RESET_AT", "yesterday"),
    ],
)
def test_out_of_range_falls_back_to_the_default_with_a_warning(variable: str, value: str) -> None:
    with capture_logs() as logs:
        cfg = SpotConfig.from_env({variable: value})
    assert cfg == SpotConfig()
    assert [e["variable"] for e in logs if e["event"] == "meme_spot_config_invalid"] == [variable]


def test_values_in_range_are_read_as_written() -> None:
    cfg = SpotConfig.from_env(
        {
            "SPOT1_STRATEGY_VERSION": "v7",
            "SPOT1_TICKET_SOL": "0.15",
            "SPOT1_MAX_OPEN": "1",
            "SPOT1_PRIORITY_FEE_MAX_LAMPORTS": "50000",
            "SPOT1_REFUTATION_RESET_AT": "2026-09-20T12:00:00Z",
        }
    )
    assert (cfg.strategy_version, cfg.ticket_sol, cfg.max_open) == ("v7", Decimal("0.15"), 1)
    assert cfg.priority_fee_max_lamports == 50_000
    assert cfg.refutation_reset_at == datetime(2026, 9, 20, 12, tzinfo=UTC)


# ------------------------------------------------------------------ signals
async def _close(age_s: int) -> spot_signals.FinalClose | None:
    fake = FakeSession(
        rows=[{"close": Decimal("7.5"), "open_time": NOW - timedelta(seconds=age_s)}]
    )
    got = await spot_signals.latest_final_close(
        cast(Any, fake), symbol="UNIUSDT", exchange_id="e1", market_type="perpetual", now=NOW, max_age_s=180
    )  # fmt: skip
    sql, params = fake.calls[0]
    assert len(fake.calls) == 1 and params is not None
    assert "timeframe = '1m'" in sql and "c.is_final" in sql and "LIMIT 1" in sql
    assert "m.symbol = :symbol" in sql and "m.exchange_id = :exchange_id" in sql
    assert params["since"] == NOW - timedelta(seconds=240), "open_time = close_time - 1 min"
    assert "c.open_time <= :until" in sql and params["until"] == NOW - timedelta(seconds=60)
    return got


async def test_latest_final_close_reads_one_final_1m_candle_and_refuses_a_stale_one() -> None:
    fresh = await _close(90)
    assert fresh is not None and fresh.close == Decimal("7.5")
    assert fresh.close_time == NOW - timedelta(seconds=30)
    assert await _close(300) is None
    assert await _close(30) is None, "a bar that closes after now is never used (no look-ahead)"


def _parity(**over: Any) -> spot_signals.Parity:
    kwargs: dict[str, Any] = {**PARITY, **over}
    return spot_signals.parity_ratio(**kwargs)


def _geometry(**over: Any) -> spot_signals.Geometry:
    kwargs: dict[str, Any] = {**GEOMETRY, **over}
    return spot_signals.geometry(**kwargs)


def test_parity_ratio_is_jup_usd_over_bin_usd_in_decimal() -> None:
    parity = _parity()
    assert parity.reason is None and parity.jup_usd is not None and parity.ratio is not None
    assert parity.jup_usd == Decimal("10") / Decimal("12.345678")
    assert parity.ratio == parity.jup_usd / Decimal("0.80")
    assert abs(parity.ratio - Decimal("1.0125")) < Decimal("0.00001")
    thousand = _parity(units_per_binance_unit=Decimal(1000), bin_usd=Decimal("800"))
    assert thousand.ratio == parity.ratio, "1000BONK: 1000 token units per Binance unit"


@pytest.mark.parametrize(
    "over,reason",
    [
        ({"bin_usd": None}, "market_price_unavailable"),
        ({"bin_usd": Decimal(0)}, "market_price_unavailable"),
        ({"sol_usd": None}, "sol_usd_unavailable"),
        ({"decimals": None}, "decimals_unavailable"),
        ({"out_amount_atoms": 0}, "quote_unavailable"),
    ],
)
def test_parity_unavailable_names_its_reason_never_zero(over: dict[str, Any], reason: str) -> None:
    parity = _parity(**over)
    assert parity.ratio is None and parity.reason == reason


def test_geometry_is_the_signal_s_fractions_and_a_capped_horizon() -> None:
    geo = _geometry()
    assert geo.reason is None and geo.horizon_s == 14_400
    assert (geo.stop_frac, geo.target_frac) == (Decimal("0.015"), Decimal("0.0225"))
    assert _geometry(expected_holding_s=None, max_hold_s=3_600).horizon_s == 3_600
    assert _geometry(reference_price=None).reason == "reference_unavailable"
    assert _geometry(stop=None).reason == "stop_unavailable"
    assert _geometry(target1=Decimal(0)).reason == "target_unavailable"
    inverted = _geometry(stop=Decimal("101"))
    assert inverted.reason is None and inverted.stop_frac is not None and inverted.stop_frac < 0


def test_signal_inputs_carry_the_parity_and_the_desk_s_open_and_pending_markets() -> None:
    candidate = spot_repo.candidate_from_row(candidate_row())
    parity = spot_signals.Parity(ratio=None, reason="sol_usd_unavailable")
    inputs = spot_signals.signal_inputs(
        candidate,
        parity=parity,
        quote_impact_pct=Decimal("0.001"),
        priority_fee_sol=Decimal("0.0001"),
        open_spot_markets=("WIFUSDT",),
        pending_spot_markets=(),
    )
    assert inputs is not None and inputs.signal_id == SIGNAL and inputs.parity_ratio is None
    assert inputs.parity_reason == "sol_usd_unavailable"
    assert inputs.open_spot_markets == ("WIFUSDT",)
    assert inputs.stop_frac == Decimal("0.015") and inputs.target_frac == Decimal("0.0225")
    incomplete = spot_repo.candidate_from_row({**candidate_row(), "reference_price": None})
    assert spot_signals.signal_inputs(
        incomplete, parity=parity, quote_impact_pct=None, priority_fee_sol=Decimal(0),
        open_spot_markets=(), pending_spot_markets=(),
    ) is None  # fmt: skip


# ------------------------------------------------------------------ brake
async def test_brake_positions_are_memes_plus_spot_with_lane_spot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    meme = OpenPosition(
        id="m1", proposal_id="pr1", mint="M" * 44, entry_at=NOW, tokens=5,
        sol_spent_lamports=10_000_000, initial_risk_sol=Decimal("0.01"), params={},
        mark_sol=Decimal("0.01"), high_water_sol=None, exit_intent=None,
        sell_requested_at=None, sell_requested_by=None, migrated=False,
    )  # fmt: skip

    async def memes(_session: Any) -> list[OpenPosition]:
        return [meme]

    async def spots(_session: Any) -> list[spot_repo.SpotPosition]:
        return [spot_repo.spot_position_from_row(position_row())]

    monkeypatch.setattr(spot_brake, "open_positions", memes)
    monkeypatch.setattr(spot_brake, "open_spot_positions", spots)
    got = await spot_brake.brake_positions(cast(Any, object()))
    assert [p.id for p in got] == ["m1", "p1"]
    spot = got[1]
    assert spot.params["lane"] == SPOT_LANE == "spot" and spot.proposal_id == SIGNAL
    assert (spot.sol_spent_lamports, spot.mark_sol) == (50_000_000, Decimal("0.0505"))
    assert spot.initial_risk_sol == Decimal("0.00075") and spot.tokens == 660_000_000
    assert spot.migrated is False and spot.mint == MINT


async def test_spot_pending_intents_reserve_the_ticket_on_lane_spot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pending = spot_repo.PendingSpotIntent(
        signal_id=SIGNAL, market_symbol="UNIUSDT", mint=MINT, reserved_sol=Decimal("0.05")
    )

    async def rows(_session: Any) -> list[spot_repo.PendingSpotIntent]:
        return [pending]

    monkeypatch.setattr(spot_brake, "pending_spot_markets", rows)
    [intent] = await spot_brake.spot_pending_intents(cast(Any, object()))
    assert (intent.proposal_id, intent.mint, intent.reserved_sol) == (SIGNAL, MINT, Decimal("0.05"))
    assert intent.lane == "spot"
