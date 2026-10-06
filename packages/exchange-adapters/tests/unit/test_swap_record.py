"""Wave 1a of H-030: how each of the three events becomes a ``SwapRecord`` — gross SOL leg, fees apart,
reserves after the trade, ``int`` units, UTC — and the guards that refuse an event whose numbers do not
add up. Real fixtures (``fixtures/t1a_provenance.json``); anything built by hand from their logs is
labelled SYNTHETIC.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest

from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.program_logs import (
    read_program_logs,
)
from hunter_exchanges.pumpfun.trade_event_codec import (
    TRADE_EVENT_DISCRIMINATOR,
    decode_trade_event,
)
from hunter_exchanges.pumpswap.buy_event import (
    BUY_EVENT_DISCRIMINATOR,
    decode_buy_event,
)
from hunter_exchanges.pumpswap.decode import PUMPSWAP_PROGRAM_ID
from hunter_exchanges.pumpswap.sell_event import (
    SELL_EVENT_DISCRIMINATOR,
    decode_sell_event,
)

from .t1a_chain import inner_event_payloads
from .t1a_logs import (
    AMM_BUY,
    AMM_BUY_EXACT,
    AMM_SELL,
    AMM_SELL_CASHBACK_X2,
    AMM_SELL_NEXT,
    RECEIVED,
    V1_AMM_SELL,
    V1_PUMP_BUY,
    V1_PUMP_SELL,
)
from .t1a_logs import (
    amm as _amm,
)
from .t1a_logs import data_line_index as _data_line_index
from .t1a_logs import (
    logs_of as _logs,
)
from .t1a_logs import payload_of as _payload
from .t1a_logs import (
    pump as _pump,
)
from .t1a_logs import (
    read as _read,
)
from .t1a_logs import (
    sig_of as _sig,
)
from .t1a_logs import with_payload as _with_payload

# -- normalisation: gross SOL leg, fees apart, native units, UTC --------------------------------


def test_a_pumpswap_buy_becomes_a_pool_swap_with_the_chain_numbers() -> None:
    tx = _amm(AMM_BUY)
    read = _read(tx)
    (swap,) = read.swaps
    event = decode_buy_event(
        inner_event_payloads(tx, PUMPSWAP_PROGRAM_ID, BUY_EVENT_DISCRIMINATOR)[0]
    )
    assert read.counters.swaps == 1 and not read.gap and read.problems == ()
    assert swap.identity == (_sig(tx), PUMPSWAP_PROGRAM_ID, 0)
    assert (swap.signature, swap.slot) == (_sig(tx), tx["slot"])
    assert (swap.program, swap.venue, swap.side) == (PUMPSWAP_PROGRAM_ID, "pool", "buy")
    assert swap.market == swap.pool == event.pool
    assert swap.mint is None  # the event names the pool; pool -> mint is the collector's lookup
    assert swap.wallet == event.user
    assert swap.sol_lamports == event.net_quote_in == 38_387_041
    assert swap.token_atoms == event.base_amount_out == 52_542_044_672
    assert swap.fee_lamports == event.fee_total == 76_775 + 19_194 + 364_677
    assert swap.sol_lamports + swap.fee_lamports == event.total_quote_paid == 38_847_687
    assert swap.fee_bps == 20 + 5 + 95
    assert swap.ix_name == "buy" and swap.quote_is_sol is None  # the event has no quote mint


def test_a_buy_exact_quote_in_is_normalised_by_meaning_not_by_field_name() -> None:
    (swap,) = _read(_amm(AMM_BUY_EXACT)).swaps
    assert swap.ix_name == "buy_exact_quote_in"
    assert swap.sol_lamports == 751_281  # net quote that priced the base
    assert swap.sol_lamports + swap.fee_lamports == 758_044  # what the user paid in total


def test_a_pumpswap_sell_nets_to_what_the_chain_paid_the_user_cashback_included() -> None:
    tx = _amm(AMM_SELL_CASHBACK_X2)
    read = _read(tx)
    events = [
        decode_sell_event(p)
        for p in inner_event_payloads(tx, PUMPSWAP_PROGRAM_ID, SELL_EVENT_DISCRIMINATOR)
    ]
    assert [s.cashback for s in events] == [21, 166]  # two real events, both with cashback
    assert [s.event_ordinal for s in read.swaps] == [0, 1]
    for swap, event in zip(read.swaps, events, strict=True):
        assert swap.side == "sell" and swap.venue == "pool" and swap.market == event.pool
        assert swap.sol_lamports == event.quote_amount_out  # gross of every fee
        assert swap.sol_lamports - swap.fee_lamports == event.user_quote_amount_out
        assert swap.token_atoms == event.base_amount_in
        assert (
            swap.fee_lamports
            == event.lp_fee + event.protocol_fee + event.coin_creator_fee + event.cashback
        )
    assert read.counters.swaps == 2 and not read.gap


def test_a_curve_trade_of_a_version_1_transaction_becomes_a_curve_swap() -> None:
    tx = _pump(V1_PUMP_BUY)
    assert tx["version"] == 1
    (swap,) = _read(tx).swaps
    event = decode_trade_event(
        inner_event_payloads(tx, PUMP_PROGRAM_ID, TRADE_EVENT_DISCRIMINATOR)[0]
    )
    assert (swap.venue, swap.side, swap.program) == ("curve", "buy", PUMP_PROGRAM_ID)
    assert swap.market == swap.mint == event.mint and swap.pool is None
    assert swap.wallet == event.user
    assert swap.sol_lamports == event.sol_amount  # gross of the fees
    assert swap.fee_lamports == event.fee + event.creator_fee + event.cashback
    assert swap.token_atoms == event.token_amount
    assert swap.quote_is_sol is True
    assert swap.reserves_source == "event_after"
    assert swap.lp_fee_lamports == 0
    assert swap.real_sol_reserves == event.real_sol_reserves
    assert (swap.sol_reserves, swap.token_reserves) == (
        event.virtual_sol_reserves,
        event.virtual_token_reserves,
    )


def test_a_curve_sell_nets_like_the_curve_event_says() -> None:
    (swap,) = _read(_pump(V1_PUMP_SELL)).swaps
    assert swap.side == "sell"
    event = decode_trade_event(
        inner_event_payloads(_pump(V1_PUMP_SELL), PUMP_PROGRAM_ID, TRADE_EVENT_DISCRIMINATOR)[0]
    )
    assert swap.sol_lamports - swap.fee_lamports == event.sell_net_proceeds


def test_pool_reserves_of_the_record_are_the_state_AFTER_the_trade() -> None:
    """The event reports the pool BEFORE its trade; the record moves it by the exact vault flow
    (buy: +quote in with LP fee, -base out; sell: -(gross - LP fee), +base in) so that every venue
    hands the tape a post-trade state. Checked against an independent witness: the reserves the
    NEXT trade of the same pool reports as its own "before". A one-off scan of 05/10 matched 61 of 61
    consecutive real pairs; the fixtures pin three of them (a buy pair, a sell pair, the cashback pair)."""
    for first_name, next_name, decode_next in (
        (AMM_BUY, "t1a_rpc_amm_buy_2EjiTbbdkX2L_raw.json", decode_buy_event),
        (AMM_SELL, AMM_SELL_NEXT, decode_sell_event),
    ):
        (first,) = _read(_amm(first_name)).swaps
        next_tx = _amm(next_name)
        disc = (
            BUY_EVENT_DISCRIMINATOR if decode_next is decode_buy_event else SELL_EVENT_DISCRIMINATOR
        )
        (payload,) = inner_event_payloads(next_tx, PUMPSWAP_PROGRAM_ID, disc)
        following = decode_next(payload)
        assert first.pool == following.pool
        assert first.reserves_source == "derived_after"
        assert first.sol_reserves == following.pool_quote_token_reserves
        assert first.token_reserves == following.pool_base_token_reserves
        assert first.real_sol_reserves is None


def test_the_two_cashback_sells_of_one_transaction_chain_through_the_pool() -> None:
    tx = _amm(AMM_SELL_CASHBACK_X2)
    first, second = _read(tx).swaps
    events = [
        decode_sell_event(p)
        for p in inner_event_payloads(tx, PUMPSWAP_PROGRAM_ID, SELL_EVENT_DISCRIMINATOR)
    ]
    assert first.pool == second.pool  # the fixture's two sells hit one pool
    assert first.sol_reserves == events[1].pool_quote_token_reserves
    assert first.token_reserves == events[1].pool_base_token_reserves


def test_the_record_carries_the_lp_fee_apart_so_the_vault_flow_can_be_rebuilt() -> None:
    (buy,) = _read(_amm(AMM_BUY)).swaps
    assert buy.lp_fee_lamports == 76_775
    assert buy.lp_fee_lamports < buy.fee_lamports  # LP is one of four fees
    (sell,) = _read(_amm(AMM_SELL)).swaps
    assert (sell.lp_fee_lamports, sell.sol_lamports) == (364_066, 145_626_232)


def test_every_number_is_an_int_and_every_time_is_utc() -> None:
    for tx, record in (
        (_amm(AMM_BUY), 0),
        (_pump(V1_PUMP_SELL), 0),
        (_amm(V1_AMM_SELL), 0),
    ):
        swap = _read(tx).swaps[record]
        for value in (
            swap.slot,
            swap.sol_lamports,
            swap.token_atoms,
            swap.fee_lamports,
            swap.fee_bps,
            swap.sol_reserves,
            swap.token_reserves,
        ):
            assert type(value) is int
        assert swap.block_time.utcoffset() == timedelta(0)
        assert swap.block_time == datetime.fromtimestamp(tx["blockTime"], tz=UTC)
        assert swap.received_at == RECEIVED


def test_received_at_must_be_utc_aware() -> None:
    tx = _amm(AMM_BUY)
    for bad in (
        datetime(2026, 10, 5, 23, 59),  # noqa: DTZ001 - the naive datetime is the point
        datetime(2026, 10, 5, 20, 59, tzinfo=timezone(timedelta(hours=-3))),
    ):
        with pytest.raises(ValueError, match="UTC"):
            read_program_logs(signature=_sig(tx), slot=1, logs=_logs(tx), received_at=bad)


def test_a_pool_trade_is_priced_with_the_virtual_quote_reserve_the_record_carries() -> None:
    """The pool's real quote reserve alone misprices the trade by ~15 % on a boosted pool (``can_boost``);
    adding the event's ``virtual_quote_reserves`` reproduces the chain's number to the lamport: a
    buy is exact-out (ceil), a sell exact-in (floor). The record holds the state AFTER the trade, so
    the state the trade was priced on is rebuilt with the LP fee the record also carries."""
    (buy,) = _read(_amm(AMM_BUY)).swaps
    sol_before = buy.sol_reserves - (buy.sol_lamports + buy.lp_fee_lamports)
    token_before = buy.token_reserves + buy.token_atoms
    priced = (sol_before + (buy.virtual_quote_reserves or 0)) * buy.token_atoms
    assert -(-priced // (token_before - buy.token_atoms)) == buy.sol_lamports
    real_only = -(-(sol_before * buy.token_atoms) // (token_before - buy.token_atoms))
    assert 10 * real_only < 9 * buy.sol_lamports  # the real reserve alone is wrong by > 10 %
    for sell in _read(_amm(AMM_SELL_CASHBACK_X2)).swaps:
        sol_before = sell.sol_reserves + (sell.sol_lamports - sell.lp_fee_lamports)
        token_before = sell.token_reserves - sell.token_atoms
        quoted = (sol_before + (sell.virtual_quote_reserves or 0)) * sell.token_atoms
        assert quoted // (token_before + sell.token_atoms) == sell.sol_lamports


def test_a_curve_record_has_no_separate_virtual_quote_reserve() -> None:
    """The curve's reserves in the event are already the virtual ones."""
    (swap,) = _read(_pump(V1_PUMP_BUY)).swaps
    assert swap.virtual_quote_reserves is None


