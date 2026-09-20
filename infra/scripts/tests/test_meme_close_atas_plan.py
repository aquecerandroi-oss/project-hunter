"""``meme_close_atas_plan`` (T4.77): the pure half — parsing a
``getTokenAccountsByOwner`` (``jsonParsed``) listing, the verdict per
account, the plan (selection, batches, total recoverable), the table and
the batch message the send path signs. No network, no key.
"""

from __future__ import annotations

import functools
import sys
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
REPO_ROOT = Path(__file__).resolve().parents[3]
for extra in ("services/meme-executor", "packages/exchange-adapters", "packages/risk-core"):
    candidate = str(REPO_ROOT / extra)
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from meme_close_atas_plan import (  # noqa: E402
    BATCH_SIZE,
    TokenAccountRow,
    batches,
    build_batch_message,
    build_plan,
    classify,
    format_table,
    list_token_accounts,
    parse_token_accounts,
)
from meme_close_atas_verify import priority_fee_lamports  # noqa: E402

from hunter_exchanges.pumpfun.solana_codec import (  # noqa: E402
    COMPUTE_BUDGET_PROGRAM_ID,
    TOKEN_2022_PROGRAM_ID,
    TOKEN_PROGRAM_ID,
    associated_token_address,
    b58encode,
    decompile_message,
)

WALLET = "ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4"
OTHER = "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"
WSOL = "So11111111111111111111111111111111111111112"
RENT = 2_039_280
BLOCKHASH = b58encode(bytes([7]) * 32)


def _mint(i: int) -> str:
    return b58encode(bytes([0x10 + i]) * 32)


@functools.cache
def _ata(
    i: int, program: str = TOKEN_PROGRAM_ID, owner: str = WALLET, mint: str | None = None
) -> str:
    """The real associated token address — the plan derives it to refuse
    anything that is a token account of the wallet but not its ATA."""
    return associated_token_address(owner, mint or _mint(i), token_program=program)


def raw_account(
    i: int,
    *,
    amount: int = 0,
    lamports: int = RENT,
    owner: str = WALLET,
    program: str = TOKEN_PROGRAM_ID,
    delegate: str | None = None,
    close_authority: str | None = None,
    state: str = "initialized",
    native: bool = False,
    mint: str | None = None,
    pubkey: str | None = None,
    kind: str = "account",
    extensions: list[dict[str, Any]] | None = None,
    space: int | None = None,
) -> dict[str, Any]:
    """One ``value[]`` entry as the RPC returns it with ``encoding: jsonParsed``.
    A Token-2022 row carries the ``extensions`` list the account decoder
    emits (``[{"extension": "immutableOwner"}]`` for the desk's pump.fun ATAs,
    170 bytes, 1 513 840 lamports — T4.77b) unless the test says otherwise."""
    if extensions is None and program == TOKEN_2022_PROGRAM_ID:
        extensions = [{"extension": "immutableOwner"}]
    if space is None:
        space = 165 if program == TOKEN_PROGRAM_ID else 170
    info: dict[str, Any] = {
        "isNative": native,
        "mint": mint or _mint(i),
        "owner": owner,
        "state": state,
        "tokenAmount": {
            "amount": str(amount),
            "decimals": 6,
            "uiAmount": amount / 1e6,
            "uiAmountString": str(amount / 1e6),
        },
    }
    if native:
        info["rentExemptReserve"] = {"amount": str(RENT), "decimals": 9}
    if delegate is not None:
        info["delegate"] = delegate
        info["delegatedAmount"] = {"amount": "1", "decimals": 6}
    if close_authority is not None:
        info["closeAuthority"] = close_authority
    if extensions:
        info["extensions"] = extensions
    return {
        "pubkey": pubkey or _ata(i, program, owner, mint),
        "account": {
            "lamports": lamports,
            "owner": program,
            "executable": False,
            "rentEpoch": 18446744073709551615,
            "space": space,
            "data": {
                "program": "spl-token" if program == TOKEN_PROGRAM_ID else "spl-token-2022",
                "parsed": {"type": kind, "info": info},
                "space": space,
            },
        },
    }


def _row(i: int, **kw: Any) -> TokenAccountRow:
    program = kw.get("program", TOKEN_PROGRAM_ID)
    (row,) = parse_token_accounts([raw_account(i, **kw)], program=program)
    return row


