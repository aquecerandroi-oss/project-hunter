"""T4.8 item 6 — the end-to-end proof, outside CI (``live_devnet`` marker).

Which of the two options the brief allowed was possible, and why:

- The pump program **does** exist on devnet (``6EF8…`` and ``pfee…`` are executable
  there; ``Global`` is initialised; ``create_v2``/``buy_exact_quote_in_v2`` land
  every few minutes — checked 2026-09-12 08:01–08:04 UTC). A devnet *send* needs
  devnet SOL, and the public faucet answered ``requestAirdrop`` with
  ``-32603 Internal error`` for a fresh throwaway key at 08:04 UTC. So no
  transaction was sent anywhere by this task.
- What ran, and is re-run by this test on demand: **``simulateTransaction`` on
  mainnet with ``sigVerify=false``** — our own ``buy``/``sell`` bytes, unsigned,
  executed by the cluster against real curve state, with the logs proving the
  program reached ``Instruction: Buy``/``Sell`` and emitted the event path.
  Recorded once in ``tests/fixtures/pumpfun/simulation_proof_mainnet_raw.json``
  (asserted offline by ``test_pumpfun_quote.py``).

Run: ``HUNTER_LIVE_DEVNET=1 timeout 290 uv run pytest -m live_devnet packages/exchange-adapters/tests/live/test_live_pumpfun_simulation.py -q``
Optional devnet send: additionally set ``MEME_DEVNET_RPC_URL`` and export a
**devnet-only** throwaway key in ``SOLANA_WALLET_SECRET_KEY`` funded by the
faucet; the test then drives the real submitter on devnet. Never mainnet: the
RPC client is built with ``allow_send`` only for the devnet URL.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from hunter_core.execution.meme.journal import InMemoryOrderJournal, SubmitState
from hunter_core.execution.meme.signer import ENV_SECRET_KEY, MemeSigner
from hunter_core.execution.meme.submit import ApprovedSubmission, MemeSubmitter, SubmitPolicy
from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID, decode_bonding_curve_account
from hunter_exchanges.pumpfun.global_state import GLOBAL_ACCOUNT_ADDRESS, decode_global_account
from hunter_exchanges.pumpfun.quote import (
    BONDING_CURVE_FEE_TIER_2026_05_20,
    CurveReserves,
    quote_buy,
)
from hunter_exchanges.pumpfun.solana_codec import serialize_message, serialize_transaction
from hunter_exchanges.pumpfun.trade_event import trade_events_from_transaction
from hunter_exchanges.pumpfun.tx import (
    TradeIntent,
    bonding_curve_address,
    build_buy_instruction,
    build_trade_message,
    create_ata_idempotent,
)
from hunter_exchanges.pumpfun.tx_rpc import MAINNET_PUBLIC_RPC_URL, SolanaTxRpcClient
from hunter_exchanges.pumpfun.verify import ExecutionCaps, verify_trade_message

FIXTURES = Path(__file__).parents[1] / "fixtures/pumpfun"
pytestmark = pytest.mark.live_devnet

MINT = "5ejAEbzxiZuwUNgZcoryoAY8gA5oCAVJZx5AyDnApump"
FUNDED_UNSIGNED_PAYER = (
    "AsRQHoHxfBYqvxJZxK9RtJUnRZcCwUoh9KNpVxH6Jhnd"  # holds the ATA; simulation only
)


def _skip_unless_enabled() -> None:
    if os.environ.get("HUNTER_LIVE_DEVNET") != "1":
        pytest.skip("set HUNTER_LIVE_DEVNET=1 to run the live simulation proof")


def test_mainnet_simulation_of_our_buy_never_sent() -> None:
    _skip_unless_enabled()
    rpc = SolanaTxRpcClient(MAINNET_PUBLIC_RPC_URL)  # allow_send=False: sending is impossible
    global_snapshot = rpc.get_account(GLOBAL_ACCOUNT_ADDRESS)
    curve_snapshot = rpc.get_account(bonding_curve_address(MINT))
    assert global_snapshot is not None and curve_snapshot is not None
    global_account = decode_global_account(global_snapshot.data_base64, owner=global_snapshot.owner)
    curve = decode_bonding_curve_account(curve_snapshot.data_base64, owner=curve_snapshot.owner)
    if curve.complete:
        pytest.skip("the fixture coin graduated; pick another mint")
    reserves = CurveReserves(
        curve.virtual_sol_reserves,
        curve.virtual_token_reserves,
        curve.real_sol_reserves,
        curve.real_token_reserves,
    )
    quote = quote_buy(reserves, 1_000_000, BONDING_CURVE_FEE_TIER_2026_05_20, max_slippage_bps=100)
    intent = TradeIntent(
        "buy",
        MINT,
        FUNDED_UNSIGNED_PAYER,
        curve.creator,
        "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
        1_000_000,
        quote.max_sol_cost,
        global_account.fee_recipient,
        global_account.buyback_fee_recipients[0],
        curve.is_mayhem_mode,
    )
    message = build_trade_message(
        build_buy_instruction(intent, global_account),
        payer=intent.user,
        recent_blockhash="11111111111111111111111111111111",
        compute_unit_limit=400_000,
        compute_unit_price_micro_lamports=10_000,
    )
    raw = serialize_message(message)
    simulation = rpc.simulate_transaction(
        serialize_transaction([b"\0" * 64], raw), sig_verify=False, replace_blockhash=True
    )
    assert simulation.ok, simulation.logs
    assert any("Instruction: Buy" in line for line in simulation.logs)
    assert not rpc.allow_send


def test_devnet_send_when_a_funded_throwaway_key_is_provided() -> None:
    _skip_unless_enabled()
    devnet_url = os.environ.get("MEME_DEVNET_RPC_URL", "")
    if not devnet_url or ENV_SECRET_KEY not in os.environ:
        pytest.skip("devnet send needs MEME_DEVNET_RPC_URL and a devnet-only throwaway key")
    assert "mainnet" not in devnet_url, "never mainnet"
    signer = MemeSigner.from_environment(os.environ)  # scrubs the variable
    rpc = SolanaTxRpcClient(devnet_url, allow_send=True)
    global_snapshot = rpc.get_account(GLOBAL_ACCOUNT_ADDRESS)
    assert global_snapshot is not None
    global_account = decode_global_account(global_snapshot.data_base64, owner=global_snapshot.owner)
    mint = os.environ.get("MEME_DEVNET_MINT", "")
    if not mint:
        pytest.skip("MEME_DEVNET_MINT: a live devnet bonding curve to trade on")
    curve_snapshot = rpc.get_account(bonding_curve_address(mint))
    assert curve_snapshot is not None
    curve = decode_bonding_curve_account(curve_snapshot.data_base64, owner=curve_snapshot.owner)
    mint_account = rpc.get_account(mint)
    assert mint_account is not None
    reserves = CurveReserves(
        curve.virtual_sol_reserves,
        curve.virtual_token_reserves,
        curve.real_sol_reserves,
        curve.real_token_reserves,
    )
    quote = quote_buy(reserves, 1_000_000, BONDING_CURVE_FEE_TIER_2026_05_20, max_slippage_bps=300)
    intent = TradeIntent(
        "buy",
        mint,
        signer.pubkey,
        curve.creator,
        mint_account.owner,
        1_000_000,
        quote.max_sol_cost,
        global_account.fee_recipient,
        global_account.buyback_fee_recipients[0],
        curve.is_mayhem_mode,
    )
    blockhash, last_valid = rpc.get_latest_blockhash()
    message = build_trade_message(
        build_buy_instruction(intent, global_account),
        payer=signer.pubkey,
        recent_blockhash=blockhash,
        compute_unit_limit=400_000,
        compute_unit_price_micro_lamports=10_000,
        create_user_ata=create_ata_idempotent(
            payer=signer.pubkey, owner=signer.pubkey, mint=mint, token_program=mint_account.owner
        ),
    )
    caps = ExecutionCaps(
        max_compute_unit_limit=400_000, max_compute_unit_price_micro_lamports=10_000
    )
    submitter = MemeSubmitter(
        rpc=rpc,
        signer=signer,
        journal=InMemoryOrderJournal(),
        verify=lambda raw: verify_trade_message(
            raw, intent, global_account, caps, expected_blockhash=blockhash
        ),
        decode_fill=lambda tx: trade_events_from_transaction(tx, program_id=PUMP_PROGRAM_ID),
        policy=SubmitPolicy(allow_send=True, cluster="devnet", confirm_timeout_s=60.0),
        now=lambda: datetime.now(UTC),
    )
    result = submitter.submit(
        ApprovedSubmission(
            "devnet-proof",
            datetime.now(UTC) + timedelta(seconds=30),
            serialize_message(message),
            last_valid,
        )
    )
    record: dict[str, Any] = {
        "state": result.state,
        "reason": result.reason,
        "signature": result.signature,
    }
    (FIXTURES / "devnet_send_proof_raw.json").write_text(
        json.dumps(record, default=str), encoding="utf-8"
    )
    assert result.state in (SubmitState.CONFIRMED, SubmitState.SUBMITTED_UNCONFIRMED), record