def _patched(tx: dict[str, Any], offset: int, value: int, nth: int = 0) -> list[str]:
    logs = _logs(tx)
    at = _data_line_index(logs, nth)
    body = bytearray(_payload(logs, at))
    body[offset : offset + 8] = value.to_bytes(8, "little")
    return _with_payload(logs, at, bytes(body))


def test_a_buy_that_takes_more_base_than_the_pool_holds_is_not_emitted() -> None:
    """SYNTHETIC: the pool's base reserve (the 5th u64 after the timestamp) patched to 0."""
    tx = _amm(AMM_BUY)
    read = _read(tx, logs=_patched(tx, 8 + 8 + 4 * 8, 0))
    assert read.swaps == () and read.counters.unconserved == 1 and read.gap
    assert "takes" in read.problems[0].detail


def test_a_sell_that_pays_more_quote_than_the_pool_holds_is_not_emitted() -> None:
    """SYNTHETIC: the pool's quote reserve (the 6th u64 after the timestamp) patched to 0."""
    tx = _amm(AMM_SELL)
    read = _read(tx, logs=_patched(tx, 8 + 8 + 5 * 8, 0))
    assert read.swaps == () and read.counters.unconserved == 1 and read.gap
    assert "pays" in read.problems[0].detail


def test_an_event_timestamp_that_is_not_positive_is_undecodable() -> None:
    """SYNTHETIC: a real buy with its timestamp patched to 0."""
    tx = _amm(AMM_BUY)
    logs = _logs(tx)
    at = _data_line_index(logs)
    body = bytearray(_payload(logs, at))
    body[8:16] = (0).to_bytes(8, "little")
    read = _read(tx, logs=_with_payload(logs, at, bytes(body)))
    assert read.swaps == () and read.counters.undecodable == 1 and read.gap
    assert "timestamp" in read.problems[0].detail
