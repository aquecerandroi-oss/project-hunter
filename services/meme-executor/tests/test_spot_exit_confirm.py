"""KB-0172 / Open Bugs "decide stop/alvo numa cotação só" (01/10/2026): a stop
or a target decided on one Jupiter quote of the lot must hold on a second
quote — the one the sell then executes — before anything is sold.

Real-shaped incidents (labeled test data, numbers from ``Perdas-spot-1``):

* **UNI 29/09 16:01Z** — mark 0,043310 SOL (``r_now`` −8,55) while Binance
  alt/SOL was +0,39 %; the sell re-quoted 0,049838 and sold a "stop" 2 h 29 min
  early. Now: the confirmation sees 0,049838, nothing is sold.
* **NEAR 26/09 04:30:56Z** — mark +3,59 % over the spend (Binance +0,25 %), the
  "target" sell died in simulation (6001). Now: no order at all.

Bounded: a stop the confirmation keeps contradicting (or cannot read) is sold
anyway once ``STOP_CONFIRM_DEADLINE_S`` passed since the first contradiction —
the episode start is durable (``exit_intent.stop_unconfirmed_since``), so a
restart does not reset it. A target is never forced. ``time``,
``sell_requested`` and ``emergency`` never wait for a confirmation, and a phantom
target never starves the time exit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest

from hunter_core.domain.enums import KillSwitchState
from hunter_exchanges.jupiter import JupiterQuote, JupiterSwapTransaction
from hunter_meme_executor import spot_exits
from hunter_meme_executor.spot_exit_rules import (
    STOP_CONFIRM_DEADLINE_S,
    confirm_trigger,
    decide_exit,
)

from .spot_exits_rig import NOW, TOKENS, exits_rig, position
from .spot_fakes import FakeJupiter
from .spot_tx_fixtures import WIF, WSOL, as_swap, quote, sell_message

pytestmark = pytest.mark.unit

ACTIVE = KillSwitchState.ACTIVE
UNI_SPENT, UNI_RISK = 50_064_500, Decimal("0.00079")
"""Chosen so the phantom mark reads ``r_now = −8,55`` exactly, as recorded."""
UNI_PHANTOM, UNI_REQUOTE = Decimal("0.043310"), Decimal("0.049838")
NEAR_PHANTOM = Decimal("0.05") * Decimal("1.0359")  # default position: spent 0,05 SOL
NEAR_REAL = Decimal("0.05") * Decimal("1.0025")
GENUINE_STOP = Decimal("0.0490")  # below 0,05 − 0,00075


def uni(**over: Any) -> Any:
    return position(sol_spent_lamports=UNI_SPENT, initial_risk_sol=UNI_RISK, **over)


# ------------------------------------------------------------------ the pure rule
def test_the_uni_phantom_stop_is_not_confirmed_and_opens_a_stop_episode() -> None:
    pos = uni()
    assert decide_exit(pos, UNI_PHANTOM, NOW, ACTIVE) == "stop"
    verdict = confirm_trigger(pos, "stop", UNI_REQUOTE, NOW, ACTIVE)
    assert verdict.reason is None and verdict.use_quote is False
    assert verdict.outcome == "disagreed:none" and verdict.stop_since == NOW


def test_a_genuine_stop_is_confirmed_on_the_quote_that_will_be_executed() -> None:
    verdict = confirm_trigger(position(), "stop", GENUINE_STOP, NOW, ACTIVE)
    assert (verdict.reason, verdict.use_quote, verdict.outcome) == ("stop", True, "confirmed")
    assert verdict.stop_since is None


def test_the_near_phantom_target_is_not_confirmed_and_never_forced() -> None:
    pos = position()
    assert decide_exit(pos, NEAR_PHANTOM, NOW, ACTIVE) == "target"
    verdict = confirm_trigger(pos, "target", NEAR_REAL, NOW, ACTIVE)
    assert verdict.reason is None and verdict.stop_since is None
    late = confirm_trigger(
        pos, "target", NEAR_REAL, NOW, ACTIVE, stop_since=NOW - timedelta(hours=1)
    )
    assert late.reason is None, "a target is never forced"


def test_a_stop_contradicted_past_the_deadline_is_sold_anyway() -> None:
    since = NOW - timedelta(seconds=STOP_CONFIRM_DEADLINE_S)
    verdict = confirm_trigger(uni(), "stop", UNI_REQUOTE, NOW, ACTIVE, stop_since=since)
    assert (verdict.reason, verdict.use_quote) == ("stop", False)
    assert verdict.outcome == f"disagreed:none->forced_after_{STOP_CONFIRM_DEADLINE_S}s"
    inside = confirm_trigger(
        uni(), "stop", UNI_REQUOTE, NOW, ACTIVE, stop_since=since + timedelta(seconds=1)
    )
    assert inside.reason is None and inside.stop_since == since + timedelta(seconds=1), (
        "kept, not reset"
    )


def test_an_unreadable_confirmation_spends_the_stop_s_wait_but_is_not_evidence() -> None:
    verdict = confirm_trigger(uni(), "stop", None, NOW, ACTIVE)
    assert verdict.reason is None and verdict.outcome == "unavailable"
    assert verdict.stop_since == NOW
    since = NOW - timedelta(seconds=STOP_CONFIRM_DEADLINE_S + 5)
    forced = confirm_trigger(uni(), "stop", None, NOW, ACTIVE, stop_since=since)
    assert forced.reason == "stop" and forced.outcome.startswith("unavailable->forced_after_")


@pytest.mark.parametrize("first,second", [("target", "stop"), ("stop", "target")])
def test_a_flip_between_stop_and_target_is_a_stop_episode_not_a_sale(
    first: str, second: str
) -> None:
    marks = {"stop": GENUINE_STOP, "target": NEAR_PHANTOM}
    verdict = confirm_trigger(position(), first, marks[second], NOW, ACTIVE)
    assert verdict.reason is None and verdict.outcome == f"disagreed:{second}"
    assert verdict.stop_since == NOW


def test_a_phantom_target_never_starves_the_time_exit() -> None:
    old = position(entry_at=NOW - timedelta(hours=5))
    assert decide_exit(old, NEAR_PHANTOM, NOW, ACTIVE) == "target", "target wins over time"
    for confirm in (NEAR_REAL, None, GENUINE_STOP):
        verdict = confirm_trigger(old, "target", confirm, NOW, ACTIVE)
        assert (verdict.reason, verdict.use_quote) == ("time", False)


def test_an_emergency_that_arrives_meanwhile_is_not_held_by_the_confirmation() -> None:
    verdict = confirm_trigger(
        uni(), "stop", UNI_REQUOTE, NOW, KillSwitchState.EMERGENCY, auto_close_on_emergency=True
    )
    assert verdict.reason == "emergency" and verdict.use_quote is False


# ------------------------------------------------------------------ the loop
@dataclass
class SeqJupiter(FakeJupiter):
    """Answers the quotes in order (mark, confirmation, leg …); the swap is built
    from the last quote handed out, as Jupiter's ``/swap`` would."""

    outs: list[int | None] = field(default_factory=lambda: list[int | None]())
    last: int = 0

    def quote(self, **kwargs: Any) -> JupiterQuote:
        self.quote_calls += 1
        out = self.outs.pop(0)
        if out is None:
            raise RuntimeError("jupiter_down")
        self.last = out
        return quote(input_mint=WIF, output_mint=WSOL, amount=TOKENS, out=self.last)

    def swap(self, **kwargs: Any) -> JupiterSwapTransaction:
        self.swap_calls.append(kwargs)
        return as_swap(sell_message(in_amount=TOKENS, out=self.last))


