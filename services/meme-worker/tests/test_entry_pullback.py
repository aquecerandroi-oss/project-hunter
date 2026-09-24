"""T4.91 (H-016, EXP-M24), pure (no Docker): the entry at the pullback — the
params, the running max, the trigger, the window boundary, the bounded book
and the recheck filter. Known values on synthetic tapes; R77's own example
(``.claude/state/r77/test_r77.py``) is reproduced so the live mechanism and
the study agree on what "the first trade that touches the pullback" means.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_exchanges.pumpfun.models import NormalizedCurveTrade
from hunter_meme_worker.entry_pullback import (
    ARMED,
    DROPPED_CAP,
    EVENT_LANE_ONLY,
    FEED_LOST,
    NO_PULLBACK,
    PULLBACK_ARM_RULE_SET_ID,
    STALL_S,
    ArmedEntry,
    EntryPullback,
    entry_pullback_of,
    fatal_refusals,
    outcome_of,
    price_of,
)
from hunter_meme_worker.entry_pullback_book import PullbackBook
from hunter_meme_worker.gate_refusal_trail import RefusalTrailRow

pytestmark = pytest.mark.unit

T0 = datetime(2026, 9, 24, 12, 0, 0, tzinfo=UTC)
VTOK = Decimal("1000000000")


def at(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


def _entry(
    *,
    mint: str = "MINT",
    spec_id: str = "rs-1",
    pct: str = "3",
    window_s: int = 20,
    m0: str = "100",
) -> ArmedEntry:
    return ArmedEntry(
        spec_id=spec_id,
        mint=mint,
        params=EntryPullback(pct=Decimal(pct), window_s=window_s),
        t0=T0,
        armed_max=Decimal(m0),
        gaps=0,
        creator_sells=0,
        draft=None,  # type: ignore[arg-type]  # the pure tests never read it
        row=None,  # type: ignore[arg-type]
    )


def _trade(price: str, *, s: float, mint: str = "MINT", trader: str = "X") -> NormalizedCurveTrade:
    """A fill whose post-trade marginal price (vsol/vtok) is ``price``."""
    return NormalizedCurveTrade(
        mint=mint,
        slot=1000 + int(s * 10),
        signature=f"sig-{s}-{price}",
        trader=trader,
        side="buy",
        lamports=Decimal(1_000_000_000),
        token_amount=Decimal(1_000_000),
        virtual_sol_reserves=Decimal(price) * VTOK,
        virtual_token_reserves=VTOK,
        real_sol_reserves=Decimal("10"),
        real_token_reserves=Decimal("700000000"),
        creator="CREATOR",
        mayhem=False,
        block_time=at(s),
        received_at=at(s),
    )


# ---- params --------------------------------------------------------------------------


def test_absent_params_mean_no_pullback() -> None:
    assert entry_pullback_of({"clock": "15s"}, clock="15s") is None


def test_the_percent_is_the_switch_so_the_window_can_be_written_first() -> None:
    """``--set-param`` writes one key per call and refuses a document the Lab
    cannot load: the window alone must load (inert), then the percent turns it on."""
    assert entry_pullback_of({"entry_pullback_window_s": 60}, clock="15s") is None
    assert entry_pullback_of({"entry_pullback_window_s": 60}, clock="1m") is None
    off = {"entry_pullback_pct": None, "entry_pullback_window_s": 60}  # ``pct=null`` turns it off
    assert entry_pullback_of(off, clock="15s") is None


def test_both_params_parse_to_decimal_and_int() -> None:
    parsed = entry_pullback_of(
        {"entry_pullback_pct": "5", "entry_pullback_window_s": 60}, clock="15s"
    )
    assert parsed == EntryPullback(pct=Decimal("5"), window_s=60)


@pytest.mark.parametrize(
    ("params", "error"),
    [
        ({"entry_pullback_pct": "5"}, ValueError),  # the switch without its window
        ({"entry_pullback_window_s": "60"}, TypeError),  # an inert window is still validated
        ({"entry_pullback_pct": 5.0, "entry_pullback_window_s": 60}, TypeError),  # a float
        ({"entry_pullback_pct": 5, "entry_pullback_window_s": 60}, TypeError),  # a JSON number
        ({"entry_pullback_pct": "NaN", "entry_pullback_window_s": 60}, ValueError),
        ({"entry_pullback_pct": "Infinity", "entry_pullback_window_s": 60}, ValueError),
        ({"entry_pullback_pct": "5", "entry_pullback_window_s": "60"}, TypeError),  # not a count
        ({"entry_pullback_pct": "5", "entry_pullback_window_s": True}, TypeError),
        ({"entry_pullback_pct": "0", "entry_pullback_window_s": 60}, ValueError),
        ({"entry_pullback_pct": "100", "entry_pullback_window_s": 60}, ValueError),
        ({"entry_pullback_pct": "5", "entry_pullback_window_s": 0}, ValueError),
        ({"entry_pullback_pct": "5", "entry_pullback_window_s": 601}, ValueError),
    ],
)
def test_bad_params_never_load(params: dict[str, object], error: type[Exception]) -> None:
    with pytest.raises(error):
        entry_pullback_of(params, clock="15s")


@pytest.mark.parametrize("clock", ["1m", "refused", "event"])
def test_only_the_event_lanes_clock_can_wait_for_a_pullback(clock: str) -> None:
    with pytest.raises(ValueError, match="15s"):
        entry_pullback_of({"entry_pullback_pct": "5", "entry_pullback_window_s": 60}, clock=clock)


def test_price_is_the_marginal_price_and_unknown_on_an_empty_curve() -> None:
    assert price_of(Decimal("30"), Decimal("1000000000")) == Decimal("3E-8")
    assert price_of(Decimal("0"), Decimal("1")) is None
    assert price_of(Decimal("1"), Decimal("0")) is None


# ---- the trigger (R77's own known values) ---------------------------------------------


def test_the_running_max_not_the_t0_price_sets_the_threshold() -> None:
    """R77: t0 at 100, rises to 110, 108, then 106.6 <= 110 x 0.97 = 106.7."""
    entry = _entry(pct="3")
    fired = [entry.observe(Decimal(p), at(s)) for s, p in ((1, "105"), (2, "110"), (3, "108"))]
    assert fired == [False, False, False]
    assert entry.observe(Decimal("106.6"), at(4)) is True
    assert (entry.trigger_price, entry.max_at_trigger, entry.trigger_at) == (
        Decimal("106.6"),
        Decimal("110"),
        at(4),
    )
    assert entry.observe(Decimal("50"), at(5)) is False  # fired once, never again


def test_five_percent_waits_for_the_deeper_trade() -> None:
    entry = _entry(pct="5")
    for s, p in ((1, "105"), (2, "110"), (3, "108"), (4, "106.6")):
        assert entry.observe(Decimal(p), at(s)) is False
    assert entry.observe(Decimal("90"), at(5)) is True


def test_the_initial_max_is_the_state_at_t0_and_the_threshold_is_inclusive() -> None:
    entry = _entry(pct="3", m0="100")
    assert entry.observe(Decimal("97"), at(0.5)) is True  # 97 <= 100 x 0.97, equal counts


def test_a_frame_received_by_t0_but_folded_late_is_the_t0_state_and_never_fires() -> None:
    """A backlog: the frame was received before the decision instant but the
    lane folded it after arming. It is part of the state at ``t0`` (R77: the
    last point <= t0) — it refreshes ``M`` and never fires, so no trigger can
    carry ``trigger_at <= t0``."""
    entry = _entry(pct="3", m0="100")
    assert entry.observe(Decimal("96"), T0 - timedelta(seconds=1)) is False
    assert entry.observe(Decimal("95"), T0) is False  # received exactly at t0: still the state
    assert (entry.armed_max, entry.t0_price) == (Decimal("95"), Decimal("95"))
    assert entry.observe(Decimal("93"), at(1)) is False  # 93 > 95 x 0.97 = 92.15
    assert entry.observe(Decimal("92.15"), at(2)) is True
    assert entry.trigger_at == at(2) and entry.max_at_trigger == Decimal("95")


def test_the_window_end_is_inclusive_and_nothing_after_it_fires() -> None:
    """``(t0, t0 + W]`` on ``received_at``: a trade at exactly the deadline is
    inside; one microsecond later is not."""
    inside = _entry(window_s=20)
    assert inside.observe(Decimal("90"), at(20)) is True
    outside = _entry(window_s=20)
    late = at(20) + timedelta(microseconds=1)
    assert outside.observe(Decimal("90"), late) is False
    assert outside.trigger_price is None


def test_the_deepest_pullback_seen_is_kept_for_the_no_pullback_row() -> None:
    entry = _entry(pct="5")
    for s, p in ((1, "110"), (2, "106"), (3, "108"), (4, "120"), (5, "117")):
        assert entry.observe(Decimal(p), at(s)) is False
    # 106 / 110 = 3.6363...% below the max then; 117 / 120 = 2.5 %: the deepest is 3.63 %.
    assert entry.deepest_pct.quantize(Decimal("0.0001")) == Decimal("3.6364")


@pytest.mark.parametrize("seed", range(10))
def test_the_trigger_never_depends_on_the_future(seed: int) -> None:
    """No look-ahead: rewriting every trade after the trigger (or after the
    deadline, when nothing fired) never moves the trigger."""
    rnd = random.Random(seed)
    prices = [Decimal(100)]
    for _ in range(80):
        step = Decimal(str(round(rnd.uniform(-0.04, 0.04), 4)))
        prices.append(max(Decimal(1), prices[-1] * (1 + step)))

    def first_fire(series: list[Decimal]) -> int | None:
        entry = _entry(pct="5", window_s=60)
        for k, price in enumerate(series[1:], start=1):
            if entry.observe(price, at(k)):
                return k
        return None

    k = first_fire(prices)
    cut = k if k is not None else 60
    future = [p * Decimal(str(round(rnd.uniform(0.3, 3.0), 3))) for p in prices[cut + 1 :]]
    assert first_fire(prices[: cut + 1] + future) == k


# ---- the book: bounded, one arming per (set, mint), O(1) for an unarmed mint -------------


def test_the_book_fires_only_the_armed_mint_and_spends_it() -> None:
    book = PullbackBook()
    assert book.arm(_entry(mint="A")) is True
    book.observe_trade("B", _trade("50", s=1, mint="B"))  # not armed: nothing happens
    assert book.pop_fired("B") == []
    book.observe_trade("A", _trade("96", s=1, mint="A"))
    fired = book.pop_fired("A")
    assert [e.mint for e in fired] == ["A"] and book.triggered == 1
    assert book.pop_fired("A") == []
    assert book.arm(_entry(mint="A")) is False, "spent: one arming per (set, mint)"
    assert book.armed == 1 and book.size == 0


def test_the_same_mint_is_armed_once_per_set() -> None:
    book = PullbackBook()
    assert book.arm(_entry(mint="A", spec_id="rs-1")) is True
    assert book.arm(_entry(mint="A", spec_id="rs-1")) is False
    assert book.arm(_entry(mint="A", spec_id="rs-2")) is True
    assert book.size == 2


def test_the_cap_drops_the_oldest_with_a_counter() -> None:
    book = PullbackBook(max_armed=2)
    first, second, third = (_entry(mint=m) for m in ("A", "B", "C"))
    second.t0 = T0 + timedelta(seconds=1)
    third.t0 = T0 + timedelta(seconds=2)
    for entry in (first, second, third):
        assert book.arm(entry) is True
    assert book.size == 2 and book.dropped_cap == 1
    assert not book.is_armed("A") and book.is_armed("B") and book.is_armed("C")
    (dropped,) = [row for row, _tape in book.drain_trail()]
    assert (dropped.mint, dropped.refusal, dropped.as_of) == (
        "A",
        DROPPED_CAP,
        T0 + timedelta(seconds=2),
    )


def test_no_pullback_only_once_the_lane_processed_a_frame_received_after_the_deadline() -> None:
    """The queue is FIFO in receipt order: a processed frame received after the
    deadline proves every frame received by the deadline was folded — a trade
    that touched the pullback in time but waited in the queue is never lost."""
    book = PullbackBook()
    book.arm(_entry(window_s=20))
    book.mark_processed(at(19.9))
    assert book.pop_due(at(25)) == []  # the clock passed the deadline, the queue did not
    book.mark_processed(at(20))
    assert book.pop_due(at(25)) == []  # the deadline itself is inside the window
    book.mark_processed(at(20.001))
    due = book.pop_due(at(25))
    assert [(e.mint, outcome) for e, outcome in due] == [("MINT", NO_PULLBACK)]
    assert book.size == 0
    assert book.arm(_entry(window_s=20)) is False, "an expired arming is spent too"


def test_a_stalled_queue_ends_as_feed_lost_never_as_no_pullback() -> None:
    book = PullbackBook()
    book.arm(_entry(window_s=20))
    book.mark_processed(at(10))
    assert book.pop_due(at(20 + STALL_S - 1)) == []
    due = book.pop_due(at(20 + STALL_S))
    assert [outcome for _e, outcome in due] == [FEED_LOST]


def test_a_fired_entry_is_never_also_expired() -> None:
    book = PullbackBook()
    book.arm(_entry(window_s=20))
    book.observe_trade("MINT", _trade("90", s=5))
    book.mark_processed(at(60))
    assert book.pop_due(at(60)) == []
    assert len(book.pop_fired("MINT")) == 1


def test_the_trail_queue_is_bounded() -> None:
    book = PullbackBook(max_trail=2)
    for k in range(3):
        book.queue_trail(RefusalTrailRow(at(k), "rs-1", "MINT", ARMED), None)
    assert [row.as_of for row, _tape in book.drain_trail()] == [at(1), at(2)]
    assert book.trail_dropped == 1 and book.drain_trail() == []


def test_heartbeat_names_every_counter() -> None:
    fields = PullbackBook().heartbeat_fields()
    assert set(fields) == {
        "event_gate_pullback_armed_now",
        "event_gate_pullback_armed_total",
        "event_gate_pullback_triggered_total",
        "event_gate_pullback_proposed_total",
        "event_gate_pullback_not_inserted_total",
        "event_gate_pullback_expired_no_pullback_total",
        "event_gate_pullback_censored_total",
        "event_gate_pullback_killed_by_recheck_total",
        "event_gate_pullback_dropped_cap_total",
        "event_gate_pullback_trail_dropped_total",
        "event_gate_pullback_trail_write_failed_total",
    }


# ---- the recheck at the trigger ---------------------------------------------------------


def test_momentum_refusals_were_judged_at_t0_and_never_kill() -> None:
    waived = ["flow_not_positive", "progress_not_rising", "sells_ratio_above_max", "age_above_max"]
    assert fatal_refusals(waived) == ()


@pytest.mark.parametrize(
    "refusal",
    [
        "creator_is_net_seller",
        "creator_net_seller_unknown",
        "creator_serial",
        "creator_repeat_dumper",
        "pedigree_unknown",
        "curve_complete",
        "already_migrated",
        "mayhem_curve",
        "already_open",
        "buyers_unknown",
        "recent_drawdown",  # real SOL lost, its own window: not the price pullback (Astra)
        "participation_above_cap",  # the ticket against the volume now
        "curve_volume_1m_zero",
        "buys_1m_above_max",
        "no_snapshot_for_quote",
        "a_criterion_added_after_t4_91",
    ],
)
def test_anything_else_kills_the_entry_fail_closed(refusal: str) -> None:
    assert fatal_refusals(["flow_not_positive", refusal]) == (refusal,)


def test_the_fifteen_second_lane_names_what_it_leaves_to_the_event_lane() -> None:
    assert EVENT_LANE_ONLY == "entry_pullback_event_lane_only"


@pytest.mark.parametrize(
    ("reason", "outcome"),
    [
        ("feed_gap", "pullback_censored:feed_gap"),
        ("feed_lost", "pullback_censored:feed_lost"),
        ("spec_changed", "pullback_censored:spec_changed"),
        ("no_base_row", "pullback_censored:no_base_row"),
        ("creator_flow_overflow", "pullback_censored:creator_flow_overflow"),
        ("creator_sold_during_wait", "pullback_killed:creator_sold_during_wait"),
        ("creator_is_net_seller", "pullback_killed:creator_is_net_seller"),
    ],
)
def test_an_operational_loss_is_censored_a_judgement_kills(reason: str, outcome: str) -> None:
    """Astra (diff review): the same feed loss must get the same name whether
    a trade touched the pullback afterwards or not — censored, out of both
    sides of the pairing; only a judgement (the creator, the gate) is a kill."""
    assert outcome_of(reason) == outcome
    assert FEED_LOST == "pullback_censored:feed_lost"


def test_the_armed_draft_shares_no_mutable_reasons_with_the_desks() -> None:
    """risk-engine-guardian (LOW): the ``t0`` draft is held up to 60 s and its
    reasons re-emitted — never the same dicts another set's draft carries."""
    from dataclasses import dataclass, field
    from types import SimpleNamespace
    from typing import Any

    from hunter_meme_worker.entry_pullback_book import arm_from_gate

    shared_block: dict[str, Any] = {"feature": "flow", "net_sol_flow_1m": "0.9"}
    tape_block: dict[str, Any] = {"feature": "decision_tape", "derived": {"n": 1}}

    @dataclass
    class Draft:
        reasons: list[dict[str, Any]] = field(default_factory=lambda: [shared_block])

    class Tape:
        def reasons_block(self) -> dict[str, Any]:
            return tape_block

    book = PullbackBook()
    spec = SimpleNamespace(id="rs", entry_pullback=EntryPullback(Decimal(3), 60))

    def creator_flow(_now: object) -> SimpleNamespace:
        return SimpleNamespace(sells=0)

    state = SimpleNamespace(gaps=0, creator_flow=creator_flow)
    row = SimpleNamespace(mint="MINT")
    armed = arm_from_gate(
        book,
        [Draft()],  # type: ignore[list-item]
        spec=spec,  # type: ignore[arg-type]
        row=row,  # type: ignore[arg-type]
        state=state,  # type: ignore[arg-type]
        t0_price=Decimal(1),
        tape=Tape(),  # type: ignore[arg-type]
        offer_tape=False,
        now=T0,
    )
    assert armed
    (entry,) = book._by_mint["MINT"].values()  # pyright: ignore[reportPrivateUsage]
    reasons = entry.draft.reasons
    assert reasons == [shared_block, tape_block]
    assert reasons[0] is not shared_block and reasons[1] is not tape_block
    assert reasons[1]["derived"] is not tape_block["derived"]


