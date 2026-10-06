"""Wave 1a of H-030: the integrity rules of the program-logs reader — identity that survives a lost
neighbour, an invoke stack that must be coherent, unknown events that stay visible, an input that is
never mutated. Real fixtures (``fixtures/t1a_provenance.json``); anything built by hand from their
logs is labelled SYNTHETIC.
"""

from __future__ import annotations

import base64
import copy
from typing import Any

import pytest

from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.program_logs import read_transaction_logs
from hunter_exchanges.pumpswap.buy_event import buy_events_from_transaction
from hunter_exchanges.pumpswap.decode import PUMPSWAP_PROGRAM_ID
from hunter_exchanges.pumpswap.sell_event import sell_events_from_transaction

from .t1a_chain import (
    inner_event_bodies,
    log_event_payloads,
    tx_fixture,
)
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
    read as _read,
)
from .t1a_logs import (
    with_payload as _with_payload,
)

# -- identity stays stable when a neighbouring line is lost -------------------------------------


def test_a_corrupt_event_line_does_not_shift_the_identity_of_the_next_event() -> None:
    """Events A and B of one program in one transaction (real: two sells). If A arrives corrupt,
    B must still be ordinal 1 — the ordinal it gets in the full recovery read — never 0."""
    tx = _amm(AMM_SELL_CASHBACK_X2)
    logs = _logs(tx)
    clean = _read(tx).swaps
    assert [s.event_ordinal for s in clean] == [0, 1]
    first_line = _data_line_index(logs, 0)
    for corrupt in (
        _PREFIX + "###not-base64###",  # not base64
        _PREFIX + base64.b64encode(b"\x01\x02").decode(),  # shorter than a discriminator
    ):
        broken = list(logs)
        broken[first_line] = corrupt
        read = _read(tx, logs=broken)
        assert read.gap and read.counters.bad_base64 == 1
        (survivor,) = read.swaps
        assert survivor == clean[1]  # same identity AND same content as in the clean read


# -- the invoke stack must be coherent or it attributes nothing ---------------------------------


def _foreign_frame_logs(tx: dict[str, Any], *, bad_return: bool) -> list[str]:
    """SYNTHETIC: our real event line placed inside a foreign program's frame, closed by the
    return line of a *different* program when ``bad_return`` — so a naive stack would pop the
    foreign frame, fall back to the PumpSwap frame and give the event to it."""
    logs = _logs(tx)
    line = logs[_data_line_index(logs)]
    return [
        f"Program {PUMPSWAP_PROGRAM_ID} invoke [1]",
        "Program Foreign1111111111111111111111111111111111 invoke [2]",
        f"Program {PUMPSWAP_PROGRAM_ID} success"
        if bad_return
        else "Program Foreign1111111111111111111111111111111111 success",
        line,
        f"Program {PUMPSWAP_PROGRAM_ID} success",
    ]


def test_a_return_line_of_the_wrong_program_breaks_the_context_and_is_a_gap() -> None:
    read = _read(_amm(AMM_BUY), logs=_foreign_frame_logs(_amm(AMM_BUY), bad_return=True))
    assert read.swaps == ()
    assert read.counters.stack_inconsistencies >= 1 and read.gap


def test_a_depth_that_skips_a_level_breaks_the_context_and_is_a_gap() -> None:
    tx = _amm(AMM_BUY)
    line = _logs(tx)[_data_line_index(_logs(tx))]
    logs = [
        f"Program {PUMPSWAP_PROGRAM_ID} invoke [3]",
        line,
        f"Program {PUMPSWAP_PROGRAM_ID} success",
    ]
    read = _read(tx, logs=logs)
    assert read.swaps == () and read.counters.stack_inconsistencies >= 1 and read.gap


