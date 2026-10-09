"""The copy lane's in-memory decision (H-037, EXP-M28 design §3.2/§3.4): an entry only on the first
observation of a (leader, mint) pair that is a first purchase of at least the floor, one copy per
(stratum, mint) key forever, the day and open ceilings, exits on the leader's peak drop or full sell,
gaps censor, an unconfirmed event is acted on and validated later — and invalidated, not dropped.
Pure: no IO, no clock but the argument."""

from __future__ import annotations

from datetime import timedelta

import pytest

from hunter_exchanges.pumpfun.leader_events import LeaderEvent
from hunter_meme_worker.copy_book import CopyBook
from hunter_meme_worker.copy_events import (
    CENSOR_REASONS,
    CensorEntry,
    CloseIntent,
    ConfirmIntent,
    InvalidateIntent,
    OpenIntent,
    RejectEntry,
)

from .copy_support import LEADER_A, LEADER_B, MINT_1, MINT_2, T0, buy, gap, make_spec, sell

pytestmark = pytest.mark.unit


def _book(**overrides: object) -> CopyBook:
    return CopyBook(make_spec(**overrides), t0=T0 - timedelta(hours=1))


def _opened(book: CopyBook, event_buy: LeaderEvent | None = None) -> OpenIntent:
    decision = book.on_event(event_buy or buy(), T0 + timedelta(milliseconds=3))
    assert len(decision.jobs) == 1 and isinstance(decision.jobs[0], OpenIntent)
    return decision.jobs[0]


def test_the_first_buy_of_a_followed_wallet_opens_a_copy_priced_after_the_latency() -> None:
    book = _book(exec_latency_s="1.65")
    event = buy()
    now = T0 + timedelta(milliseconds=3)
    intent = book.on_event(event, now).jobs[0]
    assert isinstance(intent, OpenIntent)
    assert intent.mint == MINT_1 and intent.leader.wallet == LEADER_A
    assert intent.leader.stratum == "regra" and intent.leader.signature == event.signature
    assert intent.decided_at == now
    assert intent.target_at == now + timedelta(milliseconds=1650)  # decision + declared latency
    assert book.open_count == 1 and book.occupied("regra") == 1


def test_a_wallet_outside_the_frozen_set_is_ignored_and_named() -> None:
    decision = _book().on_event(buy("Stranger1111111111111111111111111111111111"), T0)
    assert decision.jobs == [] and decision.skipped == "unknown_wallet"


def test_a_buy_below_the_trigger_floor_is_a_rejected_funnel_row_not_a_copy() -> None:
    book = _book()
    job = book.on_event(buy(spent_sol="0.099"), T0).jobs[0]
    assert isinstance(job, RejectEntry) and job.reason == "abaixo_do_piso"
    # the pair has been observed: a later, bigger buy is not "the first" any more
    assert book.on_event(buy(spent_sol="0.5"), T0).skipped == "already_observed"
    assert isinstance(book.on_event(buy(spent_sol="0.10", mint=MINT_2), T0).jobs[0], OpenIntent)


def test_adding_to_a_position_held_before_is_not_a_first_purchase() -> None:
    book = _book()
    job = book.on_event(buy(position_after=3_000_000, position_before=2_000_000), T0).jobs[0]
    assert isinstance(job, RejectEntry) and job.reason == "nao_primeira"
    assert book.open_count == 0


def test_one_copy_per_stratum_and_mint_forever_even_after_it_closed() -> None:
    book = _book()
    first = _opened(book)
    book.mark_open(first.key, bet_id="bet-1", entry_at=T0 + timedelta(seconds=1))
    # another leader of the same stratum buys the same mint while we hold it
    held = book.on_event(buy(LEADER_B, at=T0 + timedelta(seconds=2)), T0).jobs[0]
    assert isinstance(held, RejectEntry) and held.reason == "co_compra"
    book.on_event(sell(at=T0 + timedelta(seconds=10)), T0 + timedelta(seconds=10))
    book.mark_closed(first.key)
    # the key is consumed by the admitted attempt, not only while the mint is held
    later = book.on_event(buy(LEADER_B, mint=MINT_1, at=T0 + timedelta(seconds=20)), T0).skipped
    assert later == "already_observed"
    fresh = _book()
    fresh.restore_consumed("regra", MINT_2)
    again = fresh.on_event(buy(LEADER_A, MINT_2), T0).jobs[0]
    assert isinstance(again, RejectEntry) and again.reason == "co_compra"


