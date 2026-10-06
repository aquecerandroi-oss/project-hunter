"""Wave 1a of H-030: what the program-logs reader does when the logs are damaged around the events —
an event line with no frame, a missing line, a suffix cut with no marker. Real fixtures
(``fixtures/t1a_provenance.json``); anything built by hand from their logs is labelled SYNTHETIC.
"""

from __future__ import annotations

from .t1a_chain import (
    tx_fixture,
)
from .t1a_logs import (
    AMM_BUY,
    AMM_SELL_CASHBACK_X2,
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

# -- a line with no context, a missing line, a cut suffix --------------------------------------


def _second_frame_start(logs: list[str]) -> int:
    """Index of the ``invoke [1]`` line that opens the frame holding the second event line."""
    second = _data_line_index(logs, 1)
    return max(i for i in range(second) if logs[i].endswith(" invoke [1]"))


def test_an_orphan_data_line_followed_by_a_full_frame_does_not_take_the_first_identity() -> None:
    """The residual case a reviewer reproduced on the two-sell fixture: event 0's data line is kept but
    its invoke context is gone, then the second sell's frame arrives whole. The orphan only counted as
    unattributed, so the second sell became ordinal 0 (token_atoms 976016 under the identity of the
    sell of 121423). Now the orphan blinds the read: nothing after it is given an identity."""
    tx = _amm(AMM_SELL_CASHBACK_X2)
    logs = _logs(tx)
    clean = {s.identity: s for s in _read(tx).swaps}
    assert len(clean) == 2
    damaged = [logs[_data_line_index(logs, 0)], *logs[_second_frame_start(logs) :]]
    read = _read(tx, logs=damaged)
    assert read.swaps == ()
    assert read.counters.unattributed_data_lines >= 1 and read.gap
    for swap in read.swaps:  # (vacuous now; the invariant that matters for any damage)
        assert clean[swap.identity] == swap


def test_a_missing_context_line_never_gives_a_known_identity_to_a_different_event() -> None:
    """Delete, one at a time, every line that is NOT an event line (invoke, return, logs, consumed
    units...): whatever survives is identical, in identity and content, to the clean read. (A deleted
    event line inside an intact frame cannot be seen from the logs alone: only the inner instructions
    would tell.)"""
    for directory, name in (
        ("pumpswap", AMM_SELL_CASHBACK_X2),
        ("pumpswap", AMM_BUY),
        ("pumpfun", V1_PUMP_BUY),
    ):
        tx = tx_fixture(directory, name)
        logs = _logs(tx)
        clean = {s.identity: s for s in _read(tx).swaps}
        for at, line in enumerate(logs):
            if line.startswith(_PREFIX):
                continue
            for swap in _read(tx, logs=[*logs[:at], *logs[at + 1 :]]).swaps:
                assert clean[swap.identity] == swap


def test_a_log_that_ends_inside_an_open_frame_is_a_gap_even_without_a_marker() -> None:
    """The second reproduced case: the logs cut right before the second event line (a lost suffix, no
    ``Log truncated``). It used to read clean with one swap; the second sell vanished silently."""
    tx = _amm(AMM_SELL_CASHBACK_X2)
    logs = _logs(tx)
    cut = logs[: _data_line_index(logs, 1)]
    read = _read(tx, logs=cut)
    assert len(read.swaps) == 1 and read.swaps[0] == _read(tx).swaps[0]  # the prefix is still read
    assert read.counters.open_frames_at_end == 1 and read.gap


def test_every_cut_that_leaves_a_frame_open_is_a_gap() -> None:
    """For every prefix of the logs, an open invoke stack at the end means a lost suffix."""
    tx = _amm(AMM_SELL_CASHBACK_X2)
    logs = _logs(tx)
    depth = 0
    for k in range(1, len(logs)):
        line = logs[k - 1]
        if " invoke [" in line:
            depth += 1
        elif line.startswith("Program ") and (line.endswith(" success") or " failed" in line):
            depth -= 1
        read = _read(tx, logs=logs[:k])
        if depth > 0:
            assert read.gap, k
        else:
            assert read.counters.open_frames_at_end == 0, k


def test_a_complete_transaction_ends_with_an_empty_stack() -> None:
    for directory, name in (
        ("pumpswap", AMM_BUY),
        ("pumpfun", V1_PUMP_SELL),
        ("pumpswap", V1_AMM_SELL),
    ):
        read = _read(tx_fixture(directory, name))
        assert read.counters.open_frames_at_end == 0 and not read.gap
