"""T4.81 — ``spot_send.spot_leg`` over a transaction whose accounts live in an
address lookup table: the desk's real shape since 23/09/2026. Fakes only
(``spot_fakes.py``): the lookup table is served by the fake RPC's
``getMultipleAccounts``, the transaction is encoded and decoded for real.

What these pin down: the tables are read **before** the verification and before
anything is signed; a table that cannot be read, or that resolves to somebody
else's account, refuses the leg with nothing signed and nothing sent.
"""

from __future__ import annotations

import base64

import pytest

from hunter_exchanges.jupiter.versioned_tx import decode_versioned_transaction
from hunter_meme_executor.spot_verify import SpotSwapIntent, verify_spot_swap_tx
from hunter_meme_executor.treasury_rules import TreasurySwapRefused

from .spot_fakes import Rig, buy_rig, run_buy
from .spot_tx_fixtures import (
    ALT_TABLE,
    ALT_TABLE_ADDRESSES,
    OUT,
    SIGNATURE,
    TICKET,
    WALLET,
    WIF,
    WIF_ATA,
    WSOL,
    alt_buy_message,
    as_swap,
    lookup_table_data,
    table_addresses,
)

pytestmark = pytest.mark.unit


def _rig(monkeypatch: pytest.MonkeyPatch, addresses: tuple[str, ...] | None) -> Rig:
    rig = buy_rig(monkeypatch, message=alt_buy_message())
    if addresses is not None:
        rig.ctx.chain.rpc.lookup_tables = {ALT_TABLE: lookup_table_data(addresses)}
    return rig


async def test_a_buy_through_a_lookup_table_resolves_verifies_and_confirms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = _rig(monkeypatch, ALT_TABLE_ADDRESSES)
    result = await run_buy(rig)
    assert result.status == "confirmed"
    assert result.signature == SIGNATURE
    assert result.filled_atoms == OUT
    # the tables are read first, then the simulation, and only then the signature
    assert rig.log[: rig.log.index("sign")] == [
        "get_multiple_accounts",
        "simulate",
        "simulated",
    ]
    assert rig.db.statuses() == ["simulated", "submitted", "confirmed"]
    # and the bytes that were signed are the bytes that were verified and sent
    # (Astra, T4.81 diff review): nothing is rebuilt between the two.
    original = decode_versioned_transaction(
        base64.b64decode(as_swap(alt_buy_message()).swap_transaction_b64)
    )
    signed = rig.signer.signed[0]
    assert signed == original.message_bytes
    assert rig.ctx.chain.rpc.sent[0].endswith(signed)


async def test_a_lookup_table_the_rpc_cannot_serve_refuses_the_leg_unsigned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = _rig(monkeypatch, None)
    result = await run_buy(rig)
    assert result.status == "refused"
    assert result.reason == f"lookup_table_missing:{ALT_TABLE}"
    assert "sign" not in rig.log and "send" not in rig.log and "simulate" not in rig.log
    assert rig.db.statuses() == ["refused"]


async def test_an_rpc_failure_on_the_table_read_refuses_by_name_unsigned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = _rig(monkeypatch, ALT_TABLE_ADDRESSES)
    rig.ctx.chain.rpc.call_error = TimeoutError("rpc down")
    result = await run_buy(rig)
    assert result.status == "refused"
    assert result.reason == "lookup_table_read_failed:TimeoutError"
    assert "sign" not in rig.log


async def test_a_table_that_points_the_route_at_a_stranger_refuses_unsigned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The table holds a token account that is not ours where the route's
    destination index points: refused before the simulation, nothing signed."""
    stranger = "So11111111111111111111111111111111111111112"
    rig = _rig(monkeypatch, table_addresses(16, {5: stranger, 7: WIF}))
    result = await run_buy(rig)
    assert result.status == "refused"
    assert result.reason == "ata_address_mismatch"
    assert "sign" not in rig.log and "simulate" not in rig.log


async def test_a_deactivated_table_refuses_the_leg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = buy_rig(monkeypatch, message=alt_buy_message())
    rig.ctx.chain.rpc.lookup_tables = {
        ALT_TABLE: lookup_table_data(ALT_TABLE_ADDRESSES, deactivation_slot=1)
    }
    result = await run_buy(rig)
    assert result.status == "refused"
    assert result.reason == f"lookup_table_deactivated:{ALT_TABLE}"
    assert "sign" not in rig.log


def test_the_same_transaction_is_refused_when_nothing_resolved_it() -> None:
    """The regression that kept the desk inert: without the resolution step the
    very same message cannot be verified at all."""
    intent = SpotSwapIntent(
        wallet=WALLET,
        input_mint=WSOL,
        output_mint=WIF,
        in_amount=TICKET,
        min_quoted_out=OUT,
        max_slippage_bps=50,
    )
    with pytest.raises(TreasurySwapRefused) as excinfo:
        verify_spot_swap_tx(alt_buy_message(), intent=intent)
    assert excinfo.value.reason == "lookup_tables_unresolved"
    assert WIF_ATA  # the address the table holds, checked in test_spot_verify_alt
