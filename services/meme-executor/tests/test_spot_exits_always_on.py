"""T4.74-7 — the two MEDIUM findings of ``.claude/state/review-T4.74.md``:

A1: the exits loop runs whenever the executor is live with a signer, whatever
``SPOT1_ENABLED`` says — the flag gates ENTRIES only (RISK_ENGINE §10: an
exit is never blocked by an entry gate). Flag off + one open position ⇒ the
mark and the sell happen; flag off + no position ⇒ zero quotes; no signer or
no live ⇒ still inert. The heartbeat says so (``exits_active``).

A2: a non-retryable Jupiter error on the sell quote / swap build is a HARD
refusal (``quote_refused:<type>`` / ``swap_refused:<type>``) that spends the
``MAX_EXIT_ATTEMPTS`` budget; transient ones keep backing off, and after
``STUCK_AFTER_TRANSIENT`` in a row the position is published as
``stuck_exits[id] = <last reason>`` — cleared by the next hard failure or sell.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, cast

import pytest

from hunter_exchanges.base import ExchangeError
from hunter_exchanges.jupiter.client import JupiterQuoteError
from hunter_meme_executor import main as executor_main
from hunter_meme_executor import spot_exits
from hunter_meme_executor.spot_config import SpotConfig
from hunter_meme_executor.spot_exit_rules import MAX_EXIT_ATTEMPTS
from hunter_meme_executor.spot_heartbeat import spot1_fields
from hunter_meme_executor.spot_send_rules import LegResult

from .spot_exits_rig import NOW, POSITION_ID, FailingJupiter, exits_rig, position
from .spot_fakes import FakeJupiter
from .spot_tx_fixtures import SIGNATURE

pytestmark = pytest.mark.unit

STOP_OUT = 49_000_000
FLAG_OFF = SpotConfig(requested=False, live=True, signer_present=True)
"""``SPOT1_ENABLED=false`` on a live executor with its signer: entries inert, exits on."""


# ------------------------------------------------------------------------ A1
async def test_flag_off_with_an_open_position_still_marks_and_sells(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = exits_rig(monkeypatch, sol_out=STOP_OUT)
    rig.ctx.config.spot = FLAG_OFF
    rig.store.positions = [position()]
    await spot_exits.spot_exits_once(rig.ctx)
    assert [(m[0], str(m[1])) for m in rig.store.marks] == [(POSITION_ID, "0.049")], "marked"
    assert len(rig.store.closes) == 1, "a stop sells with the flag off (RISK_ENGINE §10)"
    assert "sign" in rig.log and rig.store.closes[0]["position_id"] == POSITION_ID
    assert rig.stats.last_exits_tick_at == NOW


async def test_flag_off_without_positions_makes_no_quote(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = exits_rig(monkeypatch, jupiter=FailingJupiter(cast(Any, None), cast(Any, None)))
    rig.ctx.config.spot = FLAG_OFF
    rig.store.positions = []
    await spot_exits.spot_exits_once(rig.ctx)
    assert rig.ctx.treasury_client.quote_calls == 0 and rig.store.marks == []
    assert rig.store.queries == ["open_spot_positions"], "one read, nothing else"


@pytest.mark.parametrize(
    "spot",
    [
        SpotConfig(),
        SpotConfig(requested=False, live=False, signer_present=True),
        SpotConfig(requested=True, live=True, signer_present=False),
    ],
)
async def test_without_live_or_signer_the_exits_stay_inert(
    monkeypatch: pytest.MonkeyPatch, spot: SpotConfig
) -> None:
    rig = exits_rig(monkeypatch, jupiter=FailingJupiter(cast(Any, None), cast(Any, None)))
    rig.ctx.config.spot = spot
    rig.store.positions = [position()]

    def no_session(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("no query while inert")

    monkeypatch.setattr(spot_exits, "role_session", no_session)
    await spot_exits.spot_exits_once(rig.ctx)
    assert rig.ctx.treasury_client.quote_calls == 0 and rig.store.marks == []
    assert not spot_exits.exits_active(spot)


def test_exits_active_is_live_and_signer_never_the_flag() -> None:
    assert spot_exits.exits_active(FLAG_OFF) is True
    assert spot_exits.exits_active(SpotConfig(requested=True, live=True, signer_present=True))
    assert (
        spot_exits.exits_active(SpotConfig(requested=True, live=False, signer_present=True))
        is False
    )
    assert (
        spot_exits.exits_active(SpotConfig(requested=True, live=True, signer_present=False))
        is False
    )
    assert executor_main.spot_exits_active is spot_exits.exits_active, (
        "main.py gates the task by it"
    )


def test_the_heartbeat_publishes_exits_active_next_to_the_inert_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = exits_rig(monkeypatch)
    rig.ctx.config.spot = FLAG_OFF
    fields = spot1_fields(rig.ctx, FLAG_OFF, NOW)
    assert fields["mode"] == "inert:disabled", "still means: no entries"
    assert fields["exits_active"] is True
    off = SpotConfig(requested=True, live=True, signer_present=False)
    assert spot1_fields(rig.ctx, off, NOW)["exits_active"] is False
    assert "stuck_exits" in fields and fields["stuck_exits"] == {}


# ------------------------------------------------------------------------ A2
class _NoRoute(FakeJupiter):
    def quote(self, **kwargs: Any) -> Any:
        self.quote_calls += 1
        raise JupiterQuoteError("no route", status_code=400)


class _RetryableDown(FakeJupiter):
    def quote(self, **kwargs: Any) -> Any:
        self.quote_calls += 1
        raise ExchangeError("503", exchange="jupiter", retryable=True)


class _SwapRefused(FakeJupiter):
    def swap(self, **kwargs: Any) -> Any:
        raise JupiterQuoteError("bad swap", status_code=422)


def _refusals(rig: Any) -> list[str]:
    return [kw["reason"] for status, kw in rig.db.rows if status == "refused"]


async def test_a_non_retryable_quote_error_is_a_hard_refusal_that_blocks_after_six(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = exits_rig(
        monkeypatch, sol_out=STOP_OUT, jupiter=_NoRoute(cast(Any, None), cast(Any, None))
    )
    # The mark fails too (same client) — a ``time`` exit needs no mark.
    rig.store.positions = [position(entry_at=NOW - timedelta(hours=5))]
    clock = NOW
    for n in range(MAX_EXIT_ATTEMPTS):
        monkeypatch.setattr(spot_exits, "utcnow", lambda clock=clock: clock)
        await spot_exits.spot_exits_once(rig.ctx)
        clock = clock + timedelta(seconds=61)
        assert rig.stats.exit_hard_failures[POSITION_ID] == n + 1
    assert rig.db.statuses() == ["refused"] * MAX_EXIT_ATTEMPTS
    assert _refusals(rig)[0] == "quote_refused:JupiterQuoteError"
    assert rig.stats.blocked_exits == {POSITION_ID: "time"}
    assert rig.stats.stuck_exits == {}, "blocked, not stuck: the budget was spent"
    assert "sign" not in rig.log


async def test_a_non_retryable_swap_build_error_is_hard_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = exits_rig(monkeypatch, sol_out=STOP_OUT)
    rig.ctx.treasury_client = _SwapRefused(
        rig.ctx.treasury_client.quote_reply, rig.ctx.treasury_client.swap_reply
    )
    rig.store.positions = [position()]
    await spot_exits.spot_exits_once(rig.ctx)
    assert _refusals(rig) == ["swap_refused:JupiterQuoteError"]
    assert rig.stats.exit_hard_failures[POSITION_ID] == 1


async def test_a_retryable_exchange_error_stays_transient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = exits_rig(
        monkeypatch, sol_out=STOP_OUT, jupiter=_RetryableDown(cast(Any, None), cast(Any, None))
    )
    rig.store.positions = [position(entry_at=NOW - timedelta(hours=5))]
    await spot_exits.spot_exits_once(rig.ctx)
    assert _refusals(rig) == ["quote_failed:ExchangeError"]
    assert rig.stats.exit_hard_failures[POSITION_ID] == 0
    assert rig.stats.exit_transient_streak[POSITION_ID] == 1


def _stub_leg(monkeypatch: pytest.MonkeyPatch, reason: str) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    async def leg(ctx: Any, **kw: Any) -> LegResult:
        calls.append(kw)
        return LegResult("refused", reason, None, 0, 0, None)

    monkeypatch.setattr(spot_exits, "spot_leg", leg)
    return calls


async def test_thirty_transient_refusals_in_a_row_publish_the_position_as_stuck(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = exits_rig(monkeypatch, sol_out=STOP_OUT)
    rig.store.positions = [position()]
    calls = _stub_leg(monkeypatch, "quote_failed:ReadTimeout")
    n = spot_exits.STUCK_AFTER_TRANSIENT
    clock = NOW
    for k in range(n - 1):
        monkeypatch.setattr(spot_exits, "utcnow", lambda clock=clock: clock)
        await spot_exits.spot_exits_once(rig.ctx)
        clock = clock + timedelta(seconds=61)
        assert rig.stats.stuck_exits == {}, f"not yet at {k + 1}"
    monkeypatch.setattr(spot_exits, "utcnow", lambda clock=clock: clock)
    await spot_exits.spot_exits_once(rig.ctx)
    assert len(calls) == n
    assert rig.stats.stuck_exits == {POSITION_ID: "quote_failed:ReadTimeout"}
    assert rig.stats.blocked_exits == {}, "stuck is visible, never a block: the loop keeps trying"
    assert rig.stats.exit_hard_failures[POSITION_ID] == 0
    fields = spot1_fields(rig.ctx, rig.ctx.config.spot, clock)
    assert fields["stuck_exits"] == {POSITION_ID: "quote_failed:ReadTimeout"}
    # Still retried past the threshold, and the reason follows the last refusal.
    calls_before = len(calls)
    _stub_leg(monkeypatch, "simulation_unreadable:Timeout")
    clock = clock + timedelta(seconds=61)
    monkeypatch.setattr(spot_exits, "utcnow", lambda clock=clock: clock)
    await spot_exits.spot_exits_once(rig.ctx)
    assert rig.stats.stuck_exits == {POSITION_ID: "simulation_unreadable:Timeout"}
    assert len(rig.store.orders) == calls_before + 1


async def test_a_hard_refusal_or_a_sell_resets_the_transient_streak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = exits_rig(monkeypatch, sol_out=STOP_OUT)
    rig.store.positions = [position()]
    rig.stats.exit_transient_streak[POSITION_ID] = spot_exits.STUCK_AFTER_TRANSIENT
    rig.stats.stuck_exits[POSITION_ID] = "quote_failed:ReadTimeout"
    _stub_leg(monkeypatch, "simulation_failed:x")
    await spot_exits.spot_exits_once(rig.ctx)
    assert rig.stats.exit_transient_streak.get(POSITION_ID, 0) == 0
    assert rig.stats.stuck_exits == {}


async def test_a_confirmed_sell_forgets_the_stuck_flag_with_the_rest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = exits_rig(monkeypatch, sol_out=STOP_OUT)
    rig.store.positions = [position()]
    rig.stats.stuck_exits[POSITION_ID] = "quote_failed:ReadTimeout"
    rig.stats.exit_transient_streak[POSITION_ID] = 40
    await spot_exits.spot_exits_once(rig.ctx)
    assert rig.store.closes and rig.stats.last_signature == SIGNATURE
    assert rig.stats.stuck_exits == {} and POSITION_ID not in rig.stats.exit_transient_streak


# ------------------------------------------------ Astra (T4.74-7 review) #3
async def test_a_position_closed_under_the_loop_is_never_sold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--close-manual`` (or the reconcile) closed the row between the read and
    the pending marker: ``set_exit_pending`` returns False and the leg must not
    run — a second lot of the same mint in the wallet would be sold otherwise."""
    rig = exits_rig(monkeypatch, sol_out=STOP_OUT)
    rig.store.positions = [position()]

    async def taken(_s: Any, position_id: str, **kw: Any) -> bool:
        return False

    monkeypatch.setattr(spot_exits, "set_exit_pending", taken)
    await spot_exits.spot_exits_once(rig.ctx)
    assert "sign" not in rig.log and rig.ctx.treasury_client.swap_calls == []
    assert rig.db.statuses() == ["refused"]
    assert rig.db.rows[0][1]["reason"] == "position_not_open"
    assert rig.store.closes == [] and rig.stats.exit_hard_failures.get(POSITION_ID, 0) == 0
