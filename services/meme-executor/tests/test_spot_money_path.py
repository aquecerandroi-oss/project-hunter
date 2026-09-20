"""T4.74-4 — ``spot_send.spot_leg`` with fakes only (``spot_fakes.py``): the
one place of the lane that signs. The invariants the design §5.1/§9 name:
``signer.sign`` only after ``verify`` and after the invariant read from
``simulation.accounts``; the kill switch re-read before the signature blocks a
buy, never a sell; the signature is on the row **before** the broadcast;
``pending`` is ``submitted_unconfirmed``, never ``confirmed``; a confirmed buy
whose fill is not visible is not ``confirmed`` with zero; the priority fee is
capped by the caller's number.
"""

from __future__ import annotations

from typing import Any, cast

import pytest

from hunter_core.domain.enums import KillSwitchState
from hunter_exchanges.pumpfun.tx_rpc import SendDisabled
from hunter_meme_executor import spot_send
from hunter_meme_executor.chain import TokenAccountRead

from .spot_fakes import (
    Db,
    FakeChain,
    FakeConfig,
    FakeContext,
    FakeJupiter,
    FakeKill,
    FakeRpc,
    FakeSigner,
    accounts_after,
    buy_rig,
    run_buy,
    simulation,
    tx_meta,
    wire_db,
)
from .spot_tx_fixtures import (
    ATA_RENT,
    ORDER,
    OUT,
    SIGNATURE,
    THRESHOLD,
    TICKET,
    WALLET,
    WIF,
    WIF_ATA,
    WSOL,
    as_swap,
    buy_message,
    quote,
    sell_message,
)

pytestmark = pytest.mark.unit


# ------------------------------------------------------------------------ the buy
async def test_a_buy_verifies_simulates_signs_records_then_sends_and_confirms_from_the_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = buy_rig(monkeypatch)
    result = await run_buy(rig)
    assert result.status == "confirmed" and result.reason is None
    assert result.signature == SIGNATURE
    assert result.filled_atoms == OUT, "the ATA delta, not the quote"
    assert result.sol_delta_lamports == -(TICKET + ATA_RENT + 5_050), "this signature's delta"
    assert result.ata_rent_lamports == ATA_RENT, "the transaction created the token ATA"
    assert result.priority_fee_lamports == 50
    assert rig.log == [
        "simulate",
        "simulated",
        "sign",
        "submitted",
        "send",
        "get_transaction",
        "confirmed",
    ]
    assert rig.ctx.chain.reads == 1, "the wallet is read once, for the simulation's pre-state"
    assert rig.log.index("submitted") < rig.log.index("send"), "the signature is on the row first"
    assert rig.signer.log.count("sign") == 1
    assert rig.ctx.chain.rpc.simulated_accounts == (WALLET, WIF_ATA)
    submitted = dict(rig.db.rows)["submitted"]
    assert submitted["signature"] == SIGNATURE
    assert submitted["last_valid_block_height"] == 250_000_123
    fill = dict(rig.db.rows)["confirmed"]["fill"]
    assert fill["filled_atoms"] == OUT and fill["sol_delta_lamports"] == result.sol_delta_lamports
    assert fill["token_before_atoms"] == 0 and fill["token_after_atoms"] == OUT
    assert fill["source"] == "transaction_meta" and fill["network_fee_lamports"] == 5_000
    swap_call = rig.ctx.treasury_client.swap_calls[0]
    assert swap_call["max_priority_fee_lamports"] == 100_000
    assert swap_call["user_public_key"] == WALLET
    assert rig.ctx.state.last_signature == SIGNATURE


