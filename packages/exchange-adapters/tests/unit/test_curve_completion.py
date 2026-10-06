"""Wave 1b of H-030, part 1: does the curve record say whether the curve was complete AT THE EVENT?

What the chain gives (``fixtures/t1b_provenance.json``, real transactions of 05/10/2026):

* The post-upgrade ``TradeEvent`` has **no** ``complete`` flag (the on-chain IDL lists it only on the
  ``BondingCurve`` account, which can only be read later) but it carries ``real_token_reserves`` AFTER
  the trade. A buy that drains the curve (``real_token_reserves == 0``) is followed, in the same
  transaction, by a ``CompleteEvent`` naming the same mint.
* So completion is read point-in-time as a named tri-state: ``complete`` / ``not_complete`` /
  ``unknown``, from the event's own reserves and CORROBORATED by the transaction's own
  ``CompleteEvent`` (never by any later account read, which would be look-ahead). Anything the two
  disagree on, or that the rule cannot hold for, is ``unknown``.

Real fixtures decide the rule; whatever is built by hand from their logs is labelled SYNTHETIC.
"""

from __future__ import annotations

import base64
from typing import Any

import pytest

from hunter_exchanges.pumpfun.curve_completion import (
    COMPLETE_EVENT_DISCRIMINATOR,
    CompleteEvent,
    decode_complete_event,
)
from hunter_exchanges.pumpfun.decode import NATIVE_SOL_QUOTE_MINT, PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.pdas import bonding_curve_address
from hunter_exchanges.pumpfun.solana_codec import b58decode
from hunter_exchanges.pumpfun.trade_event_codec import (
    TRADE_EVENT_DISCRIMINATOR,
    TradeEvent,
    decode_trade_event,
)

from .t1a_chain import FIXTURES, load, log_event_payloads
from .t1a_logs import (
    AMM_BUY,
    PREFIX,
    V1_PUMP_BUY,
    V1_PUMP_SELL,
    amm,
    data_line_index,
    logs_of,
    payload_of,
    pump,
    read,
    with_payload,
)

COMPLETES = "t1b_rpc_pump_buy_completes_curve_fnG6AdqJEF_raw.json"
BEFORE = "t1b_rpc_pump_buy_before_complete_4j1Hpws2fH_raw.json"
CREATE_THEN_COMPLETES = "t1b_rpc_pump_create_buy_completes_curve_43xbmthGPT_raw.json"
_TRADE_RTR_OFFSET = 8 + 32 + 8 + 8 + 1 + 32 + 8 + 8 + 8 + 8  # disc ... real_sol_reserves, then rtr


def _trade_events(tx: dict[str, Any]) -> list[TradeEvent]:
    return [
        decode_trade_event(p)
        for p in log_event_payloads(tx, PUMP_PROGRAM_ID)
        if p[:8] == TRADE_EVENT_DISCRIMINATOR
    ]


def _complete_events(tx: dict[str, Any]) -> list[CompleteEvent]:
    return [
        decode_complete_event(p)
        for p in log_event_payloads(tx, PUMP_PROGRAM_ID)
        if p[:8] == COMPLETE_EVENT_DISCRIMINATOR
    ]


# -- the premise, from the program's own IDL ------------------------------------------------------


def test_the_idl_has_no_complete_flag_on_the_trade_event_only_on_the_curve_account() -> None:
    idl = load("pumpfun/idl_pump_onchain_raw.json")
    fields: dict[str, list[str]] = {
        t["name"]: [f["name"] for f in t["type"]["fields"] if isinstance(f, dict)]
        for t in idl["types"]
        if isinstance(t["type"], dict) and "fields" in t["type"]
    }
    assert "complete" not in fields["TradeEvent"]
    assert "real_token_reserves" in fields["TradeEvent"]
    assert "complete" in fields["BondingCurve"]  # readable only from the account, i.e. later
    assert [e for e in idl["events"] if e["name"] == "CompleteEvent"][0]["discriminator"] == list(
        COMPLETE_EVENT_DISCRIMINATOR
    )


# -- the CompleteEvent decoder, against real events -----------------------------------------------


