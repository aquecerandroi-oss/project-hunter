"""The builder against T4.8's recorded mainnet fixtures: a buy built for a budget
verifies against its own intent, a tampered byte is refused, and the fill decoder
reads the ``TradeEvent`` **and** ``meta.fee`` from a real ``getTransaction``."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from hunter_exchanges.pumpfun.decode import BondingCurveAccount
from hunter_exchanges.pumpfun.global_state import decode_global_account
from hunter_exchanges.pumpfun.quote import (
    BONDING_CURVE_FEE_TIER_2026_05_20,
    BuyQuote,
    FeeBps,
    SellQuote,
)
from hunter_exchanges.pumpfun.trade_event import LAYOUT_HOLDER_REWARDS, LAYOUT_PRE_HOLDER_REWARDS
from hunter_exchanges.pumpfun.tx import bonding_curve_v2_address
from hunter_exchanges.pumpfun.verify import UnverifiedTransaction
from hunter_meme_executor.build import build_buy, build_sell, decode_fills, fee_bps
from hunter_meme_executor.chain import CurveRead

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[3] / "packages/exchange-adapters/tests/fixtures/pumpfun"
USER = "AsRQHoHxfBYqvxJZxK9RtJUnRZcCwUoh9KNpVxH6Jhnd"
TOKEN_2022 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
BLOCKHASH = "BQ8v5pyUzayNkgPghSBd36pVgG14SGLExT5kwWkmYZWJ"


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _global_account() -> Any:
    g = _fixture("rpc_global_account_raw.json")["result"]["value"]
    return decode_global_account(g["data"][0], owner=g["owner"])


def _curve_read() -> CurveRead:
    (fill,) = decode_fills(_fixture("rpc_tx_buy_raw.json")["result"])
    e = fill.event
    account = BondingCurveAccount(
        virtual_token_reserves=e.virtual_token_reserves + e.token_amount,
        virtual_sol_reserves=e.virtual_sol_reserves - e.sol_amount,
        real_token_reserves=e.real_token_reserves + e.token_amount,
        real_sol_reserves=1,
        token_total_supply=1_000_000_000_000_000,
        complete=False,
        creator=e.creator,
        is_mayhem_mode=False,
        is_cashback_coin=True,
        quote_mint="11111111111111111111111111111111",
    )
    return CurveRead(e.mint, account, TOKEN_2022, 446_378_553, datetime(2026, 9, 12, tzinfo=UTC))


def test_decode_fills_reads_the_event_the_network_fee_and_the_payers_real_delta() -> None:
    """The ledger's ``sol_spent`` is what the wallet **lost** (``pre − post`` of the fee
    payer), not the event arithmetic: this recorded buy went through the site's own
    router, which took 13 430 340 lamports on top of the curve's fees — a path this
    executor never builds, but exactly the kind of cost an event-only sum would hide."""
    (fill,) = decode_fills(_fixture("rpc_tx_buy_raw.json")["result"])
    assert fill.event.is_buy
    assert fill.network_fee_lamports > 0
    assert fill.event_buy_total_lamports == fill.event.buy_total_cost + fill.network_fee_lamports
    assert fill.payer_delta_lamports is not None and fill.payer_delta_lamports < 0
    assert fill.buy_total_lamports == -fill.payer_delta_lamports
    assert fill.buy_total_lamports - fill.event_buy_total_lamports == 13_430_340
    payload = fill.as_json()
    assert payload["token_amount"] == fill.event.token_amount
    assert payload["signature"]
    assert payload["buy_total_lamports"] == 1_003_518_840
    assert payload["event_buy_total_lamports"] == 990_088_500
    assert payload["unexplained_lamports"] == 13_430_340, "the router's cut, named"
    assert payload["holder_rewards"] == 0 and payload["holder_rewards_basis_points"] == 0
    assert payload["event_layout"] == LAYOUT_PRE_HOLDER_REWARDS, "the fixture predates the field"


def test_a_real_sell_of_2026_09_12_reconciles_the_event_with_the_wallet_delta() -> None:
    """T4.8b: the post-upgrade layout decodes with ``holder_rewards`` as a field; the
    seller's real delta is the event's net minus the network fee minus the bot's own
    cut (1 % of the net + a tip transfer), which is exactly the ``unexplained`` gap —
    a cost of *that* bot's program, not of the pump program."""
    (fill,) = decode_fills(_fixture("t48b_rpc_tx_sell_raw.json")["result"])
    e = fill.event
    assert not e.is_buy and e.layout == LAYOUT_HOLDER_REWARDS
    assert e.holder_rewards == 0 and e.holder_rewards_basis_points == 0
    assert fill.network_fee_lamports == 281_762
    assert fill.event_sell_net_lamports == 1_221_920_857 - 281_762
    assert fill.payer_delta_lamports == fill.sell_net_lamports == 1_207_696_649
    assert fill.unexplained_lamports == 12_219_208 + 1_723_238
    payload = fill.as_json()
    assert payload["sell_net_lamports"] == 1_207_696_649
    assert payload["unexplained_lamports"] == 13_942_446
    assert payload["event_layout"] == LAYOUT_HOLDER_REWARDS
    assert fill.block_time == datetime(2026, 9, 12, 17, 52, 42, tzinfo=UTC)