def _lamports(sol: Decimal) -> int:
    return int(sol * Decimal(1_000_000_000))


def _rig(monkeypatch: pytest.MonkeyPatch, outs: list[Decimal], *, sol_out: Decimal) -> Any:
    first = _lamports(outs[0]) if outs else 1
    jupiter = SeqJupiter(
        quote(input_mint=WIF, output_mint=WSOL, amount=TOKENS, out=first),
        as_swap(sell_message(in_amount=TOKENS, out=first)),
        outs=[_lamports(o) for o in outs],
    )
    return exits_rig(monkeypatch, sol_out=_lamports(sol_out), jupiter=jupiter)


async def test_the_uni_incident_sells_nothing_and_records_both_quotes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = _rig(monkeypatch, [UNI_PHANTOM, UNI_REQUOTE], sol_out=UNI_REQUOTE)
    await spot_exits.manage_position(rig.ctx, rig.ctx.config.spot, rig.stats, uni(), now=NOW)
    assert rig.store.orders == [] and rig.store.pending_set == [] and rig.store.closes == []
    assert rig.ctx.treasury_client.quote_calls == 2 and rig.ctx.treasury_client.swap_calls == []
    assert rig.store.marks[-1] == ("p1", UNI_REQUOTE, "trigger_unconfirmed:stop:disagreed:none")
    assert rig.store.episodes == [("p1", NOW)], "the episode start is durable"
    assert "p1" not in rig.stats.exit_attempts and "p1" not in rig.stats.exit_backoff_until