def test_the_complete_event_decodes_to_the_mint_the_trade_drained() -> None:
    for name in (COMPLETES, CREATE_THEN_COMPLETES):
        tx = pump(name)
        (trade,) = _trade_events(tx)
        (done,) = _complete_events(tx)
        assert done.mint == trade.mint and done.user == trade.user
        assert done.timestamp == trade.timestamp
        assert done.bonding_curve == bonding_curve_address(trade.mint)  # the PDA, not a lookup
        assert done.quote_mint == NATIVE_SOL_QUOTE_MINT


def test_a_complete_event_of_another_length_is_refused_not_guessed() -> None:
    payload = log_event_payloads(pump(COMPLETES), PUMP_PROGRAM_ID)[-1]
    assert payload[:8] == COMPLETE_EVENT_DISCRIMINATOR and len(payload) == 144
    for bad in (payload[:-1], payload + b"\0", payload[:8], b"\0" * 144):
        with pytest.raises(ValueError):
            decode_complete_event(bad)


# -- the rule on real transactions ----------------------------------------------------------------


def test_a_buy_that_drains_the_curve_is_complete_at_the_event() -> None:
    for name in (COMPLETES, CREATE_THEN_COMPLETES):
        tx = pump(name)
        r = read(tx)
        (swap,) = [s for s in r.swaps if s.venue == "curve"]
        assert (swap.side, swap.real_token_reserves) == ("buy", 0)
        assert swap.curve_completion == "complete" and swap.curve_complete is True
        assert r.counters.curve_completion_unknown == 0 and not r.gap


def test_the_complete_event_comes_after_the_draining_trade_in_the_same_transaction() -> None:
    """The independent witness of the rule: the program says "complete" itself, once, right after
    the trade whose ``real_token_reserves`` reads 0 (event order from a plain log walk)."""
    for name in (COMPLETES, CREATE_THEN_COMPLETES):
        events = log_event_payloads(pump(name), PUMP_PROGRAM_ID)
        kinds = [e[:8] for e in events]
        assert kinds.count(COMPLETE_EVENT_DISCRIMINATOR) == 1
        trade_at = kinds.index(TRADE_EVENT_DISCRIMINATOR)
        assert kinds.index(COMPLETE_EVENT_DISCRIMINATOR) == trade_at + 1


def test_the_buy_before_it_leaves_the_curve_not_complete() -> None:
    tx = pump(BEFORE)
    r = read(tx)
    (swap,) = r.swaps
    assert swap.real_token_reserves is not None and swap.real_token_reserves > 0
    assert swap.curve_completion == "not_complete" and swap.curve_complete is False
    assert _complete_events(tx) == []


def test_the_draining_buy_takes_exactly_what_the_previous_trade_left() -> None:
    """Chain evidence that ``real_token_reserves`` is the state AFTER the trade and moves by the
    trade's own tokens: the previous trade of the same mint left X, the next buy took X, leaving 0."""
    (before,) = _trade_events(pump(BEFORE))
    (after,) = _trade_events(pump(COMPLETES))
    assert before.mint == after.mint and before.is_buy and after.is_buy
    assert before.real_token_reserves - after.token_amount == after.real_token_reserves == 0


def test_the_trade_ordinal_does_not_change_the_rule() -> None:
    (swap,) = [s for s in read(pump(CREATE_THEN_COMPLETES)).swaps]
    assert swap.event_ordinal == 1  # an event of another kind came first
    assert swap.curve_completion == "complete"


def test_version_1_curve_trades_are_not_complete() -> None:
    for name in (V1_PUMP_BUY, V1_PUMP_SELL):
        (swap,) = read(pump(name)).swaps
        assert swap.real_token_reserves is not None and swap.real_token_reserves > 0
        assert swap.curve_completion == "not_complete"
        assert swap.real_token_reserves == _trade_events(pump(name))[0].real_token_reserves


def test_a_pool_record_has_no_curve_completion() -> None:
    (swap,) = read(amm(AMM_BUY)).swaps
    assert (swap.curve_completion, swap.curve_complete, swap.real_token_reserves) == (
        None,
        None,
        None,
    )


# -- what the rule refuses to call -----------------------------------------------------------------


