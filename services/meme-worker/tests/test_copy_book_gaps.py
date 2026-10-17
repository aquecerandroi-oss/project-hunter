"""Gap semantics of the copy book (H-037, R2 fix B1/B2/B5): a *source-health* gap (`nats_*`, `chain_*`)
never censors or rejects — the copy is priced and flagged; an *effective coverage loss*
(`no_coverage:*`, a downtime, `funil_indisponivel`) censors and blocks entries, and after it closes the
leader gets no new entry until its window is recomposed from chain history. Pure; no IO."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest

from hunter_meme_worker.copy_book import CopyBook
from hunter_meme_worker.copy_events import (
    CloseIntent,
    InvalidateIntent,
    OpenIntent,
    RecomposeDone,
    RejectEntry,
    UnverifiedIntent,
)
from hunter_meme_worker.copy_history import MintTrace, WindowTrace

from .copy_support import (
    LEADER_A,
    LEADER_B,
    MINT_1,
    MINT_2,
    T0,
    buy,
    confirmation,
    gap,
    make_spec,
    sell,
)

pytestmark = pytest.mark.unit


def _book(**overrides: object) -> CopyBook:
    return CopyBook(make_spec(**overrides), t0=T0 - timedelta(hours=1))


def _held(book: CopyBook, *, at: datetime = T0, **kw: Any) -> OpenIntent:
    intent = book.on_event(buy(at=at, **kw), at).jobs[0]
    assert isinstance(intent, OpenIntent)
    book.mark_open(intent.key, bet_id="b", entry_at=at + timedelta(seconds=2))
    return intent


# --------------------------------------------------------------------------------------- B1
def test_the_reviews_probe_a_nats_silence_opening_after_the_buy_does_not_censor_the_sell() -> None:
    book = _book()
    _held(book)
    book.on_gap(
        gap(T0 + timedelta(seconds=62), None, reason="nats_silent"), T0 + timedelta(seconds=62)
    )
    book.on_gap(
        gap(T0 + timedelta(seconds=62), T0 + timedelta(seconds=300), reason="nats_silent"),
        T0 + timedelta(seconds=300),
    )
    job = book.on_event(sell(at=T0 + timedelta(seconds=300)), T0 + timedelta(seconds=300)).jobs[0]
    assert isinstance(job, CloseIntent)
    assert job.censor is None  # priced, not censored
    assert job.contaminated == "nats_silent"  # but flagged


@pytest.mark.parametrize(
    "reason", ["nats_silent", "nats_connect", "chain_ws_down", "chain_logs_partial"]
)
def test_a_source_health_gap_never_rejects_an_entry(reason: str) -> None:
    book = _book()
    book.on_gap(gap(T0 - timedelta(seconds=30), None, reason=reason), T0)
    job = book.on_event(buy(at=T0 + timedelta(seconds=5)), T0 + timedelta(seconds=5)).jobs[0]
    assert isinstance(job, OpenIntent)


@pytest.mark.parametrize(
    "reason",
    [
        "no_coverage:nats_silent+chain_ws_down",
        "funil_indisponivel",
        "worker_downtime",
        "source_lost",
    ],
)
def test_an_effective_coverage_loss_still_rejects_and_censors(reason: str) -> None:
    book = _book()
    held = _held(book, mint=MINT_2)
    book.on_gap(gap(T0 - timedelta(seconds=30), None, reason=reason), T0)
    job = book.on_event(buy(at=T0 + timedelta(seconds=5)), T0 + timedelta(seconds=5)).jobs[0]
    assert isinstance(job, RejectEntry) and job.reason == "lacuna"
    if reason != "funil_indisponivel":  # a database outage does not blind an open copy
        sale = book.on_event(sell(mint=MINT_2, at=T0 + timedelta(seconds=9)), T0).jobs[0]
        assert isinstance(sale, CloseIntent) and sale.censor == "leader_gap_exit"
    else:
        assert book.position(held.key) is not None


def test_chain_only_events_open_and_close_copies() -> None:
    book = _book()
    opened = book.on_event(buy(source="chain", kind="swap", confirmed=True), T0).jobs[0]
    assert isinstance(opened, OpenIntent) and opened.leader.source == "chain"
    book.mark_open(opened.key, bet_id="b", entry_at=T0)
    sale = book.on_event(
        sell(source="chain", kind="swap", confirmed=True, at=T0 + timedelta(seconds=9)), T0
    )
    assert isinstance(sale.jobs[0], CloseIntent) and sale.jobs[0].censor is None


def test_a_nats_only_loss_with_the_chain_alive_keeps_a_copy_priced_and_flagged_until_it_closes() -> (
    None
):
    book = _book()
    held = _held(book)
    book.on_gap(gap(T0 + timedelta(seconds=10), None, reason="nats_silent"), T0)
    [cap] = book.due_time_caps(T0 + timedelta(seconds=800))
    assert cap.key == held.key and cap.censor is None and cap.contaminated == "nats_silent"


# --------------------------------------------------------------------------------------- B2 a
def test_after_a_coverage_gap_closes_the_leader_has_no_entry_until_recomposed() -> None:
    book = _book()
    book.on_gap(gap(T0, None, wallet=None, reason="no_coverage:a+b"), T0)
    book.on_gap(
        gap(T0, T0 + timedelta(seconds=20), wallet=None, reason="no_coverage:a+b"),
        T0 + timedelta(seconds=20),
    )
    later = T0 + timedelta(seconds=30)
    job = book.on_event(buy(at=later), later).jobs[0]
    assert isinstance(job, RejectEntry) and job.reason == "recomposicao_pendente"
    windows = {w.wallet: w for w in book.recompositions_due(later)}
    assert set(windows) == {LEADER_A, LEADER_B}  # a global gap is recomposed leader by leader
    assert windows[LEADER_A].start == T0 and windows[LEADER_A].end == T0 + timedelta(seconds=20)
    seen = book.apply_window(
        windows[LEADER_A], WindowTrace(complete=True, bought_mints=frozenset({MINT_2})), later
    )
    [done] = seen
    assert isinstance(done, RecomposeDone) and done.wallet == LEADER_A and done.gap_id
    assert len(done.seen) == 1 and isinstance(done.seen[0], RejectEntry)
    assert done.seen[0].reason == "visto_na_lacuna" and done.seen[0].mint == MINT_2
    assert book.is_blocked(LEADER_B)  # B's window is still open
    book.apply_window(
        windows[LEADER_B], WindowTrace(complete=True, bought_mints=frozenset()), later
    )
    assert not book.is_blocked(LEADER_A) and not book.is_blocked(LEADER_B)
    assert isinstance(book.on_event(buy(mint=MINT_1 + "x", at=later), later).jobs[0], OpenIntent)
    # the pair seen inside the hole is no longer "the first" when the leader buys it again
    assert book.on_event(buy(mint=MINT_2, at=later), later).skipped == "already_observed"


def test_an_incomplete_window_keeps_the_leader_blocked_and_is_retried() -> None:
    book = _book()
    book.on_gap(gap(T0, T0 + timedelta(seconds=20), wallet=LEADER_A, reason="no_coverage:a+b"), T0)
    later = T0 + timedelta(seconds=30)
    [window] = book.recompositions_due(later)
    book.window_failed(window, later)
    assert book.recompositions_due(later) == []  # backoff
    retry = book.recompositions_due(later + timedelta(minutes=5))
    assert len(retry) == 1
    blocked = book.on_event(buy(at=later), later).jobs[0]
    assert isinstance(blocked, RejectEntry) and blocked.reason == "recomposicao_pendente"
    other = book.on_event(buy(LEADER_B, MINT_2, at=later), later).jobs[0]
    assert isinstance(other, OpenIntent)  # another leader is unaffected


def test_a_window_that_cannot_be_read_at_all_is_a_failed_window_not_a_complete_one() -> None:
    book = _book()
    book.on_gap(gap(T0, T0 + timedelta(seconds=20), wallet=LEADER_A, reason="no_coverage:a+b"), T0)
    [window] = book.recompositions_due(T0 + timedelta(seconds=30))
    book.apply_window(
        window, WindowTrace(complete=False, bought_mints=frozenset()), T0 + timedelta(seconds=30)
    )
    assert book.is_blocked(LEADER_A)


def test_a_copy_alive_across_a_closed_gap_is_priced_and_flagged_once_the_window_is_recomposed() -> (
    None
):
    book = _book()
    held = _held(book, position_after=1_000_000)
    book.on_gap(
        gap(
            T0 + timedelta(seconds=5),
            T0 + timedelta(seconds=25),
            wallet=LEADER_A,
            reason="no_coverage:a+b",
        ),
        T0,
    )
    now = T0 + timedelta(seconds=40)
    [window] = book.recompositions_due(now)
    jobs = book.apply_window(window, WindowTrace(complete=True, bought_mints=frozenset()), now)
    [done_job] = jobs
    assert isinstance(done_job, RecomposeDone) and not done_job.seen
    trace = MintTrace(current_atoms=0, peak_atoms=1_200_000)
    exit_jobs = book.apply_trace(held.key, trace, now, reason_flag="leader_gap_exit")
    [sale] = exit_jobs
    assert isinstance(sale, CloseIntent) and sale.reason == "leader_exit_full"
    assert sale.censor is None and sale.contaminated == "leader_gap_exit"  # priced late, flagged


def test_an_unreadable_trace_leaves_the_exit_censored_with_the_named_reason() -> None:
    book = _book()
    held = _held(book)
    book.on_gap(
        gap(
            T0 + timedelta(seconds=5),
            T0 + timedelta(seconds=25),
            wallet=LEADER_A,
            reason="no_coverage:a+b",
        ),
        T0,
    )
    assert book.apply_trace(held.key, None, T0, reason_flag="leader_gap_exit") == []
    sale = book.on_event(sell(at=T0 + timedelta(seconds=60)), T0 + timedelta(seconds=60)).jobs[0]
    assert isinstance(sale, CloseIntent) and sale.censor == "leader_gap_exit"


def test_a_trace_that_shows_a_small_drop_keeps_the_copy_open_and_raises_the_peak() -> None:
    book = _book()
    held = _held(book, position_after=1_000_000)
    book.on_gap(
        gap(
            T0 + timedelta(seconds=5),
            T0 + timedelta(seconds=25),
            wallet=LEADER_A,
            reason="no_coverage:a+b",
        ),
        T0,
    )
    assert (
        book.apply_trace(held.key, MintTrace(900_000, 1_000_000), T0, reason_flag="leader_gap_exit")
        == []
    )
    position = book.position(held.key)
    assert (
        position is not None
        and position.contam == "leader_gap_exit"
        and position.gap_reason is None
    )


# --------------------------------------------------------------------------------------- B5
def test_rpc_error_only_never_liquidates_it_flags_the_copy_unverified_and_keeps_it() -> None:
    book = _book(confirm_timeout_s=30)
    event = buy(confirmed=False, signature="RPC-ONLY")
    intent = book.on_event(event, T0).jobs[0]
    assert isinstance(intent, OpenIntent)
    book.mark_open(intent.key, bet_id="b", entry_at=T0)
    assert book.on_confirmation(confirmation(event, "rpc_error"), T0).jobs == []
    due = book.expired_confirmations(T0 + timedelta(seconds=31))
    assert [type(j).__name__ for j in due] == ["UnverifiedIntent"]
    [flag] = due
    assert isinstance(flag, UnverifiedIntent) and flag.key == intent.key
    position = book.position(intent.key)
    assert position is not None and position.state == "open"  # not liquidated


def test_silence_to_the_deadline_still_liquidates_as_not_found() -> None:
    book = _book(confirm_timeout_s=30)
    event = buy(confirmed=False, signature="SILENT")
    intent = book.on_event(event, T0).jobs[0]
    assert isinstance(intent, OpenIntent)
    book.mark_open(intent.key, bet_id="b", entry_at=T0)
    sale, bad = book.expired_confirmations(T0 + timedelta(seconds=31))
    assert isinstance(sale, CloseIntent) and sale.reason == "invalidated"
    assert isinstance(bad, InvalidateIntent) and bad.reason == "not_found"


def test_a_later_not_found_after_an_rpc_error_still_liquidates() -> None:
    book = _book()
    event = buy(confirmed=False, signature="RPC-THEN-NF")
    intent = book.on_event(event, T0).jobs[0]
    assert isinstance(intent, OpenIntent)
    book.mark_open(intent.key, bet_id="b", entry_at=T0)
    book.on_confirmation(confirmation(event, "rpc_error"), T0)
    sale, bad = book.on_confirmation(confirmation(event, "not_found"), T0).jobs
    assert (
        isinstance(sale, CloseIntent)
        and isinstance(bad, InvalidateIntent)
        and bad.reason == "not_found"
    )


# --------------------------------------------------------------------------------------- review item 7
def test_a_provisional_rebuy_that_raises_the_peak_owes_its_own_confirmation() -> None:
    book = _book()
    held = _held(book, position_after=100)
    rebuy = buy(confirmed=False, signature="REBUY", position_after=300, position_before=100,
                at=T0 + timedelta(seconds=3))  # fmt: skip
    assert book.on_event(rebuy, T0).skipped == "already_observed"
    jobs = book.on_confirmation(confirmation(rebuy, chain_position_after=100), T0).jobs
    assert isinstance(jobs[-1], InvalidateIntent) and jobs[-1].key == held.key


def test_a_pair_known_only_in_memory_is_re_emitted_by_the_window_until_its_row_lands() -> None:
    """R2 round 4 (MF3): a first buy rejected under the floor whose write was lost is 'observed' in memory
    but absent from the funnel; certifying the window as recomposed without it would make the re-buy
    "the first" after a restart. The window emits it again until the book is told it landed."""
    book = _book()
    rejected = book.on_event(buy(at=T0, spent_sol="0.099"), T0).jobs[0]
    assert isinstance(rejected, RejectEntry)  # observed, rejected - and (say) its write was lost
    book.on_gap(gap(T0, T0 + timedelta(seconds=20), wallet=LEADER_A, reason="no_coverage:a+b"), T0)
    now = T0 + timedelta(seconds=30)
    trace = WindowTrace(complete=True, bought_mints=frozenset({MINT_1}))
    [window] = book.recompositions_due(now)
    [done] = book.apply_window(window, trace, now)
    assert isinstance(done, RecomposeDone) and [s.mint for s in done.seen] == [MINT_1]
    book.landed(done)  # the transaction took the window's pairs
    book.on_gap(
        gap(
            T0 + timedelta(seconds=40),
            T0 + timedelta(seconds=50),
            wallet=LEADER_A,
            reason="no_coverage:a+b",
        ),
        T0,
    )
    [again] = book.recompositions_due(now + timedelta(minutes=1))
    [second] = book.apply_window(again, trace, now + timedelta(minutes=1))
    assert isinstance(second, RecomposeDone) and second.seen == ()  # landed: not emitted twice


def test_a_pair_whose_row_landed_is_not_re_emitted_by_a_window() -> None:
    book = _book()
    rejected = book.on_event(buy(at=T0, spent_sol="0.099"), T0).jobs[0]
    assert isinstance(rejected, RejectEntry)
    book.landed(rejected)
    book.on_gap(gap(T0, T0 + timedelta(seconds=20), wallet=LEADER_A, reason="no_coverage:a+b"), T0)
    [window] = book.recompositions_due(T0 + timedelta(seconds=30))
    [done] = book.apply_window(
        window,
        WindowTrace(complete=True, bought_mints=frozenset({MINT_1})),
        T0 + timedelta(seconds=30),
    )
    assert isinstance(done, RecomposeDone) and done.seen == ()