def test_once_the_context_is_broken_later_lines_are_not_attributed() -> None:
    """After the first inconsistency attribution is unknowable: every later data line is counted
    as unattributed (a gap), even one that sits in a perfectly well-formed frame."""
    tx = _amm(AMM_BUY)
    good = _logs(tx)
    broken = [f"Program {PUMP_PROGRAM_ID} success", *good]  # a return with nothing on the stack
    read = _read(tx, logs=broken)
    assert read.counters.stack_inconsistencies == 1
    assert read.swaps == () and read.counters.unattributed_data_lines == 1 and read.gap


@pytest.mark.parametrize(
    ("directory", "name"),
    [
        ("pumpswap", AMM_BUY),
        ("pumpswap", AMM_BUY_EXACT),
        ("pumpswap", AMM_SELL),
        ("pumpswap", AMM_SELL_CASHBACK_X2),
        ("pumpswap", V1_AMM_SELL),
        ("pumpswap", V1_AMM_BUY_ROUTED),
        ("pumpswap", "t1a_rpc_amm_buy_routed_2HzxLVTqSFWq_raw.json"),
        ("pumpswap", "t1a_rpc_amm_buy_exact_3YxgSPJioUJp_raw.json"),
        ("pumpswap", "t1a_rpc_amm_buy_nocreator_4jyiFoCoVoWt_raw.json"),
        ("pumpfun", V1_PUMP_BUY),
        ("pumpfun", V1_PUMP_SELL),
    ],
)
def test_every_real_fixture_reads_clean_with_a_coherent_stack(directory: str, name: str) -> None:
    read = read_transaction_logs(tx_fixture(directory, name), received_at=RECEIVED)
    assert read.swaps and not read.gap and read.problems == ()
    assert read.counters.stack_inconsistencies == 0 and read.counters.unattributed_data_lines == 0


# -- unknown event types are visible, and the input is never touched ---------------------------


def test_events_that_are_not_swaps_are_listed_by_program_and_discriminator() -> None:
    """SYNTHETIC discriminator in a real frame: a collector aggregates this to alert on a NEW event
    type (a future swap variant) instead of finding it missing from the population."""
    tx = _amm(AMM_BUY)
    logs = _logs(tx)
    at = _data_line_index(logs)
    read = _read(tx, logs=_with_payload(logs, at, bytes.fromhex("82a42461e48287a5") + bytes(40)))
    assert read.counters.non_swap_events == 1
    assert read.other_events == ((PUMPSWAP_PROGRAM_ID, "82a42461e48287a5"),)


def test_reading_never_mutates_the_transaction_it_was_given() -> None:
    """A getTransaction result is shared by callers; appending loaded addresses to its own
    ``accountKeys`` in place would corrupt every later read of a v0 transaction."""
    for directory, name in (
        ("pumpswap", "t1a_rpc_amm_buy_routed_2HzxLVTqSFWq_raw.json"),
        ("pumpswap", V1_AMM_BUY_ROUTED),
        ("pumpswap", AMM_SELL),
    ):
        tx = tx_fixture(directory, name)
        before = copy.deepcopy(tx)
        read_transaction_logs(tx, received_at=RECEIVED)
        buy_events_from_transaction(tx)
        sell_events_from_transaction(tx)
        assert tx == before


def test_after_a_stray_return_a_data_line_on_a_still_open_frame_is_not_attributed() -> None:
    """SYNTHETIC: a PumpSwap frame is open (so a naive reader would still see it on top), then a
    return line of a program that was never invoked arrives. The context is broken; the real event
    line that follows must NOT become a swap even though the open frame is ours."""
    tx = _amm(AMM_BUY)
    line = _logs(tx)[_data_line_index(_logs(tx))]
    logs = [
        f"Program {PUMPSWAP_PROGRAM_ID} invoke [1]",
        "Program Stray111111111111111111111111111111111111 success",
        line,
        f"Program {PUMPSWAP_PROGRAM_ID} success",
    ]
    read = _read(tx, logs=logs)
    assert read.swaps == ()
    assert read.counters.stack_inconsistencies == 1 and read.counters.unattributed_data_lines == 1
    assert read.gap


# -- a lost line may have been an event: nothing after it is attributed -------------------------