def test_parse_reads_every_field_the_verdict_needs() -> None:
    row = _row(1, amount=5, delegate=OTHER, close_authority=OTHER)
    assert row == TokenAccountRow(
        address=_ata(1),
        mint=_mint(1),
        owner=WALLET,
        program=TOKEN_PROGRAM_ID,
        lamports=RENT,
        amount=5,
        is_native=False,
        rent_exempt_reserve=None,
        delegate=OTHER,
        close_authority=OTHER,
        state="initialized",
        kind="account",
        extensions=(),
        space=165,
    )


def test_parse_refuses_a_row_whose_program_differs_from_the_listing_asked() -> None:
    with pytest.raises(ValueError, match="program_mismatch"):
        parse_token_accounts(
            [raw_account(1, program=TOKEN_2022_PROGRAM_ID)], program=TOKEN_PROGRAM_ID
        )


def test_parse_refuses_a_malformed_row_instead_of_guessing() -> None:
    broken = raw_account(1)
    del broken["account"]["data"]["parsed"]["info"]["tokenAmount"]
    with pytest.raises(ValueError, match="unparsable"):
        parse_token_accounts([broken], program=TOKEN_PROGRAM_ID)


@pytest.mark.parametrize(
    ("kw", "verdict"),
    [
        ({}, "close"),
        ({"program": TOKEN_2022_PROGRAM_ID}, "skipped:token_2022"),
        ({"program": TOKEN_2022_PROGRAM_ID, "amount": 7}, "skipped:token_2022"),
        ({"amount": 1}, "skipped:nonzero_balance"),
        ({"delegate": OTHER}, "skipped:authority_mismatch"),
        ({"close_authority": OTHER}, "skipped:authority_mismatch"),
        ({"close_authority": WALLET}, "close"),
        ({"owner": OTHER}, "skipped:authority_mismatch"),
        ({"state": "frozen"}, "skipped:frozen"),
        ({"native": True, "mint": WSOL}, "close"),
        ({"native": True, "mint": WSOL, "lamports": RENT + 1}, "skipped:wsol_holds_lamports"),
        (
            {"native": True, "mint": WSOL, "amount": 3, "lamports": RENT + 3},
            "skipped:wsol_holds_lamports",
        ),
    ],
)
def test_the_verdict_table(kw: dict[str, Any], verdict: str) -> None:
    assert classify(_row(1, **kw), wallet=WALLET) == verdict


def test_a_row_with_zero_lamports_is_never_worth_closing() -> None:
    assert classify(_row(1, lamports=0), wallet=WALLET) == "skipped:no_rent"


def test_a_token_account_that_is_not_the_wallets_ata_is_listed_and_never_closed() -> None:
    """Astra (T4.77 review): an auxiliary token account some other integration
    keeps at a specific address is not rent to recover — it is that
    integration's account."""
    stray = _row(1, pubkey=b58encode(bytes([0x77]) * 32))
    assert classify(stray, wallet=WALLET) == "skipped:not_ata"
    plan = build_plan([stray, _row(2)], wallet=WALLET, limit=None)
    assert [r.address for r in plan.selected] == [_ata(2)]
    assert plan.skipped == {"not_ata": 1}


def _rows(n: int, **kw: Any) -> list[TokenAccountRow]:
    return [_row(i, **kw) for i in range(n)]


def test_the_plan_selects_only_close_verdicts_and_sums_their_rent() -> None:
    rows = [_row(0), _row(1, amount=1), _row(2, program=TOKEN_2022_PROGRAM_ID), _row(3)]
    plan = build_plan(rows, wallet=WALLET, limit=None)
    assert [v for _, v in plan.rows] == [
        "close",
        "skipped:nonzero_balance",
        "skipped:token_2022",
        "close",
    ]
    assert [r.address for r in plan.selected] == [_ata(0), _ata(3)]
    assert plan.total_recoverable == 2 * RENT
    assert plan.skipped == {"nonzero_balance": 1, "token_2022": 1}


def test_the_limit_caps_the_selection_not_the_listing() -> None:
    plan = build_plan(_rows(12), wallet=WALLET, limit=3)
    assert len(plan.rows) == 12
    assert len(plan.selected) == 3
    assert plan.total_recoverable == 3 * RENT


def test_batches_are_at_most_eight_and_disjoint() -> None:
    plan = build_plan(_rows(19), wallet=WALLET, limit=None)
    parts = batches(plan)
    assert [len(p) for p in parts] == [BATCH_SIZE, BATCH_SIZE, 3]
    seen = [r.address for part in parts for r in part]
    assert len(seen) == len(set(seen)) == 19