async def test_a_priority_fee_above_the_caller_s_cap_is_refused_before_anything_else(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # limit 100 000 × price 1 500 000 micro-lamports = 150 000 lamports > cap 100 000
    rig = buy_rig(monkeypatch, message=buy_message(cu_price=1_500_000))
    result = await run_buy(rig)
    assert result.status == "refused" and result.reason == "priority_fee_above_cap:150000"
    assert rig.log == ["refused"], "no simulation, no signature, no send"
    assert rig.ctx.kill.refreshes == 0


async def test_a_verifier_refusal_is_named_and_nothing_is_signed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = buy_rig(monkeypatch, message=buy_message(in_amount=TICKET + 1))
    result = await run_buy(rig)
    assert result.status == "refused"
    assert result.reason == f"system_transfer_amount_mismatch:{TICKET + 1}!={TICKET}"
    assert "sign" not in rig.log and "send" not in rig.log


async def test_a_quote_for_another_pair_or_amount_is_refused_before_the_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = buy_rig(monkeypatch)
    rig.ctx.treasury_client.quote_reply = quote(
        input_mint=WSOL, output_mint=WIF, amount=TICKET * 10, out=OUT * 10
    )
    result = await run_buy(rig)
    assert result.status == "refused" and result.reason == "quote_mismatch:in_amount"
    assert rig.ctx.treasury_client.swap_calls == []


@pytest.mark.parametrize(
    "accounts,reason",
    [
        (accounts_after(500_000_000 - TICKET - 60_000, THRESHOLD - 1), "simulation_token_short"),
        (accounts_after(500_000_000 - TICKET - 30_000_000, OUT), "simulation_sol_overspent"),
        (None, "simulation_accounts_unreadable"),
        (({"lamports": 1}, None), "simulation_accounts_unreadable"),
    ],
)
async def test_the_invariant_reads_the_simulated_post_state_and_refuses_by_name(
    monkeypatch: pytest.MonkeyPatch, accounts: tuple[Any, ...] | None, reason: str
) -> None:
    rig = buy_rig(monkeypatch, sim=simulation(accounts))
    result = await run_buy(rig)
    assert result.status == "refused" and result.reason == reason
    assert rig.log == ["simulate", "refused"]


async def test_a_failed_simulation_is_refused_with_the_chain_s_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = buy_rig(monkeypatch, sim=simulation(accounts_after(1, 1), ok=False))
    result = await run_buy(rig)
    assert result.status == "refused"
    assert result.reason is not None and result.reason.startswith("simulation_failed:")
    assert "sign" not in rig.log


async def test_the_kill_switch_re_read_before_the_signature_blocks_a_buy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = buy_rig(monkeypatch)
    rig.ctx.kill.flip_on_refresh = KillSwitchState.TRADING_DISABLED
    result = await run_buy(rig)
    assert result.status == "refused" and result.reason == "kill_switch_blocked_before_signing"
    assert rig.ctx.kill.refreshes == 1 and "sign" not in rig.log
    assert rig.log == ["simulate", "refused"], "re-read after the last wait on the RPC"


async def test_an_inflow_landing_in_the_window_does_not_pollute_the_fill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Astra (review of this diff): a treasury top-up of 0,04 SOL between the
    reads must not turn a 0,052 SOL buy into a 0,012 SOL one — the fill is the
    signature's own meta, whatever the wallet did meanwhile."""
    rig = buy_rig(monkeypatch)
    rig.ctx.chain.lamports_after_first_read = 540_000_000  # +0,04 SOL landed meanwhile
    result = await run_buy(rig)
    assert result.status == "confirmed"
    assert result.sol_delta_lamports == -(TICKET + ATA_RENT + 5_050)
    assert rig.ctx.chain.reads == 1 and rig.ctx.chain.lamports == 540_000_000


async def test_a_sell_proceeds_under_trading_disabled_and_fills_in_lamports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log: list[str] = []
    tokens, sol_out = OUT, 49_800_000
    before, after = 450_000_000, 450_000_000 + sol_out - 60_000
    rpc = FakeRpc(log, simulation(accounts_after(after, 0)))
    rpc.transaction = tx_meta(wallet_pre=before, wallet_post=after, token_pre=tokens, token_post=0)
    chain = FakeChain(rpc, before, TokenAccountRead(True, tokens))
    jupiter = FakeJupiter(
        quote(input_mint=WIF, output_mint=WSOL, amount=tokens, out=sol_out),
        as_swap(sell_message(in_amount=tokens, out=sol_out)),
    )
    kill = FakeKill(effective=KillSwitchState.TRADING_DISABLED)
    ctx = FakeContext(FakeConfig(), chain, FakeSigner(log), kill, jupiter)
    db = Db(log)
    wire_db(monkeypatch, db)
    result = await spot_send.spot_leg(
        cast(Any, ctx),
        order_id=ORDER,
        input_mint=WIF,
        output_mint=WSOL,
        amount_atoms=tokens,
        slippage_bps=300,
        max_priority_fee_lamports=100_000,
    )
    assert result.status == "confirmed"
    assert result.filled_atoms == sol_out - 60_000 == result.sol_delta_lamports
    assert result.ata_rent_lamports == 0
    assert log == [
        "simulate",
        "simulated",
        "sign",
        "submitted",
        "send",
        "get_transaction",
        "confirmed",
    ]
    assert rpc.simulated_accounts == (WALLET, WIF_ATA)


async def test_a_sell_whose_simulated_sol_is_short_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log: list[str] = []
    tokens, sol_out = OUT, 49_800_000
    threshold = sol_out * 9950 // 10_000
    rpc = FakeRpc(log, simulation(accounts_after(450_000_000 + threshold - 3_000_000, 0)))
    chain = FakeChain(rpc, 450_000_000, TokenAccountRead(True, tokens))
    jupiter = FakeJupiter(
        quote(input_mint=WIF, output_mint=WSOL, amount=tokens, out=sol_out),
        as_swap(sell_message(in_amount=tokens, out=sol_out)),
    )
    ctx = FakeContext(FakeConfig(), chain, FakeSigner(log), FakeKill(), jupiter)
    wire_db(monkeypatch, Db(log))
    result = await spot_send.spot_leg(
        cast(Any, ctx),
        order_id=ORDER,
        input_mint=WIF,
        output_mint=WSOL,
        amount_atoms=tokens,
        slippage_bps=50,
        max_priority_fee_lamports=100_000,
    )
    assert (result.status, result.reason) == ("refused", "simulation_sol_short")
    assert "sign" not in log


# ------------------------------------------------------------- after the signature
async def test_a_confirmation_that_stays_pending_is_submitted_unconfirmed_never_confirmed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = buy_rig(monkeypatch)
    rig.ctx.chain.rpc.statuses = [None]
    result = await run_buy(rig)
    assert result.status == "submitted_unconfirmed"
    assert result.reason == "confirm_pending_reconcile" and result.signature == SIGNATURE
    assert result.filled_atoms == 0 and result.sol_delta_lamports == 0
    assert rig.db.statuses() == ["simulated", "submitted"], "the row stays submitted"
    assert rig.ctx.chain.rpc.status_calls == 3  # confirm_timeout_s = 3, capped at 20


async def test_a_send_that_raises_keeps_the_row_submitted_with_its_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = buy_rig(monkeypatch)
    rig.ctx.chain.rpc.send_error = TimeoutError("relay timed out")
    result = await run_buy(rig)
    assert result.status == "submitted_unconfirmed"
    assert result.reason == "send_unknown:TimeoutError" and result.signature == SIGNATURE
    assert rig.db.statuses() == ["simulated", "submitted"], "never failed after a send"
    assert rig.log.index("submitted") < rig.log.index("send")


async def test_a_send_the_rpc_refused_by_construction_is_failed_not_relayed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = buy_rig(monkeypatch)
    rig.ctx.chain.rpc.send_error = SendDisabled()
    result = await run_buy(rig)
    assert (result.status, result.reason) == ("failed", "send_disabled")
    assert rig.db.statuses() == ["simulated", "submitted", "failed"]


async def test_an_on_chain_error_is_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    rig = buy_rig(monkeypatch)
    rig.ctx.chain.rpc.statuses = [{"confirmationStatus": "confirmed", "err": {"x": 1}}]
    result = await run_buy(rig)
    assert (result.status, result.reason) == ("failed", "on_chain_error")
    assert rig.db.statuses() == ["simulated", "submitted", "failed"]


async def test_a_confirmed_buy_whose_fill_is_not_visible_yet_is_not_confirmed_with_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = buy_rig(monkeypatch)
    rig.ctx.chain.rpc.transaction = None  # confirmed by status, not served by getTransaction yet
    result = await run_buy(rig)
    assert result.status == "submitted_unconfirmed" and result.reason == "fill_not_visible"
    assert rig.db.statuses() == ["simulated", "submitted"]
    rig = buy_rig(monkeypatch, token_after=0)  # a meta whose token delta is zero
    result = await run_buy(rig)
    assert result.status == "submitted_unconfirmed" and result.reason == "fill_inconsistent"
    rig = buy_rig(monkeypatch, wallet_after=500_000_000)  # tokens landed, no SOL left: no
    result = await run_buy(rig)
    assert result.status == "submitted_unconfirmed" and result.reason == "fill_inconsistent"
    assert rig.db.statuses() == ["simulated", "submitted"]


async def test_a_chain_read_that_fails_after_confirmation_leaves_the_row_submitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = buy_rig(monkeypatch)
    rig.ctx.chain.rpc.transaction_error = ConnectionError("rpc down")
    result = await run_buy(rig)
    assert result.status == "submitted_unconfirmed"
    assert result.reason == "confirm_fill_unreadable:ConnectionError"
    assert rig.db.statuses() == ["simulated", "submitted"]


async def test_a_row_that_cannot_take_the_signature_is_never_broadcast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = buy_rig(monkeypatch)
    rig.db.submitted_ok = False
    result = await run_buy(rig)
    assert (result.status, result.reason) == ("failed", "row_not_ready")
    assert "send" not in rig.log


def test_the_lane_signs_in_exactly_one_place() -> None:
    """Design §9 (1): ``signer.sign`` appears once across every ``spot_*.py`` module."""
    from pathlib import Path

    package = Path(spot_send.__file__).parent
    hits = {
        path.name: path.read_text(encoding="utf-8").count("signer.sign(")
        for path in sorted(package.glob("spot_*.py"))
    }
    assert sum(hits.values()) == 1 and hits["spot_send.py"] == 1, hits
