"""Wave 1a of H-030: the pure "program logs -> swap records" reader.

One ``logsSubscribe`` notification (or the ``meta.logMessages`` of a ``getTransaction`` used to
recover a gap) in; pump ``TradeEvent``, PumpSwap ``BuyEvent`` and ``SellEvent`` out as one record,
with counters for everything that is NOT a clean swap (nothing is dropped without a count).

Fixtures are the REAL transactions of ``fixtures/t1a_provenance.json`` (post-redeploy of 2026-10-02,
public RPC, 2026-10-05); anything built by hand from their logs is labelled SYNTHETIC.
"""

from __future__ import annotations

import base64
from dataclasses import replace
from typing import Any

import pytest

from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.program_logs import (
    LogCounters,
    read_program_logs,
    read_transaction_logs,
)
from hunter_exchanges.pumpfun.solana_codec import b58decode
from hunter_exchanges.pumpfun.trade_event_codec import (
    TRADE_EVENT_DISCRIMINATOR,
    decode_trade_event,
)
from hunter_exchanges.pumpswap.buy_event import (
    BUY_EVENT_DISCRIMINATOR,
)
from hunter_exchanges.pumpswap.decode import PUMPSWAP_PROGRAM_ID
from hunter_exchanges.pumpswap.sell_event import (
    SELL_EVENT_DISCRIMINATOR,
)

from .t1a_chain import inner_event_payloads, tx_fixture
from .t1a_logs import (
    AMM_BUY,
    AMM_BUY_EXACT,
    AMM_SELL,
    AMM_SELL_CASHBACK_X2,
    RECEIVED,
    V1_AMM_BUY_ROUTED,
    V1_AMM_SELL,
    V1_PUMP_BUY,
    V1_PUMP_SELL,
)
from .t1a_logs import (
    PREFIX as _PREFIX,
)
from .t1a_logs import (
    amm as _amm,
)
from .t1a_logs import (
    data_line_index as _data_line_index,
)
from .t1a_logs import (
    logs_of as _logs,
)
from .t1a_logs import (
    payload_of as _payload,
)
from .t1a_logs import (
    pump as _pump,
)
from .t1a_logs import (
    read as _read,
)
from .t1a_logs import (
    sig_of as _sig,
)
from .t1a_logs import (
    with_payload as _with_payload,
)

# -- the log lines ARE the inner-instruction events (payload identity, not just a count) --------


@pytest.mark.parametrize(
    ("directory", "name", "program", "discriminator"),
    [
        ("pumpswap", AMM_BUY, PUMPSWAP_PROGRAM_ID, BUY_EVENT_DISCRIMINATOR),
        ("pumpswap", AMM_BUY_EXACT, PUMPSWAP_PROGRAM_ID, BUY_EVENT_DISCRIMINATOR),
        ("pumpswap", V1_AMM_BUY_ROUTED, PUMPSWAP_PROGRAM_ID, BUY_EVENT_DISCRIMINATOR),
        ("pumpswap", AMM_SELL, PUMPSWAP_PROGRAM_ID, SELL_EVENT_DISCRIMINATOR),
        ("pumpswap", AMM_SELL_CASHBACK_X2, PUMPSWAP_PROGRAM_ID, SELL_EVENT_DISCRIMINATOR),
        ("pumpfun", V1_PUMP_BUY, PUMP_PROGRAM_ID, TRADE_EVENT_DISCRIMINATOR),
        ("pumpfun", V1_PUMP_SELL, PUMP_PROGRAM_ID, TRADE_EVENT_DISCRIMINATOR),
    ],
)
def test_the_event_lines_of_the_logs_carry_the_same_bytes_as_the_inner_instructions(
    directory: str, name: str, program: str, discriminator: bytes
) -> None:
    tx = tx_fixture(directory, name)
    from_logs = [
        base64.b64decode(line[len(_PREFIX) :])
        for line in _logs(tx)
        if line.startswith(_PREFIX) and base64.b64decode(line[len(_PREFIX) :])[:8] == discriminator
    ]
    assert from_logs
    assert from_logs == inner_event_payloads(tx, program, discriminator)