def test_a_non_text_entry_in_place_of_an_event_line_does_not_make_the_next_event_ordinal_0() -> (
    None
):
    """The reproduced failure: with the first event line replaced by ``None`` the second sell used to
    become ordinal 0, the identity of the first one, and collide with it in the recovery read."""
    tx = _amm(AMM_SELL_CASHBACK_X2)
    logs: list[Any] = list(_logs(tx))
    logs[_data_line_index(_logs(tx), 0)] = None
    read = _read(tx, logs=logs)
    assert read.swaps == ()  # nothing after the lost line is given an identity
    assert read.counters.malformed_lines == 1
    assert read.counters.unattributed_data_lines == 1 and read.gap


def test_log_truncated_before_a_later_event_keeps_the_prefix_and_attributes_nothing_after() -> None:
    """SYNTHETIC: ``Log truncated`` between the two sells of one transaction. The runtime may drop a
    big message, print the marker and keep later small ones, so the ordinal of what follows the marker
    is unknowable. The first event keeps the identity of the full read; the second is not emitted."""
    tx = _amm(AMM_SELL_CASHBACK_X2)
    logs = _logs(tx)
    clean = _read(tx).swaps
    second_line = _data_line_index(logs, 1)
    truncated = [*logs[:second_line], "Log truncated", *logs[second_line:]]
    read = _read(tx, logs=truncated)
    assert read.swaps == (clean[0],)
    assert read.counters.truncated_logs == 1
    assert read.counters.unattributed_data_lines == 1 and read.gap


def test_every_swap_a_damaged_read_emits_is_identical_to_the_one_the_full_read_gives() -> None:
    """Whatever single line is damaged (replaced by a non-text entry), the swaps that survive are a
    subset of the clean read's — same identity AND same content. Never a different event under a known id."""
    for directory, name in (
        ("pumpswap", AMM_SELL_CASHBACK_X2),
        ("pumpswap", AMM_BUY),
        ("pumpfun", V1_PUMP_BUY),
    ):
        tx = tx_fixture(directory, name)
        logs = _logs(tx)
        clean = {s.identity: s for s in _read(tx).swaps}
        for at in range(len(logs)):
            damaged: list[Any] = list(logs)
            damaged[at] = None
            for swap in _read(tx, logs=damaged).swaps:
                assert clean[swap.identity] == swap


# -- the ordinal the logs give is the one the self-CPI events give (all events, not only swaps) --


@pytest.mark.parametrize(
    ("directory", "name"),
    [
        ("pumpswap", AMM_BUY),
        ("pumpswap", AMM_BUY_EXACT),
        ("pumpswap", AMM_SELL),
        ("pumpswap", AMM_SELL_CASHBACK_X2),
        ("pumpswap", V1_AMM_SELL),
        ("pumpswap", V1_AMM_BUY_ROUTED),
        ("pumpswap", "t1a_rpc_amm_buy_routed_2HzxLVTqSFWq_raw.json"),
        ("pumpswap", "t1a_rpc_amm_buy_exact_3YxgSPJioUJp_raw.json"),
        ("pumpswap", "t1a_rpc_amm_buy_nocreator_4jyiFoCoVoWt_raw.json"),
        ("pumpfun", V1_PUMP_BUY),
        ("pumpfun", V1_PUMP_SELL),
    ],
)
def test_the_whole_event_sequence_of_each_program_is_the_same_in_the_logs_and_the_self_cpi(
    directory: str, name: str
) -> None:
    """Counting every event of the program (swap or not) before filtering: the ``Program data:`` lines
    attributed to it and its ``emit_cpi`` inner instructions are the same bytes in the same order, so
    an ordinal means the same thing on the live path and on a recovery from inner instructions.
    (Not a protocol guarantee — ``Program data:`` is generic output — but true of every real fixture.)"""
    tx = tx_fixture(directory, name)
    for program in (PUMP_PROGRAM_ID, PUMPSWAP_PROGRAM_ID):
        assert log_event_payloads(tx, program) == inner_event_bodies(tx, program)
