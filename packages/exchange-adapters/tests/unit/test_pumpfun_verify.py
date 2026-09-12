"""§9.1 verifier — adversarial: every tampered transaction is refused, by name."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.global_state import GlobalAccount, decode_global_account
from hunter_exchanges.pumpfun.solana_codec import (
    SYSTEM_PROGRAM_ID,
    TOKEN_2022_PROGRAM_ID,
    AccountMeta,
    Instruction,
    Message,
    b58decode,
    compile_message,
    serialize_message,
    set_compute_unit_limit,
    set_compute_unit_price,
    u64_le,
)
from hunter_exchanges.pumpfun.trade_event import trade_events_from_transaction
from hunter_exchanges.pumpfun.tx import (
    TradeIntent,
    build_buy_instruction,
    build_trade_message,
    create_ata_idempotent,
)
from hunter_exchanges.pumpfun.verify import (
    ExecutionCaps,
    UnverifiedTransaction,
    verify_trade_message,
)

FIXTURES = Path(__file__).parents[1] / "fixtures/pumpfun"
BLOCKHASH = "BQ8v5pyUzayNkgPghSBd36pVgG14SGLExT5kwWkmYZWJ"
TIP_ACCOUNT = "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5"  # a Jito tip account shape
CAPS = ExecutionCaps(
    max_compute_unit_limit=400_000,
    max_compute_unit_price_micro_lamports=20_000,
    max_jito_tip_lamports=100_000,
    jito_tip_account=TIP_ACCOUNT,
)


@pytest.fixture(scope="module")
def global_account() -> GlobalAccount:
    raw: dict[str, Any] = json.loads((FIXTURES / "rpc_global_account_raw.json").read_text())
    value = raw["result"]["value"]
    return decode_global_account(value["data"][0], owner=value["owner"])


@pytest.fixture(scope="module")
def intent(global_account: GlobalAccount) -> TradeIntent:
    tx: dict[str, Any] = json.loads((FIXTURES / "rpc_tx_buy_raw.json").read_text())["result"]
    (event,) = trade_events_from_transaction(tx, program_id=PUMP_PROGRAM_ID)
    return TradeIntent(
        side="buy",
        mint=event.mint,
        user=event.user,
        creator=event.creator,
        token_program=TOKEN_2022_PROGRAM_ID,
        token_amount=event.token_amount,
        sol_limit=990000001,
        fee_recipient=global_account.fee_recipient,
        buyback_fee_recipient=global_account.buyback_fee_recipients[0],
        is_mayhem_mode=False,
    )


def _message(intent: TradeIntent, global_account: GlobalAccount, **kwargs: Any) -> Message:
    trade = build_buy_instruction(intent, global_account)
    return build_trade_message(
        trade,
        payer=intent.user,
        recent_blockhash=BLOCKHASH,
        compute_unit_limit=kwargs.get("limit", 400_000),
        compute_unit_price_micro_lamports=kwargs.get("price", 10_000),
        create_user_ata=kwargs.get("ata"),
    )


def _verify(message: Message, intent: TradeIntent, global_account: GlobalAccount) -> Any:
    return verify_trade_message(
        serialize_message(message), intent, global_account, CAPS, expected_blockhash=BLOCKHASH
    )


def _refused(message: Message, intent: TradeIntent, global_account: GlobalAccount) -> str:
    with pytest.raises(UnverifiedTransaction) as excinfo:
        _verify(message, intent, global_account)
    return excinfo.value.reason


def _with_trade(
    message: Message, mutate: Any, intent: TradeIntent, extra: list[Instruction] | None = None
) -> Message:
    """Rebuild the message with the trade instruction mutated (and optional extra instructions)."""
    from hunter_exchanges.pumpfun.solana_codec import decompile_message

    instructions = list(decompile_message(message))
    trade_index = next(i for i, ix in enumerate(instructions) if ix.program_id == PUMP_PROGRAM_ID)
    instructions[trade_index] = mutate(instructions[trade_index])
    return compile_message(intent.user, instructions + (extra or []), message.recent_blockhash)


def test_our_own_message_verifies(intent: TradeIntent, global_account: GlobalAccount) -> None:
    ata = create_ata_idempotent(
        payer=intent.user, owner=intent.user, mint=intent.mint, token_program=intent.token_program
    )
    verified = _verify(_message(intent, global_account, ata=ata), intent, global_account)
    assert (
        verified.compute_unit_limit == 400_000
        and verified.compute_unit_price_micro_lamports == 10_000
    )
    assert verified.creates_user_ata and verified.jito_tip_lamports == 0
    assert len(verified.trade.accounts) == 18


def test_tampered_amount_is_refused(intent: TradeIntent, global_account: GlobalAccount) -> None:
    def bump_amount(ix: Instruction) -> Instruction:
        return replace(ix, data=ix.data[:8] + u64_le(intent.token_amount + 1) + ix.data[16:])

    assert (
        _refused(
            _with_trade(_message(intent, global_account), bump_amount, intent),
            intent,
            global_account,
        )
        == "trade_instruction_differs_from_intent"
    )


def test_tampered_max_sol_cost_is_refused(
    intent: TradeIntent, global_account: GlobalAccount
) -> None:
    def raise_cost(ix: Instruction) -> Instruction:
        return replace(ix, data=ix.data[:16] + u64_le(intent.sol_limit * 10))

    assert (
        _refused(
            _with_trade(_message(intent, global_account), raise_cost, intent),
            intent,
            global_account,
        )
        == "trade_instruction_differs_from_intent"
    )


def test_swapped_fee_recipient_is_refused(
    intent: TradeIntent, global_account: GlobalAccount
) -> None:
    def to_attacker(ix: Instruction) -> Instruction:
        accounts = list(ix.accounts)
        accounts[1] = AccountMeta("sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d", False, True)
        return replace(ix, accounts=tuple(accounts))

    assert (
        _refused(
            _with_trade(_message(intent, global_account), to_attacker, intent),
            intent,
            global_account,
        )
        == "trade_instruction_differs_from_intent"
    )


def test_extra_transfer_to_unknown_destination_is_refused(
    intent: TradeIntent, global_account: GlobalAccount
) -> None:
    drain = Instruction(
        SYSTEM_PROGRAM_ID,
        (
            AccountMeta(intent.user, True, True),
            AccountMeta("sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d", False, True),
        ),
        b"\x02\x00\x00\x00" + u64_le(1_000_000),
    )
    message = _with_trade(_message(intent, global_account), lambda ix: ix, intent, [drain])
    assert _refused(message, intent, global_account) == "transfer_destination_not_tip_account"


def test_jito_tip_within_cap_ok_above_cap_refused(
    intent: TradeIntent, global_account: GlobalAccount
) -> None:
    def tip(lamports: int) -> Instruction:
        return Instruction(
            SYSTEM_PROGRAM_ID,
            (AccountMeta(intent.user, True, True), AccountMeta(TIP_ACCOUNT, False, True)),
            b"\x02\x00\x00\x00" + u64_le(lamports),
        )

    ok = _with_trade(_message(intent, global_account), lambda ix: ix, intent, [tip(50_000)])
    assert _verify(ok, intent, global_account).jito_tip_lamports == 50_000
    over = _with_trade(_message(intent, global_account), lambda ix: ix, intent, [tip(100_001)])
    assert _refused(over, intent, global_account) == "jito_tip_above_cap"


def test_foreign_program_is_refused(intent: TradeIntent, global_account: GlobalAccount) -> None:
    foreign = Instruction(
        "6Vo3245eszAb5wuqEMw8mGdbfRUdKbHhDHP5LcaGuTAB",
        (AccountMeta(intent.user, True, True),),
        b"\x01",
    )
    message = _with_trade(_message(intent, global_account), lambda ix: ix, intent, [foreign])
    assert _refused(message, intent, global_account) == "program_not_allowed"


def test_second_signer_is_refused(intent: TradeIntent, global_account: GlobalAccount) -> None:
    def add_signer(ix: Instruction) -> Instruction:
        return replace(
            ix,
            accounts=ix.accounts
            + (AccountMeta("sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d", True, False),),
        )

    assert (
        _refused(
            _with_trade(_message(intent, global_account), add_signer, intent),
            intent,
            global_account,
        )
        == "signer_is_not_our_wallet"
    )


def test_wrong_payer_is_refused(intent: TradeIntent, global_account: GlobalAccount) -> None:
    trade = build_buy_instruction(intent, global_account)
    message = compile_message(
        "sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d",
        [set_compute_unit_limit(1), set_compute_unit_price(1), trade],
        BLOCKHASH,
    )
    assert _refused(message, intent, global_account) == "signer_is_not_our_wallet"


def test_compute_budget_caps_and_presence(
    intent: TradeIntent, global_account: GlobalAccount
) -> None:
    assert (
        _refused(_message(intent, global_account, price=20_001), intent, global_account)
        == "compute_unit_price_above_cap"
    )
    assert (
        _refused(_message(intent, global_account, limit=400_001), intent, global_account)
        == "compute_unit_limit_above_cap"
    )
    trade = build_buy_instruction(intent, global_account)
    bare = compile_message(intent.user, [trade], BLOCKHASH)
    assert _refused(bare, intent, global_account) == "compute_budget_missing"


def test_blockhash_missing_or_different_is_refused(
    intent: TradeIntent, global_account: GlobalAccount
) -> None:
    trade = build_buy_instruction(intent, global_account)
    zero = build_trade_message(
        trade,
        payer=intent.user,
        recent_blockhash="11111111111111111111111111111111",
        compute_unit_limit=1,
        compute_unit_price_micro_lamports=1,
    )
    assert _refused(zero, intent, global_account) == "blockhash_missing"
    other = build_trade_message(
        trade,
        payer=intent.user,
        recent_blockhash="Dk23hHopzL1avB5d1qFQCKvMGgoEE9CvgBgWiVrjo5Ji",
        compute_unit_limit=1,
        compute_unit_price_micro_lamports=1,
    )
    assert _refused(other, intent, global_account) == "blockhash_mismatch"


def test_two_trades_or_none_are_refused(intent: TradeIntent, global_account: GlobalAccount) -> None:
    trade = build_buy_instruction(intent, global_account)
    twice = compile_message(
        intent.user, [set_compute_unit_limit(1), set_compute_unit_price(1), trade, trade], BLOCKHASH
    )
    assert _refused(twice, intent, global_account) == "more_than_one_trade_instruction"
    none = compile_message(
        intent.user, [set_compute_unit_limit(1), set_compute_unit_price(1)], BLOCKHASH
    )
    assert _refused(none, intent, global_account) == "trade_instruction_missing"


def test_ata_for_someone_else_is_refused(
    intent: TradeIntent, global_account: GlobalAccount
) -> None:
    ata = create_ata_idempotent(
        payer=intent.user,
        owner="sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d",
        mint=intent.mint,
        token_program=intent.token_program,
    )
    assert (
        _refused(_message(intent, global_account, ata=ata), intent, global_account)
        == "ata_instruction_not_ours"
    )


def test_site_v0_transaction_is_refused_not_parsed(
    intent: TradeIntent, global_account: GlobalAccount
) -> None:
    site: dict[str, Any] = json.loads((FIXTURES / "swap_build_probe4_raw.txt").read_text())
    message = b58decode(site["transaction"])[65:]
    with pytest.raises(UnverifiedTransaction) as excinfo:
        verify_trade_message(message, intent, global_account, CAPS)
    assert excinfo.value.reason == "undecodable_message"


def test_sell_intent_against_buy_message_is_refused(
    intent: TradeIntent, global_account: GlobalAccount
) -> None:
    sell_intent = replace(intent, side="sell", sol_limit=1)
    assert (
        _refused(_message(intent, global_account), sell_intent, global_account)
        == "trade_instruction_differs_from_intent"
    )