def _patch_real_token_reserves(tx: dict[str, Any], value: int) -> list[str]:
    logs = logs_of(tx)
    for n, line in enumerate(logs):
        if line.startswith(PREFIX):
            body = payload_of(logs, n)
            if body[:8] == TRADE_EVENT_DISCRIMINATOR:
                patched = bytearray(body)
                patched[_TRADE_RTR_OFFSET : _TRADE_RTR_OFFSET + 8] = value.to_bytes(8, "little")
                return with_payload(logs, n, bytes(patched))
    raise AssertionError("no trade event")


def test_a_sell_that_reads_zero_real_tokens_is_unknown_not_complete() -> None:
    """SYNTHETIC: the v1 sell with ``real_token_reserves`` patched to 0. A sell ADDS tokens to the
    curve, so 0 after it contradicts the rule; the record says so instead of picking a side."""
    tx = pump(V1_PUMP_SELL)
    r = read(tx, logs=_patch_real_token_reserves(tx, 0))
    (swap,) = r.swaps
    assert swap.side == "sell" and swap.real_token_reserves == 0
    assert swap.curve_completion == "unknown" and swap.curve_complete is None
    assert r.counters.curve_completion_unknown == 1


def test_a_draining_buy_without_the_programs_own_complete_event_is_unknown() -> None:
    """SYNTHETIC: the real draining buy with the ``CompleteEvent`` line removed."""
    tx = pump(COMPLETES)
    logs = logs_of(tx)
    at = [n for n, line in enumerate(logs) if line.startswith(PREFIX)][-1]
    assert payload_of(logs, at)[:8] == COMPLETE_EVENT_DISCRIMINATOR
    r = read(tx, logs=[*logs[:at], *logs[at + 1 :]])
    (swap,) = r.swaps
    assert swap.real_token_reserves == 0 and swap.curve_completion == "unknown"
    assert r.counters.curve_completion_unknown == 1


def test_a_not_complete_trade_followed_by_a_complete_event_of_its_mint_is_unknown() -> None:
    """SYNTHETIC: the real not-complete buy plus a ``CompleteEvent`` for the same mint copied from
    the draining transaction and re-pointed at this mint. The two statements contradict."""
    before_tx = pump(BEFORE)
    done_tx = pump(COMPLETES)
    (trade,) = _trade_events(before_tx)
    done_payload = bytearray(log_event_payloads(done_tx, PUMP_PROGRAM_ID)[-1])
    done_payload[40:72] = b58decode(trade.mint)
    logs = logs_of(before_tx)
    at = data_line_index(logs)
    injected = PREFIX + base64.b64encode(bytes(done_payload)).decode()
    r = read(before_tx, logs=[*logs[: at + 1], injected, *logs[at + 1 :]])
    (swap,) = r.swaps
    assert swap.real_token_reserves and swap.curve_completion == "unknown"
    assert r.counters.curve_completion_unknown == 1


def test_a_complete_event_for_a_mint_with_no_trade_in_the_transaction_changes_nothing() -> None:
    """SYNTHETIC: the not-complete buy and a ``CompleteEvent`` of ANOTHER mint (the original one)."""
    before_tx = pump(BEFORE)
    done_payload = log_event_payloads(pump(COMPLETES), PUMP_PROGRAM_ID)[-1]
    logs = logs_of(before_tx)
    at = data_line_index(logs)
    # the real completing event names this same mint (BEFORE is its predecessor): re-point it at
    # 32 bytes of 0x01, a mint nothing in this transaction trades
    other = bytearray(done_payload)
    other[40:72] = b"\x01" * 32
    injected = PREFIX + base64.b64encode(bytes(other)).decode()
    r = read(before_tx, logs=[*logs[: at + 1], injected, *logs[at + 1 :]])
    (swap,) = r.swaps
    assert swap.curve_completion == "not_complete" and r.counters.curve_completion_unknown == 0


def test_two_trades_of_one_mint_the_second_one_draining_complete_only_the_second() -> None:
    """SYNTHETIC: one transaction narrating the real not-complete buy and then the real draining
    buy of the same mint (both frames concatenated). The ``CompleteEvent`` closes the LAST trade of
    its mint before it, so the first stays not complete."""
    first, second = pump(BEFORE), pump(COMPLETES)
    logs = [*logs_of(first), *logs_of(second)]
    r = read(first, logs=logs)
    assert [s.curve_completion for s in r.swaps] == ["not_complete", "complete"]
    assert r.counters.curve_completion_unknown == 0


