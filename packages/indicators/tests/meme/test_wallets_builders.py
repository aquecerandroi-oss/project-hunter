"""Synthetic tape builders for the wallet-engine tests (fixtures, not data).

Every number here is invented for a test and labelled as such; nothing in this
module is a measurement. Times are UTC, amounts are integer lamports/atoms.

The default curve is the live launch point (30 SOL virtual against 1 073 M
virtual tokens) scaled to lamports/atoms, so a quote here is the quote a real
pump.fun curve of that shape would give.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from hunter_indicators.meme.wallets.tape import CreateEvent, Fill, Reserves, Side, Venue

T0 = datetime(2026, 10, 6, tzinfo=UTC)
"""A synthetic window start (00:00 UTC); the cut of 7 days later is ``T0 + 7d``."""
SOL = 1_000_000_000
TOKEN = 1_000_000
CURVE_SOL = 30 * SOL
CURVE_TOKENS = 1_073_000_000 * TOKEN
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
AMM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"


def at(seconds: float) -> datetime:
    """``T0 + seconds`` — test time is written as an offset."""
    return T0 + timedelta(seconds=seconds)


def curve(
    sol: int = CURVE_SOL,
    tokens: int = CURVE_TOKENS,
    *,
    real_sol: int | None = None,
    complete: bool = False,
) -> Reserves:
    """A curve state; the real SOL defaults to ``virtual − 30 SOL`` (a standard curve)."""
    real = max(sol - CURVE_SOL, 0) if real_sol is None else real_sol
    return Reserves(
        venue="curve",
        sol_lamports=sol,
        token_atoms=tokens,
        real_sol_lamports=real,
        complete=complete,
    )


def pool(sol: int, tokens: int, *, virtual: int = 0) -> Reserves:
    """A pool state: real quote ``sol``, base ``tokens`` and the signed virtual quote."""
    return Reserves(
        venue="pool",
        sol_lamports=sol,
        token_atoms=tokens,
        real_sol_lamports=None,
        virtual_quote_lamports=virtual,
    )


_SEQ = [0]


def fill(
    *,
    wallet: str,
    side: Side,
    slot: int,
    sol: int,
    atoms: int,
    mint: str = "MINT",
    t: float | None = None,
    received_delay: float = 0.5,
    fee: int = 0,
    fee_bps: int = 125,
    lp_fee: int = 0,
    reserves: Reserves | None = None,
    signature: str | None = None,
    ordinal: int = 0,
    venue: Venue | None = None,
) -> Fill:
    """One event; ``t`` defaults to ``slot × 0.4 s`` after ``T0``."""
    _SEQ[0] += 1
    block_time = at(slot * 0.4 if t is None else t).replace(microsecond=0)
    state = reserves if reserves is not None else curve()
    return Fill(
        signature=signature or f"sig{_SEQ[0]}",
        program=PUMP if state.venue == "curve" else AMM,
        event_ordinal=ordinal,
        slot=slot,
        block_time=block_time,
        received_at=block_time + timedelta(seconds=received_delay),
        wallet=wallet,
        mint=mint,
        venue=venue or state.venue,
        side=side,
        sol_lamports=sol,
        token_atoms=atoms,
        fee_lamports=fee,
        fee_bps=fee_bps,
        lp_fee_lamports=lp_fee,
        reserves=state,
    )


def create(mint: str, creator: str, slot: int) -> CreateEvent:
    block_time = at(slot * 0.4).replace(microsecond=0)
    return CreateEvent(
        mint=mint,
        creator=creator,
        slot=slot,
        block_time=block_time,
        received_at=block_time + timedelta(seconds=0.5),
    )
