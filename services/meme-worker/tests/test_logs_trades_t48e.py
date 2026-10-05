"""T4.8e, pure/no Docker: a ``TradeEvent`` the decoder cannot read is not "a notification
without a trade".

Before T4.8e ``trade_events_from_logs`` swallowed an undecodable event, so after the pump
program's redeploy of 2026-10-02 (15:47:21Z) the event gate, the launch lane and the exits
kept evaluating mints off account notifications alone — ``event_gate_evaluations > 0`` — while
every trade, creator sell and early buyer vanished from the tape, with no gap mark and no counter
(Astra, 05/10/2026: "research-coverage failure, severity HIGH").
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import base64
import contextlib
import gc
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.rpc_ws_models import LogsNotification
from hunter_exchanges.pumpfun.trade_event import trade_events_from_logs
from hunter_meme_worker.config import MemeConfig
from hunter_meme_worker.context import RadarContext, RadarState
from hunter_meme_worker.event_gate_config import EventGateConfig
from hunter_meme_worker.event_gate_eval import apply_notification
from hunter_meme_worker.event_gate_runtime import EventGateRuntime
from hunter_meme_worker.event_gate_stats import EventGateStats
from hunter_meme_worker.event_gate_stats import heartbeat_fields as gate_heartbeat
from hunter_meme_worker.event_state import MintEventState
from hunter_meme_worker.lab import LabContext, LabState
from hunter_meme_worker.launch_lane_eval import _fold_logs
from hunter_meme_worker.launch_lane_runtime import LaunchWatch
from hunter_meme_worker.launch_lane_stats import LaunchLaneStats
from hunter_meme_worker.launch_lane_stats import heartbeat_fields as launch_heartbeat
from hunter_meme_worker.logs_trades import LostTrades, logs_trades
from hunter_meme_worker.tracker import MintTracker

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).parents[3] / "packages/exchange-adapters/tests/fixtures/pumpfun"
MINT = "So11111111111111111111111111111111111111112"
_PREFIX = "Program data: "


def _real_logs() -> tuple[str, ...]:
    """The logs of a real sell read off the chain on 2026-10-05, after the redeploy."""
    tx = json.loads((FIXTURES / "t48e_rpc_tx_sell_61x6SRWNuLhg_raw.json").read_text())
    return tuple(tx["meta"]["logMessages"])


def _trade_line(logs: tuple[str, ...]) -> str:
    return next(line for line in logs if line.startswith(_PREFIX))


def _undecodable(extra: int = 7) -> str:
    """The real event with ``extra`` more bytes: a layout nobody has seen."""
    raw = base64.b64decode(_trade_line(_real_logs())[len(_PREFIX) :])
    return _PREFIX + base64.b64encode(raw + b"\x00" * extra).decode()


def _notif(logs: tuple[str, ...]) -> LogsNotification:
    (event,) = trade_events_from_logs(_real_logs())
    at = datetime.fromtimestamp(event.timestamp, tz=UTC) + timedelta(seconds=0.5)
    return LogsNotification(
        subscription_id=7,
        kind="logs",
        slot=453_609_412,
        signature="sig",
        err=None,
        logs=logs,
        received_at=at,
    )


def _gate() -> EventGateRuntime:
    radar = RadarContext(
        config=MemeConfig(enabled=True),
        session_factory=None,  # type: ignore[arg-type]
        tracker=MintTracker(window_minutes=60, cap=200),
        state=RadarState(),
        events=None,  # type: ignore[arg-type]
        curves=None,  # type: ignore[arg-type]
        chain=None,  # type: ignore[arg-type]
    )
    lab = LabContext(
        config=MemeConfig(enabled=True, lab_enabled=True),
        session_factory=None,  # type: ignore[arg-type]
        state=LabState(),
        quotes=None,
        heartbeat=None,
    )
    config = EventGateConfig(mode="on", ws_url="ws://x", commitment="confirmed", max_mints=10)
    rt = EventGateRuntime(radar=radar, lab=lab, ws=None, config=config)  # type: ignore[arg-type]
    notif = _notif(_real_logs())
    rt.book.touch(
        MINT, at=notif.received_at, first_seen_at=notif.received_at - timedelta(seconds=90)
    )
    rt.subs_by_logical[notif.subscription_id] = MINT
    return rt


# -- the event gate ------------------------------------------------------------------------


def test_a_real_post_upgrade_trade_reaches_the_tape_and_marks_no_gap() -> None:
    rt = _gate()
    assert apply_notification(rt, _notif(_real_logs())) == MINT
    state = rt.book.get(MINT)
    assert state is not None and len(state.points) == 1 and state.gaps == 0
    assert MINT in rt.reserves
    assert rt.stats.lost_trades.trades_total == 0


def test_a_notification_without_a_trade_event_is_normal_and_marks_no_gap() -> None:
    """A non-trade instruction on the same PDA: nothing was lost."""
    rt = _gate()
    quiet = _notif(("Program 6EF8 invoke [1]", "Program data: AAAA", "Program 6EF8 success"))
    assert apply_notification(rt, quiet) == MINT
    state = rt.book.get(MINT)
    assert state is not None and state.gaps == 0 and len(state.points) == 0
    assert rt.stats.lost_trades.trades_total == 0 and rt.stats.lost_trades.notifications_total == 0


def test_an_undecodable_trade_event_is_counted_and_marks_a_gap() -> None:
    rt = _gate()
    notif = _notif((f"Program {PUMP_PROGRAM_ID} invoke [1]", _undecodable()))
    assert apply_notification(rt, notif) == MINT  # the lane still evaluates, off a warming tape
    state = rt.book.get(MINT)
    assert state is not None
    assert state.gaps == 1 and state.covered_since == notif.received_at
    assert len(state.points) == 0  # the lost trade is not invented
    lost = rt.stats.lost_trades
    assert (lost.trades_total, lost.notifications_total) == (1, 1)
    assert "31 trailing bytes" in lost.last_error


def test_a_notification_with_one_good_and_one_lost_trade_keeps_both_facts() -> None:
    rt = _gate()
    notif = _notif((_undecodable(), *_real_logs()))
    assert apply_notification(rt, notif) == MINT
    state = rt.book.get(MINT)
    assert state is not None and state.gaps == 1  # the tape is incomplete: say so
    assert (rt.stats.lost_trades.trades_total, rt.stats.lost_trades.notifications_total) == (1, 1)
    assert MINT in rt.reserves  # ...and the trade that could be read still moved the reserves


def test_the_gate_heartbeat_makes_the_blindness_visible() -> None:
    rt = _gate()
    now = datetime(2026, 10, 5, 16, 0, tzinfo=UTC)
    quiet = gate_heartbeat(rt.stats, now=now, enabled=True)
    assert quiet["event_gate_undecodable_trades_total"] == "0"
    assert quiet["event_gate_undecodable_trades_60s"] == "0"
    assert quiet["event_gate_last_undecodable_error"] == ""
    for _ in range(3):
        apply_notification(rt, replace(_notif((_undecodable(),)), received_at=now))
    loud = gate_heartbeat(rt.stats, now=now, enabled=True)
    assert loud["event_gate_undecodable_trades_total"] == "3"
    assert loud["event_gate_undecodable_notifications_total"] == "3"
    assert loud["event_gate_undecodable_trades_60s"] == "3"
    assert "trailing bytes" in loud["event_gate_last_undecodable_error"]
    later = gate_heartbeat(rt.stats, now=now + timedelta(seconds=120), enabled=True)
    assert later["event_gate_undecodable_trades_60s"] == "0"  # the window rolls
    assert later["event_gate_undecodable_trades_total"] == "3"  # the total does not


def test_the_log_is_rate_limited_but_the_counter_is_exact() -> None:
    lost = LostTrades()
    t0 = datetime(2026, 10, 5, 16, 0, tzinfo=UTC)
    from hunter_exchanges.pumpfun.trade_event import scan_trade_event_logs

    scan = scan_trade_event_logs([_undecodable()])
    assert lost.record(t0, scan) is True
    assert lost.record(t0 + timedelta(seconds=1), scan) is False
    assert lost.record(t0 + timedelta(seconds=31), scan) is True
    assert lost.trades_total == 3


# -- the launch lane -----------------------------------------------------------------------


def _watch() -> LaunchWatch:
    notif = _notif(_real_logs())
    state = MintEventState(
        mint=MINT,
        subscribed_at=notif.received_at - timedelta(seconds=90),
        first_seen_at=notif.received_at - timedelta(seconds=90),
    )
    return LaunchWatch(
        mint=MINT,
        spec=None,  # type: ignore[arg-type]
        proposal_id="p",
        rule_set_id="r",
        created_at=notif.received_at - timedelta(seconds=90),
        creation_buyers=frozenset(),
        initial_real_token_reserves=None,
        logs_id=7,
        account_id=8,
        state=state,
    )


def test_the_launch_lane_reads_a_real_post_upgrade_trade() -> None:
    watch, stats = _watch(), LaunchLaneStats()
    latest = _fold_logs(watch, _notif(_real_logs()), stats.lost_trades)
    assert latest is not None and watch.state.gaps == 0
    assert stats.lost_trades.trades_total == 0


def test_the_launch_lane_marks_a_gap_and_counts_an_undecodable_trade() -> None:
    watch, stats = _watch(), LaunchLaneStats()
    notif = _notif((_undecodable(),))
    assert _fold_logs(watch, notif, stats.lost_trades) is None
    assert watch.state.gaps == 1 and watch.state.covered_since == notif.received_at
    assert stats.lost_trades.trades_total == 1
    fields = launch_heartbeat(stats, now=notif.received_at, mode="shadow")
    assert fields["launch_lane_undecodable_trades_total"] == "1"
    assert "trailing bytes" in fields["launch_lane_last_undecodable_error"]


def test_the_stats_objects_carry_independent_counters() -> None:
    assert EventGateStats().lost_trades is not EventGateStats().lost_trades
    assert LaunchLaneStats().lost_trades is not LaunchLaneStats().lost_trades


def test_a_failed_instruction_is_not_a_lost_trade() -> None:
    """``err`` is set: the transaction reverted, its event (if any) never happened."""
    rt = _gate()
    failed = replace(_notif((_undecodable(),)), err={"InstructionError": [0, "Custom"]})
    assert apply_notification(rt, failed) is None
    assert rt.stats.lost_trades.trades_total == 0


# -- T4.8f (guardian): the loss is marked even when the consumer stops early --------------


def _lost_notif_with_a_readable_trade() -> LogsNotification:
    return _notif((_undecodable(), *_real_logs()))


def test_a_break_out_of_the_loop_still_marks_the_gap_and_counts_the_loss() -> None:
    rt = _gate()
    state = rt.book.get(MINT)
    assert state is not None
    notif = _lost_notif_with_a_readable_trade()
    for _trade in logs_trades(rt.stats.lost_trades, state, notif, lane="t", mint=MINT):
        break  # a future consumer that stops at the first trade must not hide the loss
    assert state.gaps == 1 and rt.stats.lost_trades.trades_total == 1


def test_an_exception_in_the_consumer_still_marks_the_gap() -> None:
    rt = _gate()
    state = rt.book.get(MINT)
    assert state is not None
    notif = _lost_notif_with_a_readable_trade()

    def consumer() -> None:
        for _trade in logs_trades(rt.stats.lost_trades, state, notif, lane="t", mint=MINT):
            raise RuntimeError("apply_trade blew up")

    with contextlib.suppress(RuntimeError):
        consumer()
    gc.collect()
    assert state.gaps == 1 and rt.stats.lost_trades.trades_total == 1


def test_closing_an_unstarted_generator_marks_nothing() -> None:
    """A generator that never ran saw nothing: no scan, no gap (the finally is not entered)."""
    rt = _gate()
    state = rt.book.get(MINT)
    assert state is not None
    gen = logs_trades(
        rt.stats.lost_trades, state, _lost_notif_with_a_readable_trade(), lane="t", mint=MINT
    )
    gen.close()
    assert state.gaps == 0 and rt.stats.lost_trades.trades_total == 0


def test_another_programs_trade_event_shaped_line_marks_no_gap() -> None:
    """T4.8f: attributed by the invoke stack — it is not the pump program's, so not a loss."""
    rt = _gate()
    other = "DRVSpZ2YUYYKgZP8XtLhAGtT1zYSCKzeHfb4DgRnrgqD"
    notif = _notif((f"Program {other} invoke [1]", _undecodable(), f"Program {other} success"))
    assert apply_notification(rt, notif) == MINT
    state = rt.book.get(MINT)
    assert state is not None and state.gaps == 0
    assert rt.stats.lost_trades.trades_total == 0


def test_a_consumer_that_raises_marks_the_gap_before_the_exception_even_leaves_the_lane(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T4.8f (Astra): the lanes close the generator deterministically (``contextlib.closing``) —
    the gap is marked when the ``with`` exits, not whenever the garbage collector gets to a
    generator the traceback is still holding."""
    rt = _gate()
    state = rt.book.get(MINT)
    assert state is not None

    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("apply_trade blew up")

    monkeypatch.setattr(MintEventState, "apply_trade", boom)
    notif = _lost_notif_with_a_readable_trade()
    with pytest.raises(RuntimeError):
        apply_notification(rt, notif)
        pytest.fail("unreachable")
    assert state.gaps == 1 and rt.stats.lost_trades.trades_total == 1
