"""T4.74-3 — one brake for every lane (design §3): the positions the wallet
checks see are the memes **and** the launch lane **and** the spot desk.

``brake_positions`` is what ``admission_context``/``launch_entries``/
``heartbeat`` call instead of ``open_positions`` (T4.74-5 wires the one-line
swap): a spot position becomes the executor's own :class:`OpenPosition` with
``params.lane = "spot"`` and ``proposal_id = signal_id``, so ``wallet_from``
already counts it in the global open cap, the daily cap (committed SOL) and the
equity — without a second code path. The spot rows are always read: a position
that exists is money on the chain, whatever ``SPOT1_ENABLED`` reads today.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from hunter_meme_executor.repo import OpenPosition, PendingAttempt, open_positions
from hunter_meme_executor.spot_repo import (
    SpotPosition,
    open_spot_positions,
    pending_spot_markets,
)
from hunter_risk_meme.spot_profile import SPOT_LANE

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["as_brake_position", "brake_positions", "spot_pending_intents"]

LAMPORTS = Decimal(1_000_000_000)


def as_brake_position(p: SpotPosition) -> OpenPosition:
    """The desk's row in the wallet's shape; ``migrated`` is meaningless for a
    Jupiter-routed token and reads ``False`` (never a curve)."""
    return OpenPosition(
        id=p.id,
        proposal_id=p.signal_id,
        mint=p.mint,
        entry_at=p.entry_at,
        tokens=p.tokens,
        sol_spent_lamports=p.sol_spent_lamports,
        initial_risk_sol=p.initial_risk_sol,
        params={**p.params, "lane": SPOT_LANE, "market_symbol": p.market_symbol},
        mark_sol=p.mark_sol,
        high_water_sol=p.high_water_sol,
        exit_intent=p.exit_intent,
        sell_requested_at=p.sell_requested_at,
        sell_requested_by=p.sell_requested_by,
        migrated=False,
    )


async def brake_positions(session: AsyncSession) -> list[OpenPosition]:
    """Memes + launch (``meme_live_positions``, every lane) + spot, in one list."""
    memes = await open_positions(session)
    spots = await open_spot_positions(session)
    return [*memes, *(as_brake_position(p) for p in spots)]


async def spot_pending_intents(session: AsyncSession) -> list[PendingAttempt]:
    """Spot buys in flight as the engine's pending intents (``lane = spot``)."""
    return [
        PendingAttempt(p.signal_id, p.mint, p.reserved_sol, lane=SPOT_LANE)
        for p in await pending_spot_markets(session)
    ]