def test_only_the_first_observation_of_a_pair_is_a_funnel_fact() -> None:
    book = _book()
    book.on_event(buy(), T0)
    assert book.on_event(buy(at=T0 + timedelta(seconds=5)), T0).skipped == "already_observed"


def test_the_leader_selling_everything_closes_our_copy() -> None:
    book = _book()
    opened = _opened(book)
    book.mark_open(opened.key, bet_id="b", entry_at=T0 + timedelta(seconds=1))
    sale = sell(position_after=0, at=T0 + timedelta(seconds=30))
    job = book.on_event(sale, T0 + timedelta(seconds=30)).jobs[0]
    assert isinstance(job, CloseIntent) and job.reason == "leader_exit_full"
    assert job.leader is not None and job.leader.signature == sale.signature
    assert job.censor is None and job.key == opened.key


def test_a_partial_sell_above_the_drop_fraction_does_not_close_but_at_it_does() -> None:
    book = _book()  # exit when position_after <= 50 % of the peak
    opened = _opened(book, buy(position_after=1_000_000))
    book.mark_open(opened.key, bet_id="b", entry_at=T0)
    small = book.on_event(sell(position_after=600_000, at=T0 + timedelta(seconds=5)), T0)
    assert small.jobs == [] and small.skipped == "exit_not_triggered"
    big = book.on_event(sell(position_after=500_000, at=T0 + timedelta(seconds=9)), T0)
    assert isinstance(big.jobs[0], CloseIntent) and big.jobs[0].reason == "leader_peak_drop"


def test_a_later_leader_add_raises_the_peak_the_drop_is_measured_from() -> None:
    book = _book()
    opened = _opened(book, buy(position_after=1_000_000))
    book.mark_open(opened.key, bet_id="b", entry_at=T0)
    add = book.on_event(
        buy(position_after=2_000_000, position_before=1_000_000, at=T0 + timedelta(seconds=3)), T0
    )
    assert add.skipped == "already_observed"  # never a second copy ...
    cut = book.on_event(sell(position_after=900_000, at=T0 + timedelta(seconds=9)), T0)
    assert isinstance(cut.jobs[0], CloseIntent)  # ... but the peak moved: 900k <= 50 % of 2M


def test_the_design_counterexample_buy_100_sell_40_rebuy_40_sell_31_does_not_exit() -> None:
    """The H-030 policy exits (71 of 140 sold > half); this lane measures position against peak."""
    book = _book()
    opened = _opened(book, buy(position_after=100, position_before=0))
    book.mark_open(opened.key, bet_id="b", entry_at=T0)
    assert book.on_event(sell(position_after=60, at=T0 + timedelta(seconds=1)), T0).jobs == []
    book.on_event(buy(position_after=100, position_before=60, at=T0 + timedelta(seconds=2)), T0)
    last = book.on_event(sell(position_after=69, at=T0 + timedelta(seconds=3)), T0)
    assert last.jobs == [] and last.skipped == "exit_not_triggered"  # 69 of a 100 peak


def test_a_sell_of_a_mint_we_never_copied_or_of_another_leader_is_ignored() -> None:
    book = _book()
    assert book.on_event(sell(), T0).skipped == "sell_without_entry"
    _opened(book)
    assert book.on_event(sell(LEADER_B), T0).skipped == "sell_without_entry"


def test_a_second_sell_while_the_exit_is_in_flight_does_not_close_twice() -> None:
    book = _book()
    opened = _opened(book)
    book.mark_open(opened.key, bet_id="b", entry_at=T0)
    assert book.on_event(sell(at=T0 + timedelta(seconds=5)), T0).jobs
    assert book.on_event(sell(at=T0 + timedelta(seconds=6)), T0).jobs == []


def test_events_before_t0_are_not_copied() -> None:
    book = CopyBook(make_spec(), t0=T0 + timedelta(minutes=5))
    old = buy(at=T0 + timedelta(minutes=4))  # its legs were complete before T0
    assert book.on_event(old, T0 + timedelta(minutes=6)).skipped == "before_t0"
    fresh = buy(LEADER_A, MINT_2, at=T0 + timedelta(minutes=6))
    assert isinstance(book.on_event(fresh, T0 + timedelta(minutes=6)).jobs[0], OpenIntent)


