"""T4.67b — ``MEME_LAUNCH_*`` from the environment: ``off`` by default, ``paper``
and ``on`` as written, anything else ``off``; every number bounded and falling
back to its default; the ticket never above ``max_sol_per_trade``; the
heartbeat fields published in every mode."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from hunter_meme_executor.launch_config import (
    DEFAULT_MAX_AGE_S,
    DEFAULT_PRIORITY_FLOOR,
    DEFAULT_TICKET_SOL,
    LaunchConfig,
)
from hunter_meme_executor.launch_stats import LaunchStats, launch_heartbeat_fields
from hunter_risk_meme import MEME_PAPER_V0

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 19, 15, 0, tzinfo=UTC)


def test_the_flag_is_off_by_default_and_only_on_enables_the_executor() -> None:
    assert LaunchConfig.from_env({}).mode == "off"
    assert LaunchConfig.from_env({}).enabled is False
    assert LaunchConfig.from_env({"MEME_LAUNCH_LANE": "paper"}).mode == "paper"
    assert LaunchConfig.from_env({"MEME_LAUNCH_LANE": "paper"}).enabled is False
    assert LaunchConfig.from_env({"MEME_LAUNCH_LANE": "on"}).enabled is True
    assert LaunchConfig.from_env({"MEME_LAUNCH_LANE": "ON "}).enabled is True
    assert LaunchConfig.from_env({"MEME_LAUNCH_LANE": "yes"}).mode == "off"
    assert LaunchConfig.from_env({"MEME_LAUNCH_LANE": "1"}).mode == "off"


def test_the_defaults_are_the_briefs() -> None:
    cfg = LaunchConfig.from_env({})
    assert cfg.max_open == 2
    assert cfg.ticket_sol == DEFAULT_TICKET_SOL == Decimal("0.01")
    assert cfg.priority_floor_micro_lamports == DEFAULT_PRIORITY_FLOOR == 1_000_000
    assert cfg.buy_slippage_pct == Decimal(10) and cfg.buy_slippage_bps() == 1000
    assert cfg.skip_simulation is False
    assert cfg.max_participation_pct == Decimal("0.10")
    assert cfg.max_age_s == DEFAULT_MAX_AGE_S == 5


def test_every_number_is_read_bounded_and_falls_back_on_nonsense() -> None:
    cfg = LaunchConfig.from_env(
        {
            "MEME_LAUNCH_MAX_OPEN": "3",
            "MEME_LAUNCH_TICKET_SOL": "0.02",
            "MEME_LAUNCH_PRIORITY_FLOOR_MICRO_LAMPORTS": "2500000",
            "MEME_LAUNCH_BUY_SLIPPAGE_PCT": "15",
            "MEME_LAUNCH_SKIP_SIMULATION": "true",
            "MEME_LAUNCH_MAX_PARTICIPATION_PCT": "0.25",
            "MEME_LAUNCH_MAX_AGE_S": "8",
        }
    )
    assert (cfg.max_open, cfg.ticket_sol, cfg.priority_floor_micro_lamports) == (
        3,
        Decimal("0.02"),
        2_500_000,
    )
    assert cfg.buy_slippage_pct == Decimal(15) and cfg.skip_simulation is True
    assert cfg.max_participation_pct == Decimal("0.25") and cfg.max_age_s == 8
    bad = LaunchConfig.from_env(
        {
            "MEME_LAUNCH_MAX_OPEN": "0",
            "MEME_LAUNCH_TICKET_SOL": "abc",
            "MEME_LAUNCH_PRIORITY_FLOOR_MICRO_LAMPORTS": "-1",
            "MEME_LAUNCH_BUY_SLIPPAGE_PCT": "25",
            "MEME_LAUNCH_SKIP_SIMULATION": "maybe",
            "MEME_LAUNCH_MAX_PARTICIPATION_PCT": "1.5",
            "MEME_LAUNCH_MAX_AGE_S": "NaN",
        }
    )
    assert bad == LaunchConfig()


def test_the_ticket_never_exceeds_the_policys_max_sol_per_trade() -> None:
    limits = MEME_PAPER_V0.model_copy(update={"max_sol_per_trade": Decimal("0.005")})
    cfg = LaunchConfig.from_env({"MEME_LAUNCH_TICKET_SOL": "0.05"})
    assert cfg.ticket(limits) == Decimal("0.005")
    assert cfg.profile(limits).ticket_sol == Decimal("0.005")
    assert cfg.ticket(MEME_PAPER_V0) == Decimal("0.05") == MEME_PAPER_V0.max_sol_per_trade
    assert cfg.as_json(limits)["ticket_sol"] == "0.005"


def test_the_heartbeat_publishes_the_lane_in_every_mode() -> None:
    stats = LaunchStats()
    off = launch_heartbeat_fields(stats, LaunchConfig(), now=NOW, open_launch=0)
    assert off["launch_lane_mode"] == "off" and off["launch_open"] == "0"
    assert off["proposal_to_submit_ms_p50"] == "" and off["launch_refusals"] == "{}"
    assert off["launch_blockhash_age_s"] == ""
    stats.record_refusal("launch_proposal_stale")
    stats.record_refusal("launch_proposal_stale")
    stats.record_refusal("kill_switch_blocked")
    for ms in (900.0, 1100.0, 1300.0, 4000.0):
        stats.record_submit_latency_ms(ms)
    stats.buys_total, stats.sells_total = 3, 2
    on = launch_heartbeat_fields(stats, LaunchConfig(mode="on"), now=NOW, open_launch=1)
    assert on["launch_lane_mode"] == "on" and on["launch_open"] == "1"
    assert on["launch_buys_total"] == "3" and on["launch_sells_total"] == "2"
    assert on["proposal_to_submit_ms_p50"] == "1200" and on["proposal_to_submit_ms_p95"] == "4000"
    assert on["launch_refusals"] == '{"kill_switch_blocked": 1, "launch_proposal_stale": 2}'
