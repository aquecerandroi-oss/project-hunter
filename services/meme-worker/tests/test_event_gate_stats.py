"""T4.70 (notes-T4.66.md §7, P0): the three new heartbeat numbers —
``subscribed_at_create_total``, ``create_to_subscribe_ms_p50``/``_p95`` and
``early_retention_unknown_share_60s``. Pure, no Docker.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hunter_meme_worker.event_gate_stats import EventGateStats, heartbeat_fields

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 20, 0, 0, tzinfo=UTC)


def test_subscribed_at_create_counts_and_measures_latency() -> None:
    stats = EventGateStats()
    stats.record_subscribed_at_create(5.0)
    stats.record_subscribed_at_create(15.0)
    fields = heartbeat_fields(stats, now=NOW, enabled=True)
    assert fields["event_gate_subscribed_at_create_total"] == "2"
    assert fields["event_gate_create_to_subscribe_ms_p50"] == "5"
    assert fields["event_gate_create_to_subscribe_ms_p95"] == "15"


def test_subscribed_at_create_unmeasured_is_never_a_zero() -> None:
    fields = heartbeat_fields(EventGateStats(), now=NOW, enabled=True)
    assert fields["event_gate_subscribed_at_create_total"] == "0"
    assert fields["event_gate_create_to_subscribe_ms_p50"] == ""
    assert fields["event_gate_create_to_subscribe_ms_p95"] == ""


def test_early_retention_unknown_share_is_over_the_same_60s_window() -> None:
    stats = EventGateStats()
    for _ in range(4):
        stats.record_evaluation(NOW)
    stats.record_early_retention_unknown(NOW)
    fields = heartbeat_fields(stats, now=NOW, enabled=True)
    assert fields["event_gate_early_retention_unknown_share_60s"] == "0.25"


def test_early_retention_unknown_share_is_blank_with_nothing_judged() -> None:
    fields = heartbeat_fields(EventGateStats(), now=NOW, enabled=True)
    assert fields["event_gate_early_retention_unknown_share_60s"] == ""
