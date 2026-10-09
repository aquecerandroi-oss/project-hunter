"""The second half of the copy book's rules (H-037): evidence, transfers, the chain's verdicts
(``LeaderConfirmation``), divergence, the horizon, contamination of our own exits and recovery of a
provisional copy. Pure: no IO, no clock but the argument."""

from __future__ import annotations

from datetime import timedelta

import pytest

from hunter_exchanges.pumpfun.leader_events import LeaderEvent
from hunter_meme_worker.copy_book import CopyBook
from hunter_meme_worker.copy_events import (
    CloseIntent,
    ConfirmIntent,
    InvalidateIntent,
    OpenIntent,
    RejectEntry,
)

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


def _provisional(
    book: CopyBook, signature: str, **kwargs: object
) -> tuple[LeaderEvent, OpenIntent]:
    event = buy(confirmed=False, signature=signature, **kwargs)  # type: ignore[arg-type]
    intent = book.on_event(event, T0).jobs[0]
    assert isinstance(intent, OpenIntent)
    book.mark_open(intent.key, bet_id="b", entry_at=T0)
    return event, intent


def test_a_missing_or_shared_sol_leg_is_never_a_guessed_zero() -> None:
    book = _book()
    multi = book.on_event(buy(multi_mint=True), T0).jobs[0]
    assert isinstance(multi, RejectEntry) and multi.reason == "multi_mint"
    unknown = book.on_event(buy(mint=MINT_2, spent_sol=None), T0).jobs[0]
    assert isinstance(unknown, RejectEntry) and unknown.reason == "evidencia_insuficiente"
    assert book.open_count == 0


def test_a_transfer_out_triggers_the_exit_labelled_leader_transfer() -> None:
    book = _book()
    _provisional(book, "T1")
    job = book.on_event(sell(kind="transfer", at=T0 + timedelta(seconds=4)), T0).jobs[0]
    assert isinstance(job, CloseIntent) and job.reason == "leader_transfer"


def test_a_confirmation_item_records_the_delay_once_and_is_idempotent() -> None:
    book = _book()
    event, _ = _provisional(book, "PC1")
    done = book.on_confirmation(confirmation(event), T0).jobs[0]
    assert isinstance(done, ConfirmIntent) and done.delay_ms == 700 and done.kind == "entry"
    assert book.on_confirmation(confirmation(event), T0).jobs == []


@pytest.mark.parametrize("status", ["divergent", "failed_tx", "not_found"])
def test_a_bad_verdict_invalidates_the_copy_by_that_name_and_sells_it_at_market(
    status: str,
) -> None:
    book = _book()
    event, _ = _provisional(book, f"PC-{status}")
    sale, bad = book.on_confirmation(confirmation(event, status), T0).jobs
    assert isinstance(sale, CloseIntent) and sale.reason == "invalidated" and sale.censor is None
    assert isinstance(bad, InvalidateIntent) and bad.reason == status


def test_an_rpc_error_says_nothing_and_the_timeout_keeps_running() -> None:
    book = _book(confirm_timeout_s=30)
    event, _ = _provisional(book, "PC-RPC")
    assert book.on_confirmation(confirmation(event, "rpc_error"), T0).jobs == []
    assert book.expired_confirmations(T0 + timedelta(seconds=31))  # still owed


def test_a_confirmation_with_other_numbers_than_the_event_we_acted_on_is_divergent() -> None:
    book = _book()
    event, _ = _provisional(book, "PC-NUM", position_after=1_000_000)
    jobs = book.on_confirmation(confirmation(event, chain_position_after=400_000), T0).jobs
    assert isinstance(jobs[-1], InvalidateIntent) and jobs[-1].reason == "divergent"


def test_the_same_fact_resent_confirmed_with_other_numbers_is_divergent_too() -> None:
    book = _book()
    sent, _ = _provisional(book, "RS", position_after=1_000_000)
    jobs = book.on_event(
        buy(confirmed=True, signature="RS", position_after=999, slot=sent.slot), T0
    ).jobs
    assert isinstance(jobs[-1], InvalidateIntent) and jobs[-1].reason == "divergent"


def test_two_facts_of_one_transaction_are_not_swallowed_as_duplicates() -> None:
    book = _book()
    first = book.on_event(buy(mint=MINT_1, signature="TX"), T0).jobs
    second = book.on_event(buy(mint=MINT_2, signature="TX"), T0).jobs
    assert isinstance(first[0], OpenIntent) and isinstance(second[0], OpenIntent)