# -- attribution and identity ---------------------------------------------------------------


def test_a_transaction_touching_both_programs_gives_each_event_to_its_own_program() -> None:
    """SYNTHETIC: the real logs of a pump trade followed by the real logs of a PumpSwap buy, as one
    transaction would narrate them (each starts at ``invoke [1]`` and ends with ``success``)."""
    pump_tx, amm_tx = _pump(V1_PUMP_BUY), _amm(AMM_BUY)
    read = _read(amm_tx, logs=_logs(pump_tx) + _logs(amm_tx))
    assert [(s.program, s.event_ordinal) for s in read.swaps] == [
        (PUMP_PROGRAM_ID, 0),
        (PUMPSWAP_PROGRAM_ID, 0),
    ]
    assert read.swaps[0].venue == "curve" and read.swaps[1].venue == "pool"
    assert len({s.identity for s in read.swaps}) == 2


def test_event_ordinals_count_each_programs_event_lines_in_order() -> None:
    """SYNTHETIC: a PumpSwap buy's logs twice, as a transaction with two swaps would show them."""
    tx = _amm(AMM_BUY)
    read = _read(tx, logs=_logs(tx) + _logs(tx))
    assert [s.event_ordinal for s in read.swaps] == [0, 1]
    assert read.swaps[0].identity != read.swaps[1].identity


def test_a_foreign_programs_line_with_our_discriminator_is_not_ours() -> None:
    """SYNTHETIC: the real PumpSwap event line, but emitted while another program is on top of the
    invoke stack — a decoy. Not decoded, not a gap, counted apart."""
    tx = _amm(AMM_BUY)
    logs = _logs(tx)
    at = _data_line_index(logs)
    decoy = ["Program Decoy1111111111111111111111111111111111111 invoke [1]", logs[at]]
    decoy.append("Program Decoy1111111111111111111111111111111111111 success")
    read = _read(tx, logs=decoy)
    assert read.swaps == () and read.counters.foreign_data_lines == 1 and not read.gap


def test_a_data_line_with_no_invoke_context_is_reported_as_a_possible_loss() -> None:
    """SYNTHETIC: only the data line of a truncated stream. Attribution is unknown, so it is a gap,
    never a silent skip."""
    tx = _amm(AMM_BUY)
    logs = _logs(tx)
    read = _read(tx, logs=[logs[_data_line_index(logs)]])
    assert read.swaps == () and read.counters.unattributed_data_lines == 1 and read.gap


# -- everything that is not a clean swap is counted ----------------------------------------


def test_a_failed_transaction_is_counted_and_yields_nothing() -> None:
    tx = _amm(AMM_BUY)
    read = _read(tx, err={"InstructionError": [3, {"Custom": 6004}]})
    assert read.swaps == () and read.counters.failed_transactions == 1 and not read.gap


def test_other_events_of_the_programs_are_counted_not_decoded() -> None:
    """SYNTHETIC: the discriminator of an event this wave does not decode, in a real frame."""
    tx = _amm(AMM_BUY)
    logs = _logs(tx)
    at = _data_line_index(logs)
    other = _with_payload(logs, at, bytes.fromhex("82a42461e48287a5") + b"\x00" * 40)
    read = _read(tx, logs=other)
    assert read.swaps == () and read.counters.non_swap_events == 1 and not read.gap


def test_log_truncated_is_a_gap_even_when_the_swap_in_hand_is_fine() -> None:
    tx = _amm(AMM_BUY)
    read = _read(tx, logs=[*_logs(tx), "Log truncated"])
    assert len(read.swaps) == 1 and read.counters.truncated_logs == 1 and read.gap