async def test_a_genuine_stop_sells_on_the_confirming_quote(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = _rig(monkeypatch, [GENUINE_STOP, GENUINE_STOP], sol_out=GENUINE_STOP)
    await spot_exits.manage_position(rig.ctx, rig.ctx.config.spot, rig.stats, position(), now=NOW)
    assert rig.ctx.treasury_client.quote_calls == 2, "mark + confirmation; the leg re-uses it"
    (order,) = rig.store.orders
    assert order["intent"]["reason"] == "stop" and order["attempt"] == 1
    confirmation = order["intent"]["trigger_confirmation"]
    assert confirmation["outcome"] == "confirmed"
    assert Decimal(confirmation["confirm_mark_sol"]) == GENUINE_STOP
    assert confirmation["confirm_r_now"] is not None
    assert rig.store.closes[0]["exit_payload"]["reason"] == "stop"


async def test_the_near_incident_sends_no_order(monkeypatch: pytest.MonkeyPatch) -> None:
    rig = _rig(monkeypatch, [NEAR_PHANTOM, NEAR_REAL], sol_out=NEAR_REAL)
    await spot_exits.manage_position(rig.ctx, rig.ctx.config.spot, rig.stats, position(), now=NOW)
    assert rig.store.orders == [] and rig.ctx.treasury_client.swap_calls == []
    assert rig.store.episodes == [], "a target never opens a stop episode"


async def test_a_stop_past_its_deadline_is_sold_with_a_fresh_quote(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    since = NOW - timedelta(seconds=STOP_CONFIRM_DEADLINE_S + 1)
    pos = uni(exit_intent={"stop_unconfirmed_since": since.isoformat()})
    rig = _rig(monkeypatch, [UNI_PHANTOM, UNI_REQUOTE, UNI_REQUOTE], sol_out=UNI_REQUOTE)
    await spot_exits.manage_position(rig.ctx, rig.ctx.config.spot, rig.stats, pos, now=NOW)
    assert rig.ctx.treasury_client.quote_calls == 3, "the forced leg quotes for itself"
    (order,) = rig.store.orders
    assert order["intent"]["reason"] == "stop"
    assert "forced_after_" in order["intent"]["trigger_confirmation"]["outcome"]


async def test_a_phantom_target_past_the_horizon_sells_for_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pos = position(entry_at=NOW - timedelta(hours=5))
    rig = _rig(monkeypatch, [NEAR_PHANTOM, NEAR_REAL, NEAR_REAL], sol_out=NEAR_REAL)
    await spot_exits.manage_position(rig.ctx, rig.ctx.config.spot, rig.stats, pos, now=NOW)
    (order,) = rig.store.orders
    assert order["intent"]["reason"] == "time" and order["intent"]["slippage_bps"] == 50


async def test_a_discarded_confirmation_spends_no_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two phantom targets, then a real one: attempt 1, normal tolerance (never panic)."""
    target = Decimal("0.0512")
    rig = _rig(
        monkeypatch,
        [NEAR_PHANTOM, NEAR_REAL, NEAR_PHANTOM, NEAR_REAL, target, target],
        sol_out=target,
    )
    for _ in range(3):
        await spot_exits.manage_position(
            rig.ctx, rig.ctx.config.spot, rig.stats, position(), now=NOW
        )
    (order,) = rig.store.orders
    assert order["attempt"] == 1 and order["intent"]["slippage_bps"] == 50
    assert order["intent"]["reason"] == "target"


async def test_a_recovered_mark_closes_the_stop_episode(monkeypatch: pytest.MonkeyPatch) -> None:
    pos = uni(exit_intent={"stop_unconfirmed_since": NOW.isoformat()})
    rig = _rig(monkeypatch, [UNI_REQUOTE], sol_out=UNI_REQUOTE)
    await spot_exits.manage_position(rig.ctx, rig.ctx.config.spot, rig.stats, pos, now=NOW)
    assert rig.store.episodes == [("p1", None)] and rig.store.orders == []


async def test_a_failed_mark_is_not_a_recovery(monkeypatch: pytest.MonkeyPatch) -> None:
    pos = uni(exit_intent={"stop_unconfirmed_since": NOW.isoformat()})
    rig = _rig(monkeypatch, [], sol_out=UNI_REQUOTE)  # the mark's quote raises (no reply left)
    await spot_exits.manage_position(rig.ctx, rig.ctx.config.spot, rig.stats, pos, now=NOW)
    assert rig.store.episodes == [] and rig.store.orders == []


async def test_a_manual_sell_request_needs_no_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    pos = uni(sell_requested_at=NOW, sell_requested_by="Everton")
    rig = _rig(monkeypatch, [UNI_PHANTOM, UNI_REQUOTE], sol_out=UNI_REQUOTE)
    await spot_exits.manage_position(rig.ctx, rig.ctx.config.spot, rig.stats, pos, now=NOW)
    (order,) = rig.store.orders
    assert order["intent"]["reason"] == "sell_requested"
    assert order["intent"]["trigger_confirmation"] is None
    assert rig.ctx.treasury_client.quote_calls == 2, "mark + the leg's own quote"


# ------------------------------------------- the episode's whole life (Astra, diff review)
def test_an_unreadable_confirmation_of_a_target_keeps_an_open_stop_episode() -> None:
    since = NOW - timedelta(seconds=20)
    kept = confirm_trigger(position(), "target", None, NOW, ACTIVE, stop_since=since)
    assert kept.reason is None and kept.stop_since == since, "absence of data is no recovery"
    cleared = confirm_trigger(position(), "target", NEAR_REAL, NOW, ACTIVE, stop_since=since)
    assert cleared.stop_since is None, "a readable quote above the stop is the recovery"


def test_alternating_target_and_stop_never_resets_the_deadline() -> None:
    """t=0 alvo→stop opens; t=20 alvo→ilegível keeps; t=40 alvo→stop continues; t=60 forced."""
    pos, since = position(), None
    steps = [(0, GENUINE_STOP), (20, None), (40, GENUINE_STOP), (60, GENUINE_STOP)]
    verdict = None
    for offset, confirm in steps:
        at = NOW + timedelta(seconds=offset)
        verdict = confirm_trigger(pos, "target", confirm, at, ACTIVE, stop_since=since)
        since = verdict.stop_since if verdict.reason is None else None
    assert verdict is not None and verdict.reason == "stop"
    assert verdict.outcome == f"disagreed:stop->forced_after_{STOP_CONFIRM_DEADLINE_S}s"


async def test_an_overdue_stop_is_tried_even_when_the_mark_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Overdue episode, the mark fails and the confirmation fails too: forced."""
    since = NOW - timedelta(seconds=STOP_CONFIRM_DEADLINE_S + 10)
    pos = uni(exit_intent={"stop_unconfirmed_since": since.isoformat()})
    rig = _rig(monkeypatch, [UNI_REQUOTE], sol_out=UNI_REQUOTE)
    rig.ctx.treasury_client.outs[:0] = [None, None]  # mark and confirmation fail
    await spot_exits.manage_position(rig.ctx, rig.ctx.config.spot, rig.stats, pos, now=NOW)
    (order,) = rig.store.orders
    assert order["intent"]["reason"] == "stop"
    assert "unavailable->forced_after_" in order["intent"]["trigger_confirmation"]["outcome"]


async def test_the_uni_at_t70_with_a_429_mark_and_a_normal_requote_sells_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Code review (MEDIUM): the injected ``stop`` of an overdue episode is not
    evidence — a readable confirmation above the stop line closes the episode."""
    since = NOW - timedelta(seconds=70)
    pos = uni(exit_intent={"stop_unconfirmed_since": since.isoformat()})
    rig = _rig(monkeypatch, [UNI_REQUOTE], sol_out=UNI_REQUOTE)
    rig.ctx.treasury_client.outs.insert(0, None)  # the mark: HTTP 429
    await spot_exits.manage_position(rig.ctx, rig.ctx.config.spot, rig.stats, pos, now=NOW)
    assert rig.store.orders == [] and rig.ctx.treasury_client.swap_calls == []
    assert rig.store.episodes == [("p1", None)], "the readable re-quote is the recovery"


async def test_an_overdue_stop_with_a_failed_mark_and_a_stop_requote_is_confirmed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    since = NOW - timedelta(seconds=70)
    pos = uni(exit_intent={"stop_unconfirmed_since": since.isoformat()})
    rig = _rig(monkeypatch, [GENUINE_STOP], sol_out=GENUINE_STOP)
    rig.ctx.treasury_client.outs.insert(0, None)
    await spot_exits.manage_position(rig.ctx, rig.ctx.config.spot, rig.stats, pos, now=NOW)
    (order,) = rig.store.orders
    assert order["intent"]["trigger_confirmation"]["outcome"] == "confirmed"
    assert rig.ctx.treasury_client.quote_calls == 2, "the leg executes the confirming quote"


def test_the_overdue_stop_without_a_mark_is_not_evidence() -> None:
    since = NOW - timedelta(seconds=70)
    pure = confirm_trigger(
        uni(), "stop", UNI_REQUOTE, NOW, ACTIVE, stop_since=since, decided_on_mark=False
    )
    assert pure.reason is None and pure.stop_since is None
    blind = confirm_trigger(
        uni(), "stop", None, NOW, ACTIVE, stop_since=since, decided_on_mark=False
    )
    assert blind.reason == "stop" and blind.outcome.startswith("unavailable->forced_after_")


async def test_a_young_episode_with_a_failed_mark_still_waits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pos = uni(exit_intent={"stop_unconfirmed_since": NOW.isoformat()})
    rig = _rig(monkeypatch, [UNI_REQUOTE], sol_out=UNI_REQUOTE)
    rig.ctx.treasury_client.outs.insert(0, None)
    await spot_exits.manage_position(rig.ctx, rig.ctx.config.spot, rig.stats, pos, now=NOW)
    assert rig.store.orders == [] and rig.ctx.treasury_client.quote_calls == 1
