"""T4.8f: ``build_pumpswap_sell`` carries the three remaining accounts the PumpSwap program
demands since 2026-10-02 (``6062 InvalidPoolV2`` without them) and refuses by name when the
GlobalConfig it read has no buyback recipient to name."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from hunter_exchanges.pumpfun.solana_codec import (
    TOKEN_PROGRAM_ID,
    associated_token_address,
    deserialize_message,
)
from hunter_exchanges.pumpswap.decode import (
    WSOL_MINT,
    decode_global_config,
    decode_pool_account,
)
from hunter_exchanges.pumpswap.pdas import pool_v2_address
from hunter_meme_executor.chain import PoolRead
from hunter_meme_executor.pumpswap_build import build_pumpswap_sell

pytestmark = pytest.mark.unit

FIXTURES = (
    Path(__file__).resolve().parents[3] / "packages/exchange-adapters/tests/fixtures/pumpswap"
)
USER = "ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4"
BLOCKHASH = "7Pptc9XnPvGCz2SExsdbLzYAWCXbGmYyewGefDCVU4A6"


def _pool_read() -> PoolRead:
    raw = json.loads((FIXTURES / "t429a_rpc_pools_raw.json").read_text(encoding="utf-8"))
    value = raw["result"]["value"][2]
    return PoolRead(
        address="F5MkE4Yf73TkeSKLv3Mr3yrGJpFg3g7sspaCosVYyxaQ",
        pool=decode_pool_account(value["data"][0], owner=value["owner"]),
        base_token_amount=964_405_811_222_437,
        quote_token_amount=751_101_815,
        slot=447586178,
        observed_at=datetime(2026, 10, 5, tzinfo=UTC),
    )


def _config() -> Any:
    value = json.loads((FIXTURES / "t48f_rpc_global_config_raw.json").read_text())["result"][
        "value"
    ]
    return decode_global_config(value["data"][0], owner=value["owner"])


def _build(config: Any, *, creates: bool = True) -> Any:
    return build_pumpswap_sell(
        _pool_read(),
        config,
        user=USER,
        base_token_program=TOKEN_PROGRAM_ID,
        token_amount=1_000_000_000,
        max_slippage_bps=500,
        blockhash=BLOCKHASH,
        last_valid_block_height=150,
        compute_unit_limit=150_000,
        compute_unit_price_micro_lamports=1_000,
        creates_wsol_ata=creates,
    )


def test_the_built_sell_carries_pool_v2_the_buyback_recipient_and_its_wsol_ata() -> None:
    config = _config()
    built = _build(config)
    assert built.intent.buyback_fee_recipient in config.buyback_fee_recipients
    trade = built.verify(built.message).trade
    assert len(trade.accounts) == 24
    assert trade.accounts[21].pubkey == pool_v2_address(built.intent.pool.base_mint)
    recipient = built.intent.buyback_fee_recipient
    assert trade.accounts[22].pubkey == recipient
    assert trade.accounts[23].pubkey == associated_token_address(
        recipient, WSOL_MINT, token_program=TOKEN_PROGRAM_ID
    )
    assert [a.is_writable for a in trade.accounts[21:]] == [False, False, True]
    assert deserialize_message(built.message).account_keys[0] == USER


def test_without_a_buyback_recipient_the_build_refuses_by_name_instead_of_signing() -> None:
    bare = replace(_config(), buyback_fee_recipients=())
    with pytest.raises(ValueError, match="pumpswap_buyback_recipients_unavailable"):
        _build(bare)


def test_a_pool_quoted_in_another_mint_is_refused_by_name() -> None:
    """The unwrap, the fee ATAs and the quote maths all assume WSOL: a custom-quote pool (real
    direct sells of 2026-10-05 exist) is never built into a sell."""
    read = _pool_read()
    other = replace(
        read, pool=replace(read.pool, quote_mint="CzUx8euxrsw1QFMjLNVdoJzxEyDcYd9Zg2j1WrE3FoYY")
    )
    with pytest.raises(ValueError, match="pumpswap_quote_not_wsol"):
        build_pumpswap_sell(
            other,
            _config(),
            user=USER,
            base_token_program=TOKEN_PROGRAM_ID,
            token_amount=1_000_000_000,
            max_slippage_bps=500,
            blockhash=BLOCKHASH,
            last_valid_block_height=150,
            compute_unit_limit=150_000,
            compute_unit_price_micro_lamports=1_000,
            creates_wsol_ata=True,
        )


def test_the_buyback_recipient_is_picked_per_intent_and_recorded() -> None:
    """T4.8f F5: any of the 8 is valid; always [0] would pile every sell's write on one ATA.
    The pick is made once per intent, injected here so the test is deterministic, and written
    to ``intent_json`` for the audit."""
    config = _config()
    picks: list[str] = []
    for i in range(8):
        built = build_pumpswap_sell(
            _pool_read(),
            config,
            user=USER,
            base_token_program=TOKEN_PROGRAM_ID,
            token_amount=1_000_000_000,
            max_slippage_bps=500,
            blockhash=BLOCKHASH,
            last_valid_block_height=150,
            compute_unit_limit=150_000,
            compute_unit_price_micro_lamports=1_000,
            creates_wsol_ata=True,
            pick_recipient=lambda recipients, i=i: recipients[i],
        )
        assert built.intent.buyback_fee_recipient == config.buyback_fee_recipients[i]
        assert built.intent_json()["buyback_fee_recipient"] == config.buyback_fee_recipients[i]
        assert built.verify(built.message) is not None  # the verifier rebuilds with the same pick
        picks.append(built.intent.buyback_fee_recipient)
    assert picks == list(config.buyback_fee_recipients)


def test_the_default_pick_is_always_one_of_the_global_config_recipients() -> None:
    config = _config()
    seen = {_build(config).intent.buyback_fee_recipient for _ in range(40)}
    assert seen <= set(config.buyback_fee_recipients) and len(seen) > 1, "40 draws of 8 vary"
