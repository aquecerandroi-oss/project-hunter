"""R36 — which account the executor reads and buys on for a **Mayhem** coin.

KB-0115 §7 found ``meme_tokens.bonding_curve`` disagreeing with the derived
``["bonding-curve", mint]`` PDA on one coin (KIRKJAK) and asked whether the
executor trades the right account. It does, and the row is the one that lies:
on 2026-09-16, 13 615 of the 112 108 rows of the last 7 days that carry a
``bonding_curve`` store the **same** address —
``BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s`` — on 13 615 different mints,
all of them ``mayhem_enabled``. That address is the Mayhem program's
``["sol-vault"]`` PDA (:func:`mayhem_pdas`): mainnet reports it owned by the
System Program with zero bytes of data, so it is not a bonding curve of any
mint. The per-mint PDA is the real curve (mainnet, mint
``3aYHwMeo…``: ``Ck72XTyT…``, owner ``6EF8rrec…``, ``is_mayhem_mode = true``).

These tests pin the two things that keep that true:

1. :meth:`ChainReader.curve` reads the **derived** PDA and never the stored
   column — "prefer ``meme_tokens.bonding_curve`` when present" would point
   13 615 mints at a 54 000 SOL shared treasury;
2. a Mayhem curve reaches the engine flagged and is refused by name, before
   any transaction is built.
"""

from __future__ import annotations

import base64
import struct
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from hunter_exchanges.pumpfun.decode import NATIVE_SOL_QUOTE_MINT, PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.mayhem_state import mayhem_pdas
from hunter_exchanges.pumpfun.solana_codec import TOKEN_PROGRAM_ID, pubkey_bytes
from hunter_exchanges.pumpfun.tx import bonding_curve_address
from hunter_exchanges.pumpfun.tx_rpc import AccountSnapshot
from hunter_meme_executor.admission import context_from, curve_from
from hunter_meme_executor.chain import ChainReader
from hunter_meme_executor.repo import TokenContext
from hunter_risk_meme.checks import mayhem_policy_check
from hunter_risk_meme.decision import CheckState

pytestmark = pytest.mark.unit

MAYHEM_MINT = "3aYHwMeoXeEqtLnap1TByBfmh2CHnVexX9pqMUHFpump"
OTHER_MAYHEM_MINT = "6thLk2TY5n2r1H5yguKd3NGkwb2GVH7vNuto9242pump"
STORED_ON_BOTH_ROWS = "BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s"
"""``meme_tokens.bonding_curve`` of both mints above, read from production on
2026-09-16 — one address, two mints, so at most one of them could be a curve."""
CREATOR = "GdTf8WxuDisy3J2u1tnTSzMXZjScJRibRq5QFupL95Ws"
NOW = datetime(2026, 9, 16, 21, 0, tzinfo=UTC)


def _curve_bytes(*, is_mayhem_mode: bool) -> str:
    """A 115-byte ``BondingCurve`` account, the layout ``decode.py`` documents."""
    raw = (
        bytes.fromhex("17b7f83760d8ac60")  # discriminator (validated by the decoder)
        + struct.pack(
            "<QQQQQ?",
            1_000_000_000_000_000,  # virtual_token_reserves
            26_430_445_402,  # virtual_sol_reserves
            700_000_000_000_000,  # real_token_reserves
            2_000_000_000,  # real_sol_reserves
            1_000_000_000_000_000,  # token_total_supply
            False,  # complete
        )
        + pubkey_bytes(CREATOR)
        + bytes([1 if is_mayhem_mode else 0, 0])
        + pubkey_bytes(NATIVE_SOL_QUOTE_MINT)
    )
    return base64.b64encode(raw).decode()


class _RecordingRpc:
    """Serves the curve only at the derived PDA; records every address asked for."""

    def __init__(self, *, is_mayhem_mode: bool = True) -> None:
        self.asked: list[str] = []
        self._curve_address = bonding_curve_address(MAYHEM_MINT)
        self._is_mayhem_mode = is_mayhem_mode

    def get_account(self, address: str, **_: Any) -> AccountSnapshot | None:
        self.asked.append(address)
        if address == self._curve_address:
            return AccountSnapshot(
                address=address,
                owner=PUMP_PROGRAM_ID,
                data_base64=_curve_bytes(is_mayhem_mode=self._is_mayhem_mode),
                lamports=2_000_000_000,
                slot=447_300_000,
                executable=False,
            )
        if address == MAYHEM_MINT:
            return AccountSnapshot(
                address=address,
                owner=TOKEN_PROGRAM_ID,
                data_base64="",
                lamports=0,
                slot=447_300_000,
                executable=False,
            )
        # The Mayhem sol-vault: a System-owned account with no data. Asking for
        # it is the failure this test exists to catch.
        return AccountSnapshot(
            address=address,
            owner="11111111111111111111111111111111",
            data_base64="",
            lamports=54_320_006_136_009,
            slot=447_300_000,
            executable=False,
        )


def _token() -> TokenContext:
    return TokenContext(
        created_at=NOW - timedelta(seconds=160),
        creator=CREATOR,
        initial_real_token_reserves=793_100_000,
        completed_at=None,
        migrated_at=None,
        curve_volume_1m_sol=Decimal("20"),
        features_end_time=NOW - timedelta(seconds=30),
        creator_sold=False,
        top10_share=Decimal("0.15"),
        bundled_share=Decimal("0.05"),
    )


class TestTheStoredAddressOfAMayhemCoin:
    def test_it_is_the_shared_mayhem_sol_vault_not_a_curve(self) -> None:
        assert mayhem_pdas().sol_vault == STORED_ON_BOTH_ROWS

    @pytest.mark.parametrize("mint", [MAYHEM_MINT, OTHER_MAYHEM_MINT])
    def test_no_mints_curve_pda_can_be_that_address(self, mint: str) -> None:
        assert bonding_curve_address(mint) != STORED_ON_BOTH_ROWS


class TestTheExecutorReadsTheDerivedPda:
    def test_the_curve_comes_from_the_per_mint_pda(self) -> None:
        rpc = _RecordingRpc()
        read = ChainReader(rpc)  # type: ignore[arg-type]  # only ``get_account`` is used
        result = read.curve(MAYHEM_MINT)
        assert result is not None
        assert result.account.creator == CREATOR
        assert bonding_curve_address(MAYHEM_MINT) in rpc.asked

    def test_the_shared_mayhem_vault_is_never_read(self) -> None:
        rpc = _RecordingRpc()
        ChainReader(rpc).curve(MAYHEM_MINT)  # type: ignore[arg-type]
        assert STORED_ON_BOTH_ROWS not in rpc.asked


class TestAMayhemCurveNeverReachesATransaction:
    def test_the_flag_survives_the_trip_into_the_engine(self) -> None:
        rpc = _RecordingRpc(is_mayhem_mode=True)
        read = ChainReader(rpc).curve(MAYHEM_MINT)  # type: ignore[arg-type]
        assert read is not None
        assert curve_from(read).is_mayhem_mode is True

    def test_it_is_refused_by_name_with_the_agent_state_unknown(self) -> None:
        rpc = _RecordingRpc(is_mayhem_mode=True)
        read = ChainReader(rpc).curve(MAYHEM_MINT)  # type: ignore[arg-type]
        assert read is not None
        context = context_from(MAYHEM_MINT, _token(), participation_used_sol=Decimal(0), now=NOW)
        result = mayhem_policy_check(curve_from(read), context)
        assert result.state is CheckState.UNAVAILABLE
        assert result.refusal == "mayhem_state_unknown"