def test_entries_stop_at_the_horizon_but_exits_of_what_is_open_do_not() -> None:
    book = CopyBook(make_spec(horizon_days=1), t0=T0 - timedelta(minutes=1))
    _provisional(book, "H1")
    late = T0 + timedelta(days=1, minutes=1)
    assert book.on_event(buy(mint=MINT_2, at=late), late).skipped == "after_horizon"
    assert isinstance(book.on_event(sell(at=late), late).jobs[0], CloseIntent)


def test_an_own_exit_of_a_copy_that_lived_across_a_gap_is_priced_but_flagged_contaminated() -> None:
    book = _book()
    _provisional(book, "G1")
    book.on_gap(gap(T0 + timedelta(seconds=5), T0 + timedelta(seconds=9)), T0)
    [cap] = book.due_time_caps(T0 + timedelta(seconds=700))
    assert cap.censor is None and cap.contaminated == "leader_gap_exit"


def test_a_provisional_copy_recovered_after_a_restart_still_owes_its_confirmation() -> None:
    book = _book(confirm_timeout_s=30)
    book.recover_open(
        key="k9", mint=MINT_1, leader=LEADER_A, stratum="regra", bet_id="b9",
        entry_at=T0, peak_atoms=1_000_000,
    )  # fmt: skip
    book.restore_pending(
        "k9", "RESTART-SIG", LEADER_A, MINT_1, first_observed_at=T0,
        position_after=1_000_000, token_delta=1_000_000, slot=1,
    )  # fmt: skip
    due = book.expired_confirmations(T0 + timedelta(seconds=31))
    [bad] = [j for j in due if isinstance(j, InvalidateIntent)]
    assert bad.key == "k9" and bad.reason == "not_found"


def test_a_migrated_copy_is_sent_out_unpriced_when_the_pool_is_not_a_venue() -> None:
    book = _book()
    _, intent = _provisional(book, "M1")
    job = book.request_exit(intent.key, "migrated", T0, censor="migrou_fora_de_praca")
    assert job is not None and job.censor == "migrou_fora_de_praca"


def test_a_restart_never_extends_the_confirmation_deadline() -> None:
    book = _book(confirm_timeout_s=30)
    book.recover_open(
        key="k8", mint=MINT_1, leader=LEADER_A, stratum="regra", bet_id="b8",
        entry_at=T0, peak_atoms=1,
    )  # fmt: skip
    book.restore_pending(
        "k8", "OLD-SIG", LEADER_A, MINT_1, first_observed_at=T0 - timedelta(seconds=100),
        position_after=1, token_delta=1, slot=1,
    )  # fmt: skip
    assert book.expired_confirmations(T0)  # already overdue: it fires at once, not 30 s later


def test_a_mint_found_on_the_pool_is_remembered_and_the_attempt_refunded() -> None:
    book = _book(max_attempts_per_leader_day=1)
    first = book.on_event(buy(mint=MINT_1), T0).jobs[0]
    assert isinstance(first, OpenIntent)
    book.pool_mint_found(first.key, LEADER_A, "regra", MINT_1, T0.date())
    again = book.on_event(buy(LEADER_B, MINT_1), T0).jobs[0]
    assert isinstance(again, RejectEntry) and again.reason == "venue_fora_do_escopo"
    # the refunded attempt does not count against the day's ceiling, the key is free again
    assert isinstance(book.on_event(buy(mint=MINT_2), T0).jobs[0], OpenIntent)


def test_a_retired_set_only_keeps_what_is_open() -> None:
    open_book = _book()
    _, intent = _provisional(open_book, "R1")
    retired = CopyBook(make_spec(status="retired"), t0=T0 - timedelta(hours=1))
    assert retired.on_event(buy(mint=MINT_2), T0).skipped == "rule_set_retired"
    retired.recover_open(
        key="kr",
        mint=MINT_1,
        leader=LEADER_A,
        stratum="regra",
        bet_id="br",
        entry_at=T0,
        peak_atoms=1,
    )
    assert isinstance(retired.on_event(sell(), T0).jobs[0], CloseIntent)  # exits keep working
    assert intent is not None