def test_the_table_names_mint8_ata8_rent_and_verdict_and_the_total() -> None:
    plan = build_plan([_row(0), _row(1, amount=1)], wallet=WALLET, limit=None)
    text = format_table(plan)
    assert _mint(0)[:8] in text and _ata(0)[:8] in text
    assert f"{RENT}" in text
    assert "close" in text and "skipped:nonzero_balance" in text
    assert "total_recoverable_lamports=2039280" in text
    assert "total_recoverable_sol=0.002039280" in text
    assert "selected=1" in text and "listed=2" in text
    assert "token_2022_rent_not_touched" not in text


def test_the_table_names_the_token_2022_rent_this_script_never_touches() -> None:
    """Measured on 19/09/2026: the desk's 34 pump.fun ATAs are Token-2022
    (1 513 840 lamports each) — the operator must see that number, not
    just a verdict column."""
    rows = [_row(0)] + [
        _row(i, program=TOKEN_2022_PROGRAM_ID, lamports=1_513_840) for i in range(1, 35)
    ]
    text = format_table(build_plan(rows, wallet=WALLET, limit=None))
    assert "skipped=token_2022=34" in text
    assert "token_2022_rent_not_touched_lamports=51470560" in text
    assert "token_2022_rent_not_touched_sol=0.051470560" in text
    assert f"total_recoverable_lamports={RENT}" in text


def test_the_batch_message_is_budget_plus_closes_to_the_wallet() -> None:
    accounts = tuple(_ata(i) for i in range(8))
    message = build_batch_message(
        wallet=WALLET,
        accounts=accounts,
        blockhash=BLOCKHASH,
        priority_fee_lamports=10_000,
        token_program=TOKEN_PROGRAM_ID,
    )
    assert message.account_keys[0] == WALLET
    assert message.num_required_signatures == 1
    assert message.recent_blockhash == BLOCKHASH
    instructions = decompile_message(message)
    assert [ix.program_id for ix in instructions[:2]] == [COMPUTE_BUDGET_PROGRAM_ID] * 2
    closes = instructions[2:]
    assert [ix.program_id for ix in closes] == [TOKEN_PROGRAM_ID] * 8
    assert [ix.accounts[0].pubkey for ix in closes] == list(accounts)
    for ix in closes:
        assert ix.data == bytes([9])
        assert ix.accounts[1].pubkey == WALLET and ix.accounts[1].is_writable
        assert ix.accounts[2].pubkey == WALLET and ix.accounts[2].is_signer
    limit = int.from_bytes(instructions[0].data[1:], "little")
    price = int.from_bytes(instructions[1].data[1:], "little")
    assert priority_fee_lamports(compute_unit_limit=limit, micro_lamports_per_cu=price) <= 10_000


def test_the_batch_message_refuses_more_than_a_batch_or_nothing() -> None:
    with pytest.raises(ValueError, match="batch_size"):
        build_batch_message(
            wallet=WALLET,
            accounts=tuple(_ata(i) for i in range(9)),
            blockhash=BLOCKHASH,
            priority_fee_lamports=1,
            token_program=TOKEN_PROGRAM_ID,
        )
    with pytest.raises(ValueError, match="batch_size"):
        build_batch_message(
            wallet=WALLET,
            accounts=(),
            blockhash=BLOCKHASH,
            priority_fee_lamports=1,
            token_program=TOKEN_PROGRAM_ID,
        )


class _ListingRpc:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[Any]]] = []

    def call(self, method: str, params: list[Any]) -> Any:
        self.calls.append((method, params))
        program = params[1]["programId"]
        value = (
            [raw_account(0), raw_account(1, amount=4)]
            if program == TOKEN_PROGRAM_ID
            else [raw_account(2, program=TOKEN_2022_PROGRAM_ID)]
        )
        return {"context": {"slot": 1}, "value": value}


def test_listing_asks_both_programs_with_json_parsed_and_merges() -> None:
    rpc = _ListingRpc()
    rows = list_token_accounts(rpc, WALLET)
    assert [m for m, _ in rpc.calls] == ["getTokenAccountsByOwner"] * 2
    for _, params in rpc.calls:
        assert params[0] == WALLET
        assert params[2]["encoding"] == "jsonParsed"
    assert {p[1]["programId"] for _, p in rpc.calls} == {TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID}
    assert [r.program for r in rows] == [TOKEN_PROGRAM_ID, TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID]
