"""T4.83 — ``treasury_send.attempt_swap`` over the **real** recorded Jupiter
swap (USDC -> SOL, 18/09/2026), whose ``CreateIdempotent`` mint only exists
inside an address lookup table.

Fakes only, in the shape of ``test_treasury_tick.py`` and ``spot_fakes.py``
(they live in ``treasury_send_rig.py`` since T4.84): no Postgres
(``role_session``/``treasury_db`` are patched), no network (the table is
served by the fake RPC's ``getMultipleAccounts``), no key (the signer returns
64 fixed bytes). The transaction is decoded for real from the fixture.

What these pin down: the tables are read **before** the verification and
before anything is signed, at ``finalized``; a table that cannot be read, that
was deactivated, that is too short or that resolves to another mint refuses
the attempt by name with nothing signed and nothing sent.
"""

from __future__ import annotations

import base64
from typing import Any

import pytest

from hunter_meme_executor.spot_alt import READ_COMMITMENT
from hunter_meme_executor.treasury_rules import USDC_MINT

from .spot_tx_fixtures import lookup_table_data, table_addresses
from .treasury_send_rig import (
    LOCAL_SIGNATURE,
    MINT_SLOT,
    TABLE,
    WSOL,
    rig,
    run_attempt,
    served,
    swap_tx,
)

pytestmark = pytest.mark.unit


# ----------------------------------------------------------------- the happy path
async def test_a_swap_whose_ata_mint_lives_in_a_table_resolves_and_confirms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = rig(monkeypatch, served(table_addresses(256, {MINT_SLOT: WSOL})))
    await run_attempt(target)
    assert target.statuses == ["quoted", "simulated", "submitted", "confirmed"]
    assert target.ctx.state.treasury_last_attempt_reason == f"ok:{LOCAL_SIGNATURE}"
    # read the tables first, simulate, and only then sign
    assert target.log[: target.log.index("sign")] == [
        "get_multiple_accounts",
        "wallet",
        "token_account",
        "simulate",
    ]
    assert target.ctx.chain.rpc.commitments == [READ_COMMITMENT] == ["finalized"]
    # the bytes signed are the bytes verified and the bytes sent
    signed = target.ctx.signer.signed[0]
    assert target.ctx.chain.rpc.sent[0].endswith(signed)
    raw = base64.b64decode(swap_tx().swap_transaction_b64)
    assert signed == raw[1 + 64 :]


# -------------------------------------------------------------- named refusals
@pytest.mark.parametrize(
    ("tables", "reason"),
    [
        ({}, f"lookup_table_missing:{TABLE}"),
        (
            served(table_addresses(256, {MINT_SLOT: WSOL}), deactivation_slot=1),
            f"lookup_table_deactivated:{TABLE}",
        ),
        (
            served(table_addresses(200, {MINT_SLOT: WSOL})),
            f"lookup_table_index_out_of_range:{TABLE}#244",
        ),
        (
            served(table_addresses(256, {MINT_SLOT: WSOL}), discriminant=0),
            f"lookup_table_uninitialized:{TABLE}",
        ),
        (served(table_addresses(256, {MINT_SLOT: USDC_MINT})), "ata_address_mismatch"),
    ],
    ids=["missing", "deactivated", "index-out-of-range", "uninitialized", "wrong-mint"],
)
async def test_a_table_that_does_not_resolve_refuses_unsigned(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, str], reason: str
) -> None:
    target = rig(monkeypatch, tables)
    await run_attempt(target)
    assert target.ctx.state.treasury_last_attempt_reason == reason
    assert target.statuses == ["quoted", "refused"]
    assert "sign" not in target.log and "send" not in target.log
    assert "simulate" not in target.log


async def test_an_rpc_failure_reading_the_tables_refuses_by_name_unsigned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = rig(monkeypatch, served(table_addresses(256, {MINT_SLOT: WSOL})))
    target.ctx.chain.rpc.call_error = TimeoutError("rpc down")
    await run_attempt(target)
    assert target.ctx.state.treasury_last_attempt_reason == "lookup_table_read_failed:TimeoutError"
    assert target.statuses == ["quoted", "refused"]
    assert "sign" not in target.log


async def test_a_table_owned_by_another_program_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fake "table" account whose owner is not the ALT program: whatever it
    holds, it is not a lookup table."""
    target = rig(monkeypatch, served(table_addresses(256, {MINT_SLOT: WSOL})))

    def call(method: str, params: list[Any]) -> Any:
        target.log.append("get_multiple_accounts")
        return {
            "context": {"slot": 1},
            "value": [
                {
                    "data": [lookup_table_data(table_addresses(256, {MINT_SLOT: WSOL})), "base64"],
                    "owner": USDC_MINT,
                    "lamports": 1,
                    "executable": False,
                }
            ],
        }

    monkeypatch.setattr(target.ctx.chain.rpc, "call", call)
    await run_attempt(target)
    assert target.ctx.state.treasury_last_attempt_reason == f"lookup_table_bad_owner:{TABLE}"
    assert "sign" not in target.log
