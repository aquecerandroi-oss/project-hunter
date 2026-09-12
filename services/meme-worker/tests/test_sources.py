"""The per-source stats and the heartbeat fields of the adendo — pure."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from hunter_meme_worker.sources import (
    PUMPFUN_REST,
    SWAP_API,
    TRENCHES_WS,
    RollingCounter,
    SourcesState,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 12, 9, 0, tzinfo=UTC)


def test_a_rolling_counter_forgets_what_left_the_window() -> None:
    counter = RollingCounter(60)
    counter.add(NOW - timedelta(seconds=70), 5)
    counter.add(NOW - timedelta(seconds=30), 2)
    counter.add(NOW, 1)
    assert counter.total(NOW) == 3
    assert counter.total(NOW + timedelta(seconds=31)) == 1
    counter.add(NOW, 0)
    assert counter.total(NOW + timedelta(seconds=61)) == 0


def test_a_monotonic_client_counter_becomes_per_minute_events() -> None:
    sources = SourcesState()
    assert sources.sample_counter("k", 3, NOW, sources.ws_malformed_60s) == 3
    assert (
        sources.sample_counter("k", 3, NOW + timedelta(seconds=10), sources.ws_malformed_60s) == 0
    )
    assert (
        sources.sample_counter("k", 5, NOW + timedelta(seconds=20), sources.ws_malformed_60s) == 2
    )
    assert sources.ws_malformed_60s.total(NOW + timedelta(seconds=20)) == 5
    assert sources.ws_malformed_60s.total(NOW + timedelta(seconds=75)) == 2


def test_the_heartbeat_names_every_source_and_never_a_silent_zero() -> None:
    sources = SourcesState()
    sources[PUMPFUN_REST].budget_60s = 60
    sources[SWAP_API].budget_60s = 900
    sources[TRENCHES_WS].enabled = False
    sources[TRENCHES_WS].connected = None
    sources[PUMPFUN_REST].record_ok(
        observed_at=NOW - timedelta(seconds=1), received_at=NOW - timedelta(milliseconds=800)
    )
    sources[PUMPFUN_REST].record_spent(NOW)
    sources[PUMPFUN_REST].record_error(NOW, "rate_limited")
    sources.record_snapshot(observed_at=NOW - timedelta(seconds=1), received_at=NOW)
    sources.gaps_60s.add(NOW)
    fields = sources.heartbeat_fields(NOW, tracked=117)
    assert fields["tracked"] == "117"
    assert fields["budget_used_60s"] == "2" and fields["budget_60s"] == "60"
    assert fields["gaps_60s"] == "1" and fields["ws_malformed_60s"] == "0"
    assert fields["lag_s"] == "1.0"
    assert fields["last_snapshot_observed_at"] == (NOW - timedelta(seconds=1)).isoformat()
    assert fields["trenches_connected"] == "disabled"
    assert fields["swap_api_used_60s"] == "0" and fields["swap_api_budget_60s"] == "900"
    per_source = json.loads(fields["sources"])
    assert set(per_source) == {
        "pumpportal_ws",
        "pumpfun_rest",
        "solana_rpc",
        "trenches_ws",
        "swap_api",
        "indexer_risk",
    }
    assert per_source["trenches_ws"]["reason"] == "disabled"
    assert per_source["swap_api"]["reason"] == "never_observed"
    assert per_source["swap_api"]["last_observed_at"] is None
    rest = per_source["pumpfun_rest"]
    assert rest["errors_1h"] == 1 and rest["last_error"] == "rate_limited"
    assert rest["used_60s"] == 2 and rest["lag_s"] == pytest.approx(0.2)
    assert rest["reason"] is None


def test_the_heartbeat_declares_the_discovery_blind_share_and_never_a_silent_zero() -> None:
    """T4.2d, item 3: 8/50 of the ``new`` board at 05:51 BRT were
    ``raydium_launchpad`` — invisible to ``subscribeNewToken`` by construction.
    The share is declared from the board's own listings; an empty hour is
    ``""`` (unknown), not ``0`` (a claim of full coverage)."""
    sources = SourcesState()
    empty = sources.heartbeat_fields(NOW, tracked=0)
    assert empty["new_board_entries_1h"] == "0" and empty["new_board_non_pump_1h"] == "0"
    assert empty["blind_share_1h"] == ""
    for i in range(50):
        sources.record_new_listing(NOW - timedelta(minutes=i), in_scope=i % 6 != 0)
    fields = sources.heartbeat_fields(NOW, tracked=0)
    assert fields["new_board_entries_1h"] == "50" and fields["new_board_non_pump_1h"] == "9"
    assert fields["blind_share_1h"] == "0.18"
    later = sources.heartbeat_fields(NOW + timedelta(hours=2), tracked=0)
    assert later["new_board_entries_1h"] == "0" and later["blind_share_1h"] == ""


def test_a_connected_trenches_says_true_and_a_dropped_one_false() -> None:
    sources = SourcesState()
    sources[TRENCHES_WS].connected = True
    assert sources.heartbeat_fields(NOW, tracked=0)["trenches_connected"] == "true"
    sources[TRENCHES_WS].connected = False
    assert sources.heartbeat_fields(NOW, tracked=0)["trenches_connected"] == "false"
