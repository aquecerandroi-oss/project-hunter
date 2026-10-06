"""Wave 1a of H-030: the PumpSwap ``BuyEvent`` decoder (36 % of the program's swaps; the wave-0
probe counted it raw because no decoder existed).

Fixtures ``t1a_rpc_*amm_buy*_raw.json``: real ``getTransaction`` results of third parties' buys,
all AFTER the 2026-10-02 15:47Z redeploy, read from the public RPC on 2026-10-05 (provenance:
``fixtures/t1a_provenance.json``). The decoder is checked against what the chain itself says —
instruction accounts 0/1 = pool/user, SPL balance deltas — not against its own output. Synthetic
bodies are built from a REAL body and are labelled as such.
"""

from __future__ import annotations

import struct
from typing import Any

import pytest

from hunter_exchanges.pumpswap.buy_event import (
    BUY_EVENT_DISCRIMINATOR,
    LAYOUT_TRAILING_U64,
    BuyEventError,
    buy_events_from_transaction,
    decode_buy_event,
)
from hunter_exchanges.pumpswap.decode import PUMPSWAP_PROGRAM_ID
from hunter_exchanges.pumpswap.sell_event import SELL_EVENT_DISCRIMINATOR

from .t1a_chain import (
    AMM_BUY_EXACT_QUOTE_IN_IX,
    AMM_BUY_IX,
    account_keys,
    inner_event_payloads,
    swap_instruction_accounts,
    token_delta,
    tx_fixture,
)

_DEFAULT_PUBKEY = "1" * 32

# (fixture, ix_name, tx version)
_REAL = [
    ("t1a_rpc_amm_buy_5SmrD75SgxDd_raw.json", "buy", 0),
    ("t1a_rpc_amm_buy_2EjiTbbdkX2L_raw.json", "buy", 0),
    ("t1a_rpc_amm_buy_exact_3YxgSPJioUJp_raw.json", "buy_exact_quote_in", "legacy"),
    ("t1a_rpc_amm_buy_exact_5tKuWqTWBw8y_raw.json", "buy_exact_quote_in", 0),
    ("t1a_rpc_amm_buy_nocreator_4jyiFoCoVoWt_raw.json", "buy", 0),
    ("t1a_rpc_amm_buy_routed_2HzxLVTqSFWq_raw.json", "buy_exact_quote_in", 0),
    ("t1a_rpc_v1_amm_buy_exact_holder_rewards_4JMsAJNT9otk_raw.json", "buy_exact_quote_in", 1),
]


def _tx(name: str) -> dict[str, Any]:
    return tx_fixture("pumpswap", name)


def _body(name: str) -> bytes:
    (body,) = inner_event_payloads(_tx(name), PUMPSWAP_PROGRAM_ID, BUY_EVENT_DISCRIMINATOR)
    return body


@pytest.mark.parametrize(("name", "ix_name", "version"), _REAL)
def test_a_real_post_upgrade_buy_decodes_and_agrees_with_the_chain(
    name: str, ix_name: str, version: Any
) -> None:
    tx = _tx(name)
    assert tx["version"] == version
    (event,) = buy_events_from_transaction(tx)
    assert event.layout == LAYOUT_TRAILING_U64
    assert event.ix_name == ix_name
    assert event.timestamp == tx["blockTime"]
    # pool / user = accounts 0 / 1 of the program's own swap instruction (also when routed)
    accounts = swap_instruction_accounts(
        tx, PUMPSWAP_PROGRAM_ID, (AMM_BUY_IX, AMM_BUY_EXACT_QUOTE_IN_IX)
    )
    assert (event.pool, event.user) == (accounts[0], accounts[1])
    assert (event.user_base_token_account, event.user_quote_token_account) == (
        accounts[5],
        accounts[6],
    )
    # the balances the chain moved: base out of the pool vault into the user's account, and the
    # quote the pool received (quote + LP fee; the other fees leave to other accounts)
    assert token_delta(tx, accounts[5]) == event.base_amount_out
    assert token_delta(tx, accounts[7]) == -event.base_amount_out
    assert token_delta(tx, accounts[8]) == event.quote_amount_in_with_lp_fee
    # the unnamed tail is the last 8 bytes of the body, read as a u64: a real 0 is a reading
    assert event.trailing_u64 == int.from_bytes(_body(name)[-8:], "little")


@pytest.mark.parametrize(("name", "_ix", "_version"), _REAL)
def test_the_money_of_every_real_buy_conserves_to_the_lamport(
    name: str, _ix: str, _version: Any
) -> None:
    (event,) = buy_events_from_transaction(_tx(name))
    assert event.net_quote_in == event.quote_amount_in_with_lp_fee - event.lp_fee
    assert event.fee_total == (
        event.lp_fee + event.protocol_fee + event.coin_creator_fee + event.cashback
    )
    assert event.total_quote_paid == event.net_quote_in + event.fee_total
    # holder_rewards is a split of a fee, not one more deduction (reported, never summed)
    assert event.money_conserves