def test_the_desks_pedigree_subtracts_the_pullback_arms_paper_bets() -> None:
    """T4.85's own precedent (``test_refused_probe_step``): ``recuo_v1/1``'s
    bets stay open later than the desk's shadow on the same mint and can
    witness a creator sale the desk's never saw — counted in
    ``creator_prior_dump_count`` they would change ``operator/5``'s
    ``creator_repeat_dumper`` refusals. Subtracted by id, in both subqueries."""
    from hunter_meme_worker import lab_repo_fast

    sql = str(lab_repo_fast._PEDIGREE)  # pyright: ignore[reportPrivateUsage]
    assert sql.count("pb.rule_set_id <> :pullback_rule_set_id") == 1
    assert sql.count("pb2.rule_set_id <> :pullback_rule_set_id") == 1
    assert PULLBACK_ARM_RULE_SET_ID == "01994d00-6c1a-7000-8000-00000000001d", "0063's own id"


# ---- the rule set reads it (absent = the set as it always was) ---------------------------


def test_the_rule_set_reads_the_pullback_and_absent_params_change_nothing() -> None:
    from .test_proposals_flow import _flow_spec  # pyright: ignore[reportPrivateUsage]

    plain = _flow_spec()
    assert plain.entry_pullback is None
    armed = _flow_spec(entry_pullback_pct="5", entry_pullback_window_s=60)
    assert armed.entry_pullback == EntryPullback(pct=Decimal("5"), window_s=60)
    assert armed.suggested() == plain.suggested(), "the desk's pre-fill never carries it"
    with pytest.raises(ValueError, match="15s"):
        _flow_spec(clock="1m", entry_pullback_pct="5", entry_pullback_window_s=60)