def test_the_day_ceiling_counts_admitted_attempts_and_the_next_utc_day_starts_clean() -> None:
    book = _book(max_attempts_per_leader_day=2)
    for i in range(2):
        assert isinstance(book.on_event(buy(mint=f"M{i}" + "1" * 40), T0).jobs[0], OpenIntent)
    third = book.on_event(buy(mint="M3" + "1" * 40), T0).jobs[0]
    assert isinstance(third, RejectEntry) and third.reason == "teto_dia"
    tomorrow = T0 + timedelta(days=1)
    assert isinstance(
        book.on_event(buy(mint="M4" + "1" * 40, at=tomorrow), tomorrow).jobs[0], OpenIntent
    )


def test_the_open_ceiling_counts_waiting_attempts_and_still_consumes_the_key() -> None:
    book = _book(max_open_per_stratum=1)
    first = _opened(book)
    over = book.on_event(buy(LEADER_B, MINT_2), T0).jobs[0]
    assert isinstance(over, CensorEntry) and over.reason == "teto_aberto"  # admitted, unfilled
    assert book.occupied("regra") == 1
    book.mark_closed(first.key)  # the slot is released ...
    again = book.on_event(buy(LEADER_A, MINT_2, at=T0 + timedelta(seconds=9)), T0).jobs[0]
    assert isinstance(again, RejectEntry) and again.reason == "co_compra"  # ... the key is not


def test_an_entry_inside_a_gap_is_a_rejected_row_named_lacuna_and_not_retried() -> None:
    book = _book()
    book.on_gap(gap(T0 - timedelta(seconds=30), T0 + timedelta(seconds=30)), T0)
    decision = book.on_event(buy(at=T0 + timedelta(seconds=40), block_time=T0), T0)
    job = decision.jobs[0]
    assert isinstance(job, RejectEntry) and job.reason == "lacuna"
    assert job.reason in CENSOR_REASONS
    assert book.on_event(buy(at=T0 + timedelta(minutes=5)), T0).skipped == "already_observed"


def test_a_gap_of_all_wallets_rejects_every_leader() -> None:
    book = _book()
    book.on_gap(gap(T0 - timedelta(seconds=5), None, wallet=None), T0)
    job = book.on_event(buy(LEADER_B), T0).jobs[0]
    assert isinstance(job, RejectEntry) and job.reason == "lacuna"


def test_a_gap_during_the_hold_censors_the_leaders_exit_not_a_guess() -> None:
    book = _book()
    opened = _opened(book)
    book.mark_open(opened.key, bet_id="b", entry_at=T0)
    book.on_gap(gap(T0 + timedelta(seconds=10), T0 + timedelta(seconds=20)), T0)
    job = book.on_event(sell(at=T0 + timedelta(seconds=40)), T0 + timedelta(seconds=40)).jobs[0]
    assert isinstance(job, CloseIntent) and job.censor == "leader_gap_exit"


def test_a_gap_of_another_wallet_does_not_touch_this_leader() -> None:
    book = _book()
    opened = _opened(book)
    book.mark_open(opened.key, bet_id="b", entry_at=T0)
    book.on_gap(gap(T0, T0 + timedelta(seconds=20), wallet=LEADER_B), T0)
    job = book.on_event(sell(at=T0 + timedelta(seconds=40)), T0).jobs[0]
    assert isinstance(job, CloseIntent) and job.censor is None


def test_an_unconfirmed_event_is_acted_on_then_confirmation_delay_is_recorded() -> None:
    book = _book()
    first = buy(confirmed=False, signature="S1", at=T0)
    intent = book.on_event(first, T0).jobs[0]
    assert isinstance(intent, OpenIntent) and intent.leader.confirmed is False
    later = buy(
        confirmed=True, signature="S1", slot=first.slot, at=T0 + timedelta(milliseconds=830)
    )
    confirm = book.on_event(later, T0 + timedelta(milliseconds=830)).jobs[0]
    assert isinstance(confirm, ConfirmIntent)
    assert confirm.key == intent.key and confirm.delay_ms == 830 and confirm.kind == "entry"
    assert book.expired_confirmations(T0 + timedelta(minutes=5)) == []  # nothing left pending


