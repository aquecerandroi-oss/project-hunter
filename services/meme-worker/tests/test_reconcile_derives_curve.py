"""T4.39/R36: ``reconcile_once`` derives the bonding-curve PDA from the mint
and never trusts ``tracked.bonding_curve``.

13 615 of 112 108 seven-day ``meme_tokens`` rows store the Mayhem program's
shared sol-vault in that column (R36, ``docs/PUMPFUN.md`` §9) — a stale
tracked entry loaded from the database before the repair script runs still
carries it, so ``reconcile_once`` must not read it at all, even as a fallback.

No database, no socket: the same ``_no_role``/fake-session pattern as
``test_mayhem.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from hunter_exchanges.pumpfun.models import NormalizedCurveState
from hunter_exchanges.pumpfun.pdas import bonding_curve_address
from hunter_meme_worker import collect
from hunter_meme_worker.config import MemeConfig
from hunter_meme_worker.context import RadarContext, RadarState
from hunter_meme_worker.sources import SourcesState
from hunter_meme_worker.tracker import MintTracker, TrackedMint

pytestmark = pytest.mark.unit

T0 = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
MINT = "3aYHwMeoXeEqtLnap1TByBfmh2CHnVexX9pqMUHFpump"
SOL_VAULT = "BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s"
"""The Mayhem program's shared ``["sol-vault"]`` PDA (R36) — what the
contaminated column stores for 13 615 mints, never a curve of any of them."""


class FakeChain:
    def __init__(self) -> None:
        self.asked: list[tuple[str, str]] = []

    async def get_curve_state(self, mint: str, bonding_curve: str) -> Any:
        self.asked.append((mint, bonding_curve))
        if bonding_curve == SOL_VAULT:
            raise AssertionError("reconcile_once must never read the sol-vault")
        return NormalizedCurveState(
            mint=mint,
            virtual_sol_reserves=Decimal("30"),
            virtual_token_reserves=Decimal("1073000000"),
            real_sol_reserves=Decimal("0"),
            real_token_reserves=Decimal("793100000"),
            total_supply=Decimal("1000000000"),
            complete=False,
            market_cap_sol=Decimal("28"),
            source="solana_rpc",
            mayhem_enabled=True,
            received_at=T0,
            observed_at=T0,
        )

    async def get_mayhem_flows(self, mints: Any) -> Any:
        raise AssertionError("not the Mayhem loop")

    async def get_curve_states(
        self, mints: Any, *, with_block_time: bool = True, commitment: str = "finalized"
    ) -> Any:
        raise AssertionError("reconcile_once reads one mint at a time")


class _Session:
    def __init__(self) -> None:
        self.statements: list[Any] = []

    async def execute(self, statement: Any, params: Any = None) -> None:
        self.statements.append((str(statement)[:60], params))

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


def _no_role(factory: Any, db_role: str) -> Any:
    return factory()


def _context(chain: FakeChain, tracker: MintTracker) -> RadarContext:
    return RadarContext(
        config=MemeConfig(rpc_top_k=5),
        session_factory=lambda: _Session(),  # type: ignore[arg-type]
        tracker=tracker,
        state=RadarState(),
        events=None,  # type: ignore[arg-type]
        curves=None,  # type: ignore[arg-type]
        chain=chain,
        sources=SourcesState(),
    )


async def test_reconcile_reads_the_derived_pda_never_the_stored_sol_vault(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(collect, "role_session", _no_role)
    tracker = MintTracker(window_minutes=1440, cap=120)
    tracker.observe(
        TrackedMint(
            mint=MINT,
            first_seen_at=T0,
            created_at=T0,
            bonding_curve=SOL_VAULT,  # the contaminated column, as loaded from the DB
            mcap_sol=Decimal("28"),
        )
    )
    chain = FakeChain()
    read = await collect.reconcile_once(_context(chain, tracker))
    assert read == 1
    assert chain.asked == [(MINT, bonding_curve_address(MINT))]


async def test_reconcile_still_works_for_a_mint_never_seen_with_a_bonding_curve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Before T4.39 this mint was skipped outright (``tracked.bonding_curve is
    None``); the PDA needs only the mint, so there is nothing left to skip for."""
    monkeypatch.setattr(collect, "role_session", _no_role)
    tracker = MintTracker(window_minutes=1440, cap=120)
    tracker.observe(TrackedMint(mint=MINT, first_seen_at=T0, mcap_sol=Decimal("28")))
    chain = FakeChain()
    read = await collect.reconcile_once(_context(chain, tracker))
    assert read == 1
    assert chain.asked == [(MINT, bonding_curve_address(MINT))]