def test_a_buy_built_on_the_upgraded_program_carries_the_derived_bonding_curve_v2() -> None:
    """The executor's own buy on the recorded coin: 18 accounts, slot 16 the PDA
    ``["bonding-curve-v2", mint]`` (read-only), slot 17 a buyback recipient (writable);
    the bound verifier accepts its own bytes — the message the mainnet simulation ran."""
    (fill,) = decode_fills(_fixture("t48b_rpc_tx_sell_raw.json")["result"])
    e = fill.event
    account = BondingCurveAccount(
        virtual_token_reserves=e.virtual_token_reserves,
        virtual_sol_reserves=e.virtual_sol_reserves,
        real_token_reserves=e.real_token_reserves,
        real_sol_reserves=e.real_sol_reserves,
        token_total_supply=1_000_000_000_000_000,
        complete=False,
        creator=e.creator,
        is_mayhem_mode=e.mayhem_mode,
        is_cashback_coin=False,
        quote_mint="11111111111111111111111111111111",
    )
    read = CurveRead(e.mint, account, TOKEN_2022, 446_490_901, datetime(2026, 9, 12, tzinfo=UTC))
    g = _fixture("t48b_rpc_global_account_raw.json")["result"]["value"]
    global_account = decode_global_account(g["data"][0], owner=g["owner"])
    built = build_buy(
        read,
        global_account,
        user=e.user,
        budget_sol=Decimal("0.005"),
        max_slippage_bps=100,
        blockhash=BLOCKHASH,
        last_valid_block_height=150,
        compute_unit_limit=400_000,
        compute_unit_price_micro_lamports=10_000,
        creates_ata=False,
    )
    verified = built.verify(built.message)
    trade = cast(Any, verified).trade
    assert len(trade.accounts) == 18
    assert trade.accounts[16].pubkey == bonding_curve_v2_address(e.mint)
    assert not trade.accounts[16].is_writable and trade.accounts[17].is_writable
    assert trade.accounts[17].pubkey in global_account.buyback_fee_recipients
    assert trade.accounts[1].pubkey == global_account.reserved_fee_recipient, "Mayhem coin"


def test_decode_fills_without_balances_falls_back_to_the_event_arithmetic() -> None:
    raw = _fixture("rpc_tx_buy_raw.json")["result"]
    meta = {k: v for k, v in raw["meta"].items() if k not in ("preBalances", "postBalances")}
    (fill,) = decode_fills({**raw, "meta": meta})
    assert fill.payer_delta_lamports is None
    assert fill.buy_total_lamports == fill.event_buy_total_lamports == 990_088_500


def test_a_sell_fill_nets_what_the_wallet_actually_received() -> None:
    (fill,) = decode_fills(_fixture("rpc_tx_probe_raw.json")["result"])
    assert not fill.event.is_buy
    assert fill.payer_delta_lamports == 715_497_919
    assert fill.sell_net_lamports == 715_497_919
    assert fill.event_sell_net_lamports == 715_558_030, "the bot's tip is not in the event"


def test_a_failed_transaction_yields_no_fill() -> None:
    raw = _fixture("rpc_tx_buy_raw.json")["result"]
    raw = {**raw, "meta": {**raw["meta"], "err": {"InstructionError": [2, {"Custom": 6002}]}}}
    assert decode_fills(raw) == []