def test_an_event_that_never_confirms_invalidates_its_copy_and_sells_it_at_market() -> None:
    book = _book(confirm_timeout_s=30)
    intent = book.on_event(buy(confirmed=False, signature="S9"), T0).jobs[0]
    assert isinstance(intent, OpenIntent)
    book.mark_open(intent.key, bet_id="b", entry_at=T0)
    assert book.expired_confirmations(T0 + timedelta(seconds=29)) == []
    sale, bad = book.expired_confirmations(T0 + timedelta(seconds=31))
    # the copy stays in the primary: it is sold at market (priced, not censored) and flagged
    assert isinstance(sale, CloseIntent) and sale.reason == "invalidated" and sale.censor is None
    assert isinstance(bad, InvalidateIntent)
    assert bad.key == intent.key and bad.reason == "not_found" and bad.kind == "entry"
    assert book.expired_confirmations(T0 + timedelta(seconds=99)) == []  # reported once


def test_an_exit_that_never_confirms_only_annotates_the_already_closed_copy() -> None:
    book = _book()
    opened = _opened(book)
    book.mark_open(opened.key, bet_id="b", entry_at=T0)
    book.on_event(sell(confirmed=False, signature="SX", at=T0 + timedelta(seconds=5)), T0)
    book.mark_closed(opened.key)
    [bad] = book.expired_confirmations(T0 + timedelta(seconds=60))
    assert isinstance(bad, InvalidateIntent) and bad.kind == "exit"


def test_act_on_unconfirmed_off_waits_for_the_confirmed_copy_of_the_event() -> None:
    book = _book(act_on_unconfirmed=False)
    assert book.on_event(buy(confirmed=False, signature="S2"), T0).skipped == "unconfirmed_ignored"
    assert isinstance(book.on_event(buy(confirmed=True, signature="S2"), T0).jobs[0], OpenIntent)


def test_a_repeated_signature_is_a_duplicate_not_a_second_decision() -> None:
    book = _book()
    event = buy(signature="DUP")
    assert book.on_event(event, T0).jobs
    assert book.on_event(event, T0).skipped == "duplicate_signature"


def test_time_cap_closes_a_copy_held_too_long_once() -> None:
    book = _book(time_cap_s=600)
    opened = _opened(book)
    book.mark_open(opened.key, bet_id="b", entry_at=T0)
    assert book.due_time_caps(T0 + timedelta(seconds=599)) == []
    [cap] = book.due_time_caps(T0 + timedelta(seconds=601))
    assert cap.reason == "time_cap" and cap.leader is None and cap.censor is None
    assert book.due_time_caps(T0 + timedelta(seconds=700)) == []


def test_request_exit_for_the_safety_stop_only_on_an_open_copy() -> None:
    book = _book()
    opened = _opened(book)
    assert book.request_exit(opened.key, "safety_stop", T0) is None  # still opening
    book.mark_open(opened.key, bet_id="b", entry_at=T0)
    job = book.request_exit(opened.key, "safety_stop", T0 + timedelta(seconds=3))
    assert job is not None and job.reason == "safety_stop"
    assert book.request_exit(opened.key, "safety_stop", T0) is None  # already closing


def test_a_job_the_queue_refused_is_rolled_back_and_the_slot_is_released() -> None:
    book = _book()
    opened = _opened(book)
    book.rollback(opened)
    assert book.open_count == 0 and book.occupied("regra") == 0


def test_a_recovered_copy_is_flagged_so_its_leader_exit_is_censored() -> None:
    book = _book()
    book.recover_open(
        key="k1", mint=MINT_1, leader=LEADER_A, stratum="regra", bet_id="b1",
        entry_at=T0 - timedelta(minutes=2), peak_atoms=1_000_000,
    )  # fmt: skip
    job = book.on_event(sell(at=T0 + timedelta(seconds=5)), T0).jobs[0]
    assert isinstance(job, CloseIntent) and job.censor == "worker_restart_gap"
    assert book.occupied("regra") == 1


def test_the_funnel_restored_from_the_database_blocks_a_second_look_at_a_pair() -> None:
    book = _book(max_attempts_per_leader_day=1)
    book.restore_pair(LEADER_A, MINT_1)
    book.restore_attempt(LEADER_A, T0.date())
    assert book.on_event(buy(LEADER_A, MINT_1), T0).skipped == "already_observed"
    job = book.on_event(buy(LEADER_A, MINT_2), T0).jobs[0]
    assert isinstance(job, RejectEntry) and job.reason == "teto_dia"