def test_the_completion_fields_are_on_the_record_and_pool_legs_are_not_confused_with_them() -> None:
    (swap,) = read(pump(COMPLETES)).swaps
    assert swap.base_mint is None and swap.quote_mint is None  # a curve has no pool legs
    assert swap.quote_is_sol is True


def test_the_fixtures_are_where_the_provenance_says() -> None:
    assert (FIXTURES / "pumpfun" / COMPLETES).is_file()


def _without_trade_line(tx: dict[str, Any]) -> list[str]:
    logs = logs_of(tx)
    at = [n for n, line in enumerate(logs) if line.startswith(PREFIX)]
    (trade_at,) = [n for n in at if payload_of(logs, n)[:8] == TRADE_EVENT_DISCRIMINATOR]
    return [*logs[:trade_at], *logs[trade_at + 1 :]]


def test_a_complete_event_with_no_trade_before_it_is_a_gap_not_a_clean_read() -> None:
    """SYNTHETIC (Astra, wallets-1b-record): the real draining buy with only its ``TradeEvent`` line
    removed. The program says the curve completed and the trade that did it is missing: the collector
    must record a gap, not declare the transaction fully read."""
    tx = pump(COMPLETES)
    r = read(tx, logs=_without_trade_line(tx))
    assert r.swaps == () and r.counters.orphan_complete_events == 1 and r.gap


def test_a_refused_trade_still_holds_the_place_that_closes_the_complete_event() -> None:
    """SYNTHETIC: the not-complete buy and then the draining buy of the same mint, the second one's
    ``TradeEvent`` corrupted (undecodable). The ``CompleteEvent`` closes THAT trade, not the first
    one: the first must stay ``not_complete`` (it was wrongly turned ``unknown``) and the gap is
    reported."""
    first, second = pump(BEFORE), pump(COMPLETES)
    second_logs = logs_of(second)
    at = [n for n, line in enumerate(second_logs) if line.startswith(PREFIX)][0]
    broken = with_payload(second_logs, at, payload_of(second_logs, at)[:-3])  # truncated body
    r = read(first, logs=[*logs_of(first), *broken])
    assert [s.curve_completion for s in r.swaps] == ["not_complete"]
    assert r.counters.undecodable == 1 and r.counters.curve_completion_unknown == 0 and r.gap
    assert r.counters.orphan_complete_events == 0


def test_a_trade_line_that_is_not_even_base64_also_keeps_its_place() -> None:
    """SYNTHETIC: as above but the second ``TradeEvent`` line is not base64 at all. It may have been
    the trade the ``CompleteEvent`` closes, so the first buy is still not turned ``unknown``."""
    first, second = pump(BEFORE), pump(COMPLETES)
    second_logs = logs_of(second)
    at = [n for n, line in enumerate(second_logs) if line.startswith(PREFIX)][0]
    broken = [*second_logs[:at], PREFIX + "!!not base64!!", *second_logs[at + 1 :]]
    r = read(first, logs=[*logs_of(first), *broken])
    assert [s.curve_completion for s in r.swaps] == ["not_complete"]
    assert r.counters.bad_base64 == 1 and r.counters.curve_completion_unknown == 0 and r.gap


def test_a_complete_event_whose_closing_trade_still_holds_tokens_is_also_a_gap() -> None:
    """SYNTHETIC (Astra + code-reviewer, round 2): the real not-complete buy of a mint, then the
    ``CompleteEvent`` of the draining buy, with the draining ``TradeEvent`` line removed. The
    ``CompleteEvent`` has a predecessor of its mint, but that predecessor says the curve still held
    tokens: the draining trade is missing, so the transaction is a gap, not a clean ``unknown``."""
    first, second = pump(BEFORE), pump(COMPLETES)
    r = read(first, logs=[*logs_of(first), *_without_trade_line(second)])
    assert [s.curve_completion for s in r.swaps] == ["unknown"]
    assert r.counters.orphan_complete_events == 1 and r.counters.curve_completion_unknown == 1
    assert r.gap