def test_a_buy_built_for_a_budget_verifies_against_its_own_intent() -> None:
    built = build_buy(
        _curve_read(),
        _global_account(),
        user=USER,
        budget_sol=Decimal("0.01"),
        max_slippage_bps=100,
        blockhash=BLOCKHASH,
        last_valid_block_height=150,
        compute_unit_limit=400_000,
        compute_unit_price_micro_lamports=10_000,
        creates_ata=True,
    )
    assert isinstance(built.quote, BuyQuote)
    assert built.quote.token_amount > 0
    assert built.intent.sol_limit >= built.quote.total_cost
    assert built.quote.total_cost <= 10_000_000
    assert built.verify(built.message) is not None
    intent = built.intent_json()
    assert intent["side"] == "buy" and intent["creates_ata"] is True


def test_a_tampered_message_is_refused_by_the_bound_verifier() -> None:
    built = build_buy(
        _curve_read(),
        _global_account(),
        user=USER,
        budget_sol=Decimal("0.01"),
        max_slippage_bps=100,
        blockhash=BLOCKHASH,
        last_valid_block_height=150,
        compute_unit_limit=400_000,
        compute_unit_price_micro_lamports=10_000,
        creates_ata=False,
    )
    tampered = bytearray(built.message)
    tampered[-9] ^= 0x01
    with pytest.raises(UnverifiedTransaction):
        built.verify(bytes(tampered))


def test_fee_bps_floors_the_creator_share_at_the_tier_the_program_charges() -> None:
    """T4.8b: ``Global.creator_fee_basis_points`` reads 5 on both recorded ``Global``s while
    every real fill (morning and afternoon) charged 30 — quoting with 5 made the executor's
    ``max_sol_cost`` headroom 0.75 % instead of 1 % and the budget a ceiling by 0.25 % less.
    The floor is the proven tier; a higher on-chain value is kept."""
    fees = fee_bps(_global_account())
    assert fees == FeeBps(protocol=95, creator=30) == BONDING_CURVE_FEE_TIER_2026_05_20
    for name in ("rpc_tx_buy_raw.json", "rpc_tx_probe_raw.json", "t48b_rpc_tx_sell_raw.json"):
        (fill,) = decode_fills(_fixture(name)["result"])
        e = fill.event
        charged = FeeBps(
            e.fee_basis_points, e.cashback_fee_basis_points or e.creator_fee_basis_points
        )
        assert charged == fees, name
    raised = replace(_global_account(), creator_fee_basis_points=40, fee_basis_points=100)
    assert fee_bps(raised) == FeeBps(protocol=100, creator=40)


def test_a_curve_quoted_in_usdc_is_refused_by_name_before_anything_is_built() -> None:
    """T4.8b: ``DU66…pump`` is quoted in USDC (``quote_mint = EPjF…``); the legacy
    ``sell`` answered our simulation with ``UnsupportedQuoteMint`` (6063). The builder
    refuses such a curve by name so the executor records ``build_failed:ValueError``
    (``unsupported_quote``) instead of quoting USDC reserves as if they were lamports."""
    read = _curve_read()
    usdc = CurveRead(
        read.mint,
        replace(read.account, quote_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"),
        read.token_program,
        read.slot,
        read.observed_at,
    )
    kwargs: dict[str, Any] = dict(
        user=USER,
        max_slippage_bps=100,
        blockhash=BLOCKHASH,
        last_valid_block_height=150,
        compute_unit_limit=400_000,
        compute_unit_price_micro_lamports=10_000,
    )
    with pytest.raises(ValueError, match="unsupported_quote:EPjF"):
        build_buy(usdc, _global_account(), budget_sol=Decimal("0.01"), creates_ata=False, **kwargs)
    with pytest.raises(ValueError, match="unsupported_quote:EPjF"):
        build_sell(usdc, _global_account(), token_amount=1_000_000, **kwargs)


def test_a_sell_carries_min_sol_output_from_the_quote() -> None:
    built = build_sell(
        _curve_read(),
        _global_account(),
        user=USER,
        token_amount=1_000_000_000,
        max_slippage_bps=100,
        blockhash=BLOCKHASH,
        last_valid_block_height=150,
        compute_unit_limit=400_000,
        compute_unit_price_micro_lamports=10_000,
    )
    assert built.intent.side == "sell"
    assert isinstance(built.quote, SellQuote)
    assert built.intent.sol_limit == built.quote.min_sol_output
    assert built.verify(built.message) is not None
