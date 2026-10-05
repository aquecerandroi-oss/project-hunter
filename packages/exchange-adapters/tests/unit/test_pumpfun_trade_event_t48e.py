"""T4.8e: the pump program redeployed on 2026-10-02 (slot 452654932, 15:47:21Z) appends one
more, unnamed ``u64`` to ``TradeEvent`` — 24 bytes after the variable fields (the
``holder_rewards`` pair + this one). Every real fill after that was refused
(``decode_fills`` raised; ``trade_events_from_logs`` returned ``()`` without a word).

Fixtures ``t48e_rpc_tx_*_raw.json``: real ``getTransaction`` results read from the public
RPC on 2026-10-05 (slot 453609715), read-only, no ``sendTransaction``.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pytest

from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.trade_event import (
    LAYOUT_HOLDER_REWARDS,
    LAYOUT_PRE_HOLDER_REWARDS,
    LAYOUT_TRAILING_U64,
    TRADE_EVENT_DISCRIMINATOR,
    decode_trade_event,
    scan_trade_event_logs,
    trade_events_from_logs,
    trade_events_from_transaction,
)

FIXTURES = Path(__file__).parents[1] / "fixtures/pumpfun"
_PREFIX = "Program data: "


def _tx(name: str, *, wrapped: bool = False) -> dict[str, Any]:
    data = json.loads((FIXTURES / name).read_text())
    return data["result"] if wrapped else data


def _raw_of(tx: dict[str, Any]) -> bytes:
    for line in tx["meta"]["logMessages"]:
        if line.startswith(_PREFIX):
            raw = base64.b64decode(line[len(_PREFIX) :])
            if raw[:8] == TRADE_EVENT_DISCRIMINATOR:
                return raw
    raise AssertionError("no TradeEvent log line")


def _probe_raw() -> bytes:
    """The 359-byte pre-2026-09-12 event of the T4.8 fixture: the base to append tails to."""
    return _raw_of(_tx("rpc_tx_probe_raw.json", wrapped=True))


def _log(raw: bytes) -> str:
    return _PREFIX + base64.b64encode(raw).decode()


# ``(fixture, ix_name, is_buy, sol_amount, trailing_u64)`` — read off the chain on 2026-10-05.
_REAL = [
    ("t48e_rpc_tx_buy_2qnMHiEaNfxX_raw.json", "buy", True, 15_660_499, 0),
    ("t48e_rpc_tx_buy_3JLToMLjc2mt_raw.json", "buy", True, 1_000_000_001, 89_139),
    ("t48e_rpc_tx_buy_57oJq3tbU7aa_raw.json", "buy", True, 97_777_777, 34_142),
    ("t48e_rpc_tx_sell_2DSRRspQNw13_raw.json", "sell", False, 97_777_776, 0),
    ("t48e_rpc_tx_sell_61x6SRWNuLhg_raw.json", "sell", False, 263_233_315, 618_215),
    ("t48e_rpc_tx_37XpnUmxsTdv_raw.json", "sell", False, 4_167_796, 0),
]


@pytest.mark.parametrize(("name", "ix_name", "is_buy", "sol", "tail"), _REAL)
def test_real_post_upgrade_events_decode_and_report_the_tail(
    name: str, ix_name: str, is_buy: bool, sol: int, tail: int
) -> None:
    tx = _tx(name)
    (event,) = trade_events_from_transaction(tx, program_id=PUMP_PROGRAM_ID)
    assert event.layout == LAYOUT_TRAILING_U64
    assert (event.ix_name, event.is_buy, event.sol_amount) == (ix_name, is_buy, sol)
    assert event.trailing_u64 == tail  # a real ``0`` is a reading, not an absence
    # the inner-instruction path, the logs-only path and the subscription path agree
    logs_only = {"meta": {"logMessages": tx["meta"]["logMessages"], "err": None}, "transaction": {}}
    assert trade_events_from_transaction(logs_only, program_id=PUMP_PROGRAM_ID) == (event,)
    assert trade_events_from_logs(tx["meta"]["logMessages"]) == (event,)
    # self-consistent: the native-SOL quote mirrors the SOL amounts, the timestamp is the block's
    assert event.quote_amount == event.sol_amount
    assert event.quote_mint == "11111111111111111111111111111111"
    assert event.timestamp == tx["blockTime"]


def test_the_unnamed_tail_is_reported_and_never_summed() -> None:
    """Its meaning is unknown (values seen 0..39 743 440): the money arithmetic must not move
    with it — the payer's real balance delta stays the ledger's truth (§9.6)."""
    raw = _probe_raw()
    hr = (50).to_bytes(8, "little") + (1234).to_bytes(8, "little")
    with_zero = decode_trade_event(raw + hr + (0).to_bytes(8, "little"))
    with_big = decode_trade_event(raw + hr + (39_743_440).to_bytes(8, "little"))
    assert with_zero.layout == with_big.layout == LAYOUT_TRAILING_U64
    assert (with_zero.trailing_u64, with_big.trailing_u64) == (0, 39_743_440)
    assert (with_big.holder_rewards_basis_points, with_big.holder_rewards) == (50, 1234)
    assert with_big.sol_deducted_from_user == with_zero.sol_deducted_from_user
    assert with_big.buy_total_cost == with_zero.buy_total_cost
    assert with_big.sell_net_proceeds == with_zero.sell_net_proceeds
    # earlier layouts carry no tail at all: ``None``, never a fabricated 0
    assert decode_trade_event(raw).trailing_u64 is None
    assert decode_trade_event(raw + hr).trailing_u64 is None


@pytest.mark.parametrize("extra", [1, 7, 8, 17, 23, 25, 31, 32, 40])
def test_any_other_trailing_length_is_still_refused(extra: int) -> None:
    """Only the three lengths seen on chain (0, 16, 24) are layouts; the next unknown one
    must fail loudly instead of being read as a fill."""
    with pytest.raises(ValueError, match=f"{extra} trailing bytes"):
        decode_trade_event(_probe_raw() + b"\x00" * extra)


def test_the_tail_is_validated_after_the_variable_fields_not_by_total_length() -> None:
    """``ix_name`` (``buy`` / ``sell`` / ``buy_exact_quote_in``) and ``shareholders`` change
    the body size: a fixed 383-byte rule would fix sells and keep refusing buys (Astra, 05/10)."""
    sizes: set[tuple[str, int]] = set()
    for name, ix_name, *_ in _REAL:
        raw = _raw_of(_tx(name))
        sizes.add((ix_name, len(raw)))
        assert decode_trade_event(raw).ix_name == ix_name
    assert ("buy", 382) in sizes and ("sell", 383) in sizes  # two real totals, one rule


def test_the_pre_upgrade_real_fixtures_still_decode_unchanged() -> None:
    """The T4.8 / T4.8b / T4.8d fixtures (359 and 375 bytes): same layouts, no tail."""
    for name, layout in (
        ("rpc_tx_probe_raw.json", LAYOUT_PRE_HOLDER_REWARDS),
        ("t48b_rpc_tx_sell_raw.json", LAYOUT_HOLDER_REWARDS),
        ("t48d_rpc_tx_sell_nonmayhem_raw.json", LAYOUT_HOLDER_REWARDS),
        ("t48d_rpc_tx_buy_nonmayhem_raw.json", LAYOUT_HOLDER_REWARDS),
    ):
        (event,) = trade_events_from_transaction(
            _tx(name, wrapped=True), program_id=PUMP_PROGRAM_ID
        )
        assert event.layout == layout, name
        assert event.trailing_u64 is None, name


# -- the logs scan: "no TradeEvent" is not "a TradeEvent we could not read" ------------------


def test_scan_separates_a_notification_without_a_trade_event_from_an_undecodable_one() -> None:
    tx = _tx("t48e_rpc_tx_sell_61x6SRWNuLhg_raw.json")
    # (a) a non-trade instruction on the same PDA: nothing trade-shaped, nothing lost
    quiet = scan_trade_event_logs(["Program 111 invoke [1]", "Program data: AAAA", "success"])
    assert quiet.events == () and quiet.undecodable == () and not quiet.lost
    # (b) a real post-upgrade fill: decoded
    good = scan_trade_event_logs(tx["meta"]["logMessages"])
    assert len(good.events) == 1 and good.undecodable == () and not good.lost
    # (c) a TradeEvent of a layout nobody has seen: reported, never silently empty
    unknown = _probe_raw() + b"\x00" * 7
    scan = scan_trade_event_logs([f"Program {PUMP_PROGRAM_ID} invoke [1]", _log(unknown)])
    assert scan.events == () and scan.lost
    assert len(scan.undecodable) == 1 and "7 trailing bytes" in scan.undecodable[0]
    # (d) a truncated one too
    assert scan_trade_event_logs([_log(_probe_raw()[:-1])]).lost
    # (e) one good + one bad line in the same notification: both facts survive
    mixed = scan_trade_event_logs([_log(unknown), *tx["meta"]["logMessages"]])
    assert len(mixed.events) == 1 and len(mixed.undecodable) == 1 and mixed.lost


def test_trade_events_from_logs_keeps_its_contract_for_callers_that_only_want_events() -> None:
    assert trade_events_from_logs([_log(_probe_raw() + b"\x00" * 7)]) == ()


def test_a_watched_wallets_post_upgrade_fill_is_a_trade_event_fill_not_an_unknown() -> None:
    """The wallet collector (T4.12) used to persist ``unknown`` + ``event_error`` for these."""
    from hunter_exchanges.pumpfun.wallet_fills import wallet_fills_from_transaction

    tx = _tx("t48e_rpc_tx_sell_61x6SRWNuLhg_raw.json")
    (event,) = trade_events_from_transaction(tx, program_id=PUMP_PROGRAM_ID)
    (fill,) = wallet_fills_from_transaction(tx, wallet=event.user, signature="sig")
    assert (fill.side, fill.venue, fill.decode) == ("sell", "curve", "trade_event")


def test_the_tail_is_found_after_a_non_empty_shareholders_vector() -> None:
    """Synthetic (no real event carries shareholders yet): the ``shareholders`` vector is a
    variable-length field *before* the tail, so a body of any other size must still decode."""
    raw = _probe_raw()
    count_at = len(raw) - (32 + 3 * 8) - 4  # quote_mint + three u64 follow the u32 count
    assert raw[count_at : count_at + 4] == b"\x00\x00\x00\x00"
    holders = (b"\x07" * 32 + (6000).to_bytes(2, "little")) + (
        b"\x08" * 32 + (4000).to_bytes(2, "little")
    )
    widened = raw[:count_at] + (2).to_bytes(4, "little") + holders + raw[count_at + 4 :]
    tail = (0).to_bytes(8, "little") * 2 + (123).to_bytes(8, "little")
    event = decode_trade_event(widened + tail)
    assert [bps for _, bps in event.shareholders] == [6000, 4000]
    assert event.layout == LAYOUT_TRAILING_U64 and event.trailing_u64 == 123
    assert len(widened + tail) - len(raw) == 68 + 24  # a size no fixed-length rule would accept
    with pytest.raises(ValueError, match="8 trailing bytes"):
        decode_trade_event(widened + tail[:8])


# -- T4.8f (guardian): attribute ``Program data`` lines to the pump program ----------------

_OTHER = "DRVSpZ2YUYYKgZP8XtLhAGtT1zYSCKzeHfb4DgRnrgqD"


def test_a_trade_event_shaped_line_of_another_program_is_not_ours_and_not_a_loss() -> None:
    """Another program's ``Program data`` that happens to start with our discriminator and
    does not decode must not mark a gap on the mint (a spurious, fail-closed gap)."""
    garbage = _log(_probe_raw() + b"\x00" * 7)
    foreign = scan_trade_event_logs(
        [f"Program {_OTHER} invoke [1]", garbage, f"Program {_OTHER} success"]
    )
    assert foreign.events == () and foreign.undecodable == () and not foreign.lost
    # the same line under the pump program is a real loss
    ours = scan_trade_event_logs(
        [f"Program {PUMP_PROGRAM_ID} invoke [1]", garbage, f"Program {PUMP_PROGRAM_ID} success"]
    )
    assert ours.lost and len(ours.undecodable) == 1
    # a decodable event of another program is not ours either
    good = _log(_probe_raw())
    other_good = scan_trade_event_logs(
        [f"Program {_OTHER} invoke [1]", good, f"Program {_OTHER} success"]
    )
    assert other_good.events == ()


def test_attribution_follows_the_invoke_stack_of_the_real_transaction() -> None:
    """A real post-upgrade sell: the ``TradeEvent`` line sits under the pump program's
    ``invoke [1]``, after the nested fee-program and token calls returned."""
    tx = _tx("t48e_rpc_tx_sell_61x6SRWNuLhg_raw.json")
    scan = scan_trade_event_logs(tx["meta"]["logMessages"])
    assert len(scan.events) == 1 and not scan.lost
    # a router (``invoke [1]``) that calls the pump program as ``invoke [2]``
    wrapped = [
        f"Program {_OTHER} invoke [1]",
        f"Program {PUMP_PROGRAM_ID} invoke [2]",
        _log(_raw_of(tx)),
        f"Program {PUMP_PROGRAM_ID} success",
        f"Program {_OTHER} success",
    ]
    assert len(scan_trade_event_logs(wrapped).events) == 1
    # after the pump call returned, the router's own line is the router's
    after = [*wrapped[:4], _log(_probe_raw() + b"\x00" * 7), *wrapped[4:]]
    assert not scan_trade_event_logs(after).lost


def test_a_line_with_no_invoke_context_is_assumed_ours() -> None:
    """Truncated or synthetic logs (no ``invoke`` line seen): unknown attribution must err
    toward counting the loss, never toward silence."""
    assert scan_trade_event_logs([_log(_probe_raw() + b"\x00" * 7)]).lost
    assert len(scan_trade_event_logs([_log(_probe_raw())]).events) == 1


def test_a_failed_nested_call_pops_the_stack() -> None:
    lines = [
        f"Program {PUMP_PROGRAM_ID} invoke [1]",
        f"Program {_OTHER} invoke [2]",
        f"Program {_OTHER} failed: custom program error: 0x1",
        _log(_probe_raw() + b"\x00" * 7),  # back under the pump program
        f"Program {PUMP_PROGRAM_ID} success",
    ]
    assert scan_trade_event_logs(lines).lost
