"""The builder against T4.8's recorded mainnet fixtures: a buy built for a budget
verifies against its own intent, a tampered byte is refused, and the fill decoder
reads the ``TradeEvent`` **and** ``meta.fee`` from a real ``getTransaction``."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from hunter_exchanges.pumpfun.decode import BondingCurveAccount
from hunter_exchanges.pumpfun.global_state import decode_global_account
from hunter_exchanges.pumpfun.quote import BuyQuote, SellQuote
from hunter_exchanges.pumpfun.verify import UnverifiedTransaction
from hunter_meme_executor.build import build_buy, build_sell, decode_fills
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
    assert payload["holder_rewards"] is None, "the recorded fixture predates the field"


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
