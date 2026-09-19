"""``services/meme_live.py::read_executor`` (T4.28c) -- the stage-1 "modo
sozinho" fields the heartbeat carries since T4.28/T4.28d/T4.28f: ``auto_approve``,
the hourly counters, the scope counters and the gates reload bookkeeping. Pure:
a fake decoded Redis hash (``dict[str, str]``, exactly what ``hgetall`` returns
after decoding) in, the Pydantic schema out -- no DB, no Redis.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_api.services.meme_live import read_executor

pytestmark = pytest.mark.unit

AS_OF = datetime(2026, 9, 16, 15, 0, tzinfo=UTC)
ALIVE_BASE: dict[str, str] = {
    "ts": AS_OF.isoformat(),
    "executor_ts": AS_OF.isoformat(),
    "last_entries_tick_at": (AS_OF - timedelta(seconds=5)).isoformat(),
}


def test_the_stage_1_fields_are_absent_before_t4_28_ever_wrote_them() -> None:
    """A heartbeat from before this feature existed names nothing invented."""
    out = read_executor(ALIVE_BASE, as_of=AS_OF, key="hb:meme:executor", error=None)
    assert out.status == "alive"
    assert out.auto_approve is None
    assert out.auto_approve_max_per_hour is None
    assert out.auto_approved_1h is None
    assert out.auto_refused_1h == {}
    assert out.auto_skipped == {}
    assert out.small_test_used_sol is None
    assert out.small_test_trades_done is None
    assert out.small_test_remaining_sol is None
    assert out.small_test_exhausted is None
    assert out.gates_mtime is None
    assert out.gates_reloaded_at is None
    assert out.gates_reload_error is None


def test_stage_1_on_with_a_partly_spent_scope_and_a_recent_reload() -> None:
    fields = {
        **ALIVE_BASE,
        "auto_approve": "true",
        "auto_approve_max_per_hour": "5",
        "auto_approved_1h": "2",
        "auto_refused_1h": '{"progress_below_window": 4, "bundled_share_unmeasurable": 1}',
        "auto_skipped": '{"mint_busy": 3, "recently_refused": 2, "scope_exhausted:max_total_sol": 1}',
        "small_test_used_sol": "0.18",
        "small_test_trades_done": "3",
        "small_test_remaining_sol": "0.07",
        "small_test_exhausted": "",
        "gates_mtime": (AS_OF - timedelta(minutes=6)).isoformat(),
        "gates_reloaded_at": (AS_OF - timedelta(minutes=6)).isoformat(),
        "gates_reload_error": "",
    }
    out = read_executor(fields, as_of=AS_OF, key="hb:meme:executor", error=None)
    assert out.auto_approve is True
    assert out.auto_approve_max_per_hour == 5
    assert out.auto_approved_1h == 2
    assert out.auto_refused_1h == {"progress_below_window": 4, "bundled_share_unmeasurable": 1}
    assert out.auto_skipped == {
        "mint_busy": 3,
        "recently_refused": 2,
        "scope_exhausted:max_total_sol": 1,
    }
    assert out.small_test_used_sol == Decimal("0.18")
    assert out.small_test_trades_done == 3
    assert out.small_test_remaining_sol == Decimal("0.07")
    assert out.small_test_exhausted is None
    assert out.gates_mtime == AS_OF - timedelta(minutes=6)
    assert out.gates_reloaded_at == AS_OF - timedelta(minutes=6)
    assert out.gates_reload_error is None


def test_an_exhausted_scope_and_a_deferred_gates_failure_are_named() -> None:
    fields = {
        **ALIVE_BASE,
        "auto_approve": "false",
        "small_test_exhausted": "max_trades",
        "gates_reload_error": "deferred:gates_file_invalid",
    }
    out = read_executor(fields, as_of=AS_OF, key="hb:meme:executor", error=None)
    assert out.auto_approve is False
    assert out.small_test_exhausted == "max_trades"
    assert out.gates_reload_error == "deferred:gates_file_invalid"


def test_an_old_heartbeat_without_spot1_parses_to_none() -> None:
    """T4.74-6: an executor build that predates the field names nothing."""
    out = read_executor(ALIVE_BASE, as_of=AS_OF, key="hb:meme:executor", error=None)
    assert out.spot1 is None


def test_a_malformed_spot1_blob_is_none_not_a_raise() -> None:
    for bad in (
        "not-json",
        "[]",
        '{"strategy_version": "v14"}',
        '{"mode": "on", "closed": "nope"}',
    ):
        out = read_executor(
            {**ALIVE_BASE, "spot1": bad}, as_of=AS_OF, key="hb:meme:executor", error=None
        )
        assert out.spot1 is None


def test_a_full_spot1_blob_parses() -> None:
    entry_at = (AS_OF - timedelta(minutes=20)).isoformat()
    blob = {
        "mode": "on",
        "strategy_version": "v14",
        "ticket_sol": "0.05",
        "max_open": 3,
        "markets_enabled": 4,
        "open": [
            {
                "market": "UNIUSDT",
                "mint8": "7xKXtg2C",
                "entry_at": entry_at,
                "sol_spent": "0.05",
                "mark_sol": "0.052",
                "r_now": "0.4",
                "age_s": 1200,
                "horizon_s": 14400,
                "mark_stale_s": None,
            },
            {"market": "bad", "sol_spent": "0.05"},
        ],
        "signals_seen": 23,
        "admitted": 5,
        "refused_by_reason": {"spot1_open_cap": 3, "signal_stale": 2},
        "exits_by_reason": {"stop": 2, "target": 1},
        "blocked_exits": {"abc12345": "panic_slippage"},
        "closed": {
            "n": 15,
            "sum_r_gross": "14.9",
            "sum_r_net": "3.2",
            "sum_pnl_sol": "0.08",
            "expectancy_r_net": "0.21",
        },
        "refutation": {"trades": 15, "threshold": 20, "state": "ok"},
        "last_signature": "5sig",
        "last_refusal": "signal_stale",
        "last_entries_tick_at": AS_OF.isoformat(),
        "last_exits_tick_at": AS_OF.isoformat(),
    }
    out = read_executor(
        {**ALIVE_BASE, "spot1": json.dumps(blob)}, as_of=AS_OF, key="hb:meme:executor", error=None
    )
    assert out.spot1 is not None
    spot1 = out.spot1
    assert spot1.mode == "on"
    assert spot1.strategy_version == "v14"
    assert spot1.ticket_sol == Decimal("0.05")
    assert spot1.max_open == 3
    assert spot1.markets_enabled == 4
    assert len(spot1.open) == 1
    position = spot1.open[0]
    assert position.market == "UNIUSDT"
    assert position.mint8 == "7xKXtg2C"
    assert position.mark_sol == Decimal("0.052")
    assert position.r_now == Decimal("0.4")
    assert position.mark_stale_s is None
    assert spot1.signals_seen == 23
    assert spot1.admitted == 5
    assert spot1.refused_by_reason == {"spot1_open_cap": 3, "signal_stale": 2}
    assert spot1.exits_by_reason == {"stop": 2, "target": 1}
    assert spot1.blocked_exits == {"abc12345": "panic_slippage"}
    assert spot1.closed.n == 15
    assert spot1.closed.sum_r_gross == Decimal("14.9")
    assert spot1.closed.expectancy_r_net == Decimal("0.21")
    assert spot1.refutation.trades == 15
    assert spot1.refutation.threshold == 20
    assert spot1.refutation.state == "ok"
    assert spot1.last_signature == "5sig"
    assert spot1.last_refusal == "signal_stale"


def test_a_malformed_count_never_crashes_the_read() -> None:
    """A bad row in the JSON dicts (or a non-numeric scalar) is dropped, not a 500."""
    fields = {
        **ALIVE_BASE,
        "auto_approve_max_per_hour": "not-a-number",
        "auto_approved_1h": "not-a-number",
        "auto_refused_1h": '{"progress_below_window": "four"}',
        "auto_skipped": "not-json",
    }
    out = read_executor(fields, as_of=AS_OF, key="hb:meme:executor", error=None)
    assert out.auto_approve_max_per_hour is None
    assert out.auto_approved_1h is None
    assert out.auto_refused_1h == {}
    assert out.auto_skipped == {}