def test_an_undecodable_swap_event_is_a_named_problem_and_a_gap_and_spares_the_good_ones() -> None:
    tx = _amm(AMM_BUY)
    logs = _logs(tx)
    at = _data_line_index(logs)
    bad = _with_payload(logs, at, _payload(logs, at) + b"\x00")  # SYNTHETIC: 50-byte tail
    read = _read(tx, logs=bad + _logs(_pump(V1_PUMP_BUY)))
    assert [s.program for s in read.swaps] == [PUMP_PROGRAM_ID]  # the good event survives
    assert read.counters.undecodable == 1 and read.gap
    (problem,) = read.problems
    assert (problem.program, problem.event_ordinal, problem.kind) == (
        PUMPSWAP_PROGRAM_ID,
        0,
        "undecodable",
    )
    assert "trailing bytes" in problem.detail


def test_an_undecodable_curve_event_is_counted_too() -> None:
    tx = _pump(V1_PUMP_SELL)
    logs = _logs(tx)
    at = _data_line_index(logs)
    bad = _with_payload(logs, at, _payload(logs, at)[:-3])  # SYNTHETIC: tail cut short
    read = _read(tx, logs=bad)
    assert read.swaps == () and read.counters.undecodable == 1 and read.gap


def test_an_event_whose_money_does_not_close_is_reported_and_not_emitted() -> None:
    """SYNTHETIC: a real buy with ``user_quote_amount_in`` (offset 8 + 8 + 13 u64) bumped by one
    lamport. Decodes fine, but the event's own numbers no longer add up — not a fill."""
    tx = _amm(AMM_BUY)
    logs = _logs(tx)
    at = _data_line_index(logs)
    body = bytearray(_payload(logs, at))
    offset = 8 + 8 + 12 * 8  # user_quote_amount_in is the 13th u64 after the timestamp
    body[offset : offset + 8] = (int.from_bytes(body[offset : offset + 8], "little") + 1).to_bytes(
        8, "little"
    )
    read = _read(tx, logs=_with_payload(logs, at, bytes(body)))
    assert read.swaps == () and read.counters.unconserved == 1 and read.gap
    assert read.problems[0].kind == "unconserved"


def test_a_sell_whose_net_does_not_equal_gross_minus_fees_is_not_emitted() -> None:
    """SYNTHETIC: a real sell with ``user_quote_amount_out`` (13th u64) bumped by one lamport."""
    tx = _amm(AMM_SELL)
    logs = _logs(tx)
    at = _data_line_index(logs)
    body = bytearray(_payload(logs, at))
    offset = 8 + 8 + 12 * 8
    body[offset : offset + 8] = (int.from_bytes(body[offset : offset + 8], "little") + 1).to_bytes(
        8, "little"
    )
    read = _read(tx, logs=_with_payload(logs, at, bytes(body)))
    assert read.swaps == () and read.counters.unconserved == 1