def test_buy_reports_quote_in_as_net_and_user_quote_in_as_the_total_paid() -> None:
    (event,) = buy_events_from_transaction(_tx("t1a_rpc_amm_buy_5SmrD75SgxDd_raw.json"))
    assert event.base_amount_out == 52_542_044_672
    assert (event.lp_fee_basis_points, event.lp_fee) == (20, 76_775)
    assert (event.protocol_fee_basis_points, event.protocol_fee) == (5, 19_194)
    assert (event.coin_creator_fee_basis_points, event.coin_creator_fee) == (95, 364_677)
    assert event.quote_amount_in == event.net_quote_in == 38_387_041
    assert event.user_quote_amount_in == event.total_quote_paid == 38_847_687
    assert event.buyback_fee == 9_597  # a split of the protocol fee, not an extra cost


def test_buy_exact_quote_in_event_swaps_the_meaning_of_two_fields_and_the_decoder_says_so() -> None:
    """On ``buy_exact_quote_in`` the program writes the TOTAL the user pays into ``quote_amount_in``
    and the net quote into ``user_quote_amount_in`` — the opposite of ``buy`` (4 of 4 real fixtures,
    each confirmed by the pool-vault delta). Normalisation must not trust the field names."""
    (event,) = buy_events_from_transaction(_tx("t1a_rpc_amm_buy_exact_5tKuWqTWBw8y_raw.json"))
    assert event.ix_name == "buy_exact_quote_in"
    assert event.quote_amount_in == 758_044 == event.total_quote_paid
    assert event.user_quote_amount_in == 751_281 == event.net_quote_in
    assert event.quote_amount_in_with_lp_fee == 752_784
    assert event.money_conserves


def test_a_pool_without_coin_creator_pays_no_creator_fee() -> None:
    (event,) = buy_events_from_transaction(_tx("t1a_rpc_amm_buy_nocreator_4jyiFoCoVoWt_raw.json"))
    assert event.coin_creator == _DEFAULT_PUBKEY
    assert event.coin_creator_fee == 0
    assert event.total_quote_paid == event.user_quote_amount_in == 1_940_005_196


def test_holder_rewards_are_reported_and_never_added_to_what_the_user_paid() -> None:
    (event,) = buy_events_from_transaction(
        _tx("t1a_rpc_v1_amm_buy_exact_holder_rewards_4JMsAJNT9otk_raw.json")
    )
    assert event.holder_rewards == 5_401_786
    # on ``buy_exact_quote_in`` the total the user paid is the event's own ``quote_amount_in``
    assert event.total_quote_paid == event.quote_amount_in
    assert event.total_quote_paid != event.quote_amount_in + event.holder_rewards
    assert event.money_conserves


def test_pool_reserves_in_the_event_are_those_BEFORE_the_trade() -> None:
    """Two consecutive buys of one pool (same slot, one after the other): the second event's
    reserves are the first's minus what it took out / plus what it put in. Reserves read as
    post-trade would break this chain; it holds to the unit."""
    (first,) = buy_events_from_transaction(_tx("t1a_rpc_amm_buy_5SmrD75SgxDd_raw.json"))
    (second,) = buy_events_from_transaction(_tx("t1a_rpc_amm_buy_2EjiTbbdkX2L_raw.json"))
    assert first.pool == second.pool
    assert second.pool_base_token_reserves == first.pool_base_token_reserves - first.base_amount_out
    assert (
        second.pool_quote_token_reserves
        == first.pool_quote_token_reserves + first.quote_amount_in_with_lp_fee
    )


def test_decode_accepts_the_body_with_or_without_the_event_cpi_tag() -> None:
    body = _body("t1a_rpc_amm_buy_5SmrD75SgxDd_raw.json")
    tagged = bytes.fromhex("e445a52e51cb9a1d") + body
    assert decode_buy_event(tagged) == decode_buy_event(body)


# -- refusals: a named error, never a silent drop and never a guessed field --------------------


def test_every_truncation_of_a_real_body_is_refused_with_the_named_error() -> None:
    body = _body("t1a_rpc_amm_buy_exact_5tKuWqTWBw8y_raw.json")
    for cut in range(len(body)):
        with pytest.raises(BuyEventError):
            decode_buy_event(body[:cut])


def test_another_event_discriminator_is_refused() -> None:
    body = _body("t1a_rpc_amm_buy_5SmrD75SgxDd_raw.json")
    with pytest.raises(BuyEventError, match="discriminator"):
        decode_buy_event(SELL_EVENT_DISCRIMINATOR + body[8:])
    with pytest.raises(BuyEventError, match="discriminator"):
        decode_buy_event(b"")