@pytest.mark.parametrize("amount_delta", [0, 7])
def test_a_curve_trade_quoted_in_something_other_than_sol_is_counted_apart(
    amount_delta: int,
) -> None:
    """SYNTHETIC: a real curve trade whose ``quote_mint`` is patched to USDC. The mint decides, not
    the amounts: with ``quote_amount == sol_amount`` (delta 0) the number still is not lamports.
    (Layout of 2026-10-02: ``quote_mint`` is 80 bytes from the end, ``quote_amount`` 48.)"""
    tx = _pump(V1_PUMP_BUY)
    logs = _logs(tx)
    at = _data_line_index(logs)
    event = decode_trade_event(_payload(logs, at))
    assert event.quote_amount == event.sol_amount  # a real SOL-quoted trade
    body = bytearray(_payload(logs, at))
    mint_at, amount_at = len(body) - 80, len(body) - 48
    assert bytes(body[mint_at : mint_at + 32]) == bytes(32)  # the all-zero native quote
    body[mint_at : mint_at + 32] = b58decode("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
    body[amount_at : amount_at + 8] = (event.sol_amount + amount_delta).to_bytes(8, "little")
    read = _read(tx, logs=_with_payload(logs, at, bytes(body)))
    assert read.swaps == () and read.counters.non_sol_quote == 1 and not read.gap


def test_a_line_that_is_not_base64_is_counted_and_never_raises() -> None:
    tx = _amm(AMM_BUY)
    logs = _logs(tx)
    at = _data_line_index(logs)
    broken = list(logs)
    broken[at] = _PREFIX + "###not-base64###"
    read = _read(tx, logs=broken)
    assert read.swaps == () and read.counters.bad_base64 == 1 and read.gap


def test_malformed_log_entries_are_counted_and_never_raise() -> None:
    tx = _amm(AMM_BUY)
    after: list[Any] = [*_logs(tx), None, 7, {"a": 1}]
    read = read_program_logs(signature=_sig(tx), slot=1, logs=after, received_at=RECEIVED)
    assert read.counters.malformed_lines == 3 and read.gap
    assert len(read.swaps) == 1  # what came BEFORE the damage is still read
    before: list[Any] = [None, 7, {"a": 1}, *_logs(tx)]
    read = read_program_logs(signature=_sig(tx), slot=1, logs=before, received_at=RECEIVED)
    assert read.counters.malformed_lines == 3 and read.gap
    # ...but after a line that may have been an event nothing is attributed (see the integrity tests)
    assert read.swaps == () and read.counters.unattributed_data_lines == 1


def test_a_notification_with_no_event_at_all_is_a_normal_empty_read() -> None:
    read = read_program_logs(
        signature="s",
        slot=1,
        logs=[
            "Program 11111111111111111111111111111111 invoke [1]",
            "Program 11111111111111111111111111111111 success",
        ],
        received_at=RECEIVED,
    )
    assert read.swaps == () and not read.gap and read.counters == LogCounters()


def test_counters_add_up_across_notifications() -> None:
    tx = _amm(AMM_BUY)
    a = _read(tx)
    b = _read(tx, logs=[*_logs(tx), "Log truncated"])
    total = a.counters + b.counters
    assert (total.swaps, total.truncated_logs) == (2, 1)
    assert total.gap and not a.counters.gap


# -- reading a getTransaction result (the REST recovery path) --------------------------------


@pytest.mark.parametrize(
    ("directory", "name"),
    [
        ("pumpswap", V1_AMM_SELL),
        ("pumpswap", V1_AMM_BUY_ROUTED),
        ("pumpfun", V1_PUMP_BUY),
        ("pumpswap", AMM_BUY),
    ],
)
def test_a_get_transaction_result_reads_like_its_logs_of_any_version(
    directory: str, name: str
) -> None:
    tx = tx_fixture(directory, name)
    from_tx = read_transaction_logs(tx, received_at=RECEIVED)
    from_logs = _read(tx)
    # Only a pool record gains something from the transaction: its mints (wave 1b, test_pool_legs).
    unlegged = tuple(
        replace(s, base_mint=None, quote_mint=None, quote_is_sol=None) if s.venue == "pool" else s
        for s in from_tx.swaps
    )
    assert unlegged == from_logs.swaps and len(from_tx.swaps) >= 1
    assert from_tx.counters == from_logs.counters


def test_a_failed_get_transaction_result_is_counted() -> None:
    tx = _amm(AMM_BUY)
    tx["meta"]["err"] = {"InstructionError": [1, "Custom"]}
    read = read_transaction_logs(tx, received_at=RECEIVED)
    assert read.swaps == () and read.counters.failed_transactions == 1


def test_a_get_transaction_result_without_logs_is_a_named_problem_not_a_clean_read() -> None:
    tx = _amm(AMM_BUY)
    tx["meta"]["logMessages"] = None  # nodes that pruned the log messages
    read = read_transaction_logs(tx, received_at=RECEIVED)
    assert read.swaps == () and read.counters.logs_missing == 1 and read.gap


@pytest.mark.parametrize("missing", ["signature", "slot"])
def test_a_get_transaction_result_without_identity_is_refused_not_stamped_with_a_default(
    missing: str,
) -> None:
    """A swap record without its signature or slot would carry an identity nobody can look up."""
    tx = _amm(AMM_BUY)
    if missing == "signature":
        tx["transaction"]["signatures"] = []
    else:
        del tx["slot"]
    with pytest.raises(ValueError, match=missing):
        read_transaction_logs(tx, received_at=RECEIVED)