@pytest.mark.parametrize("extra", [1, 8, 16, 41])
def test_a_longer_unknown_tail_is_refused(extra: int) -> None:
    """SYNTHETIC: a real body with ``extra`` zero bytes appended. Only the 49-byte tail seen on
    chain after 2026-10-02 (41 declared by the IDL + one unnamed u64) is a layout."""
    body = _body("t1a_rpc_amm_buy_5SmrD75SgxDd_raw.json")
    with pytest.raises(BuyEventError, match=f"{49 + extra} trailing bytes"):
        decode_buy_event(body + b"\x00" * extra)


@pytest.mark.parametrize("cut", [8, 41, 49])
def test_a_shorter_tail_is_refused_as_an_unknown_layout(cut: int) -> None:
    """SYNTHETIC: a real body with the last ``cut`` bytes removed — the IDL's 41 without the
    unnamed u64, and no tail at all (the pre-upgrade layout, never seen by us and so not trusted)."""
    body = _body("t1a_rpc_amm_buy_5SmrD75SgxDd_raw.json")
    with pytest.raises(BuyEventError, match="trailing bytes"):
        decode_buy_event(body[:-cut])


def test_a_boolean_that_is_not_zero_or_one_is_refused() -> None:
    body = bytearray(_body("t1a_rpc_amm_buy_5SmrD75SgxDd_raw.json"))
    boost_offset = len(body) - 8 - 8 - 8 - 8 - 1  # can_boost: before base_supply, hr_bps, hr, tail
    assert body[boost_offset] == 1
    body[boost_offset] = 2
    with pytest.raises(BuyEventError, match="boolean"):
        decode_buy_event(bytes(body))


def test_an_ix_name_that_is_not_utf8_is_refused() -> None:
    body = bytearray(_body("t1a_rpc_amm_buy_5SmrD75SgxDd_raw.json"))
    name_offset = body.index(struct.pack("<I", 3) + b"buy") + 4
    body[name_offset] = 0xFF
    with pytest.raises(BuyEventError, match="ix_name"):
        decode_buy_event(bytes(body))


def test_a_hostile_ix_name_length_cannot_run_past_the_buffer() -> None:
    body = bytearray(_body("t1a_rpc_amm_buy_5SmrD75SgxDd_raw.json"))
    at = body.index(struct.pack("<I", 3) + b"buy")
    body[at : at + 4] = struct.pack("<I", 0xFFFFFFFF)
    with pytest.raises(BuyEventError, match="truncated"):
        decode_buy_event(bytes(body))


# -- from a getTransaction result ---------------------------------------------------------------


def test_a_failed_transaction_yields_no_buy_event() -> None:
    tx = _tx("t1a_rpc_amm_buy_5SmrD75SgxDd_raw.json")
    tx["meta"]["err"] = {"InstructionError": [2, {"Custom": 6004}]}
    assert buy_events_from_transaction(tx) == ()


def test_a_buy_looking_payload_of_another_program_is_not_ours() -> None:
    tx = _tx("t1a_rpc_amm_buy_5SmrD75SgxDd_raw.json")
    keys = account_keys(tx)
    other = keys[0]  # the fee payer: some account that is not the PumpSwap program
    assert other != PUMPSWAP_PROGRAM_ID
    for group in tx["meta"]["innerInstructions"]:
        for ix in group["instructions"]:
            if keys[ix["programIdIndex"]] == PUMPSWAP_PROGRAM_ID:
                ix["programIdIndex"] = keys.index(other)
    assert buy_events_from_transaction(tx) == ()


def test_a_sell_transaction_yields_no_buy_event() -> None:
    sell = tx_fixture("pumpswap", "t1a_rpc_v1_amm_sell_5Ls5TV77aYS3_raw.json")
    assert buy_events_from_transaction(sell) == ()


def test_the_unnamed_tail_values_of_the_real_fixtures_are_pinned() -> None:
    """Zeroing the field (or reading it from the wrong place) must not pass unnoticed."""
    tails = {name: buy_events_from_transaction(_tx(name))[0].trailing_u64 for name, _, _ in _REAL}
    assert tails["t1a_rpc_amm_buy_exact_3YxgSPJioUJp_raw.json"] == 169_685
    assert len({v for v in tails.values() if v}) >= 3  # several distinct non-zero values


def test_cashback_counts_in_the_buy_fee_total_and_an_unmatched_pair_fails_conservation() -> None:
    """SYNTHETIC: a real ``buy`` body with ``cashback`` patched to 5. The event's own quote fields do not
    move, so ``total_quote_paid`` (which now includes the cashback) no longer closes against them:
    the event reports itself as not conserving instead of becoming a fill."""
    body = bytearray(_body("t1a_rpc_amm_buy_5SmrD75SgxDd_raw.json"))
    name_end = body.index(struct.pack("<I", 3) + b"buy") + 4 + 3
    assert struct.unpack_from("<QQ", body, name_end) == (0, 0)  # cashback bps, cashback
    body[name_end + 8 : name_end + 16] = struct.pack("<Q", 5)
    event = decode_buy_event(bytes(body))
    assert event.cashback == 5
    assert event.fee_total == event.lp_fee + event.protocol_fee + event.coin_creator_fee + 5
    assert not event.money_conserves
