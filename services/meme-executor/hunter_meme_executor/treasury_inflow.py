"""T4.60 — the daily-loss brake counts what the treasury put into the wallet.

Defect (18/09/2026 13:12 BRT): position YOU lost 0.0395 SOL (bought 0.0516,
sold 0.0121, trailing exit). At 13:12:06 the treasury (T4.54) swapped 5.75
USDC into 0.0516 SOL because the wallet had fallen below the floor. The next
heartbeat published ``daily_loss_sol = 0`` — ``equity_sol 0.732 >
day_start_sol_equity 0.686`` — because the brake was ``day_start - equity``,
blind to the USDC that had just refilled the wallet. With the treasury on,
``MEME_DAILY_LOSS_CAP_SOL`` could never trip: every loss was topped up.

The fix is one more input to the pure engine
(``MemeWalletState.treasury_inflow_today_sol``) and this module, which reads
it: the sum of ``sol_out_filled`` (``sol_out_quoted`` for a swap still
``submitted``) over ``meme_treasury_swaps`` with ``status in ('submitted',
'confirmed')`` and ``requested_at >= day_start_utc``. Then::

    daily_loss_sol = day_start_sol_equity + treasury_inflow_today_sol - equity_sol

Discipline (same as ``wallet_refresh.py`` and ``priority_fee.py``): one bounded
SELECT per kill-switch tick, cached ``cache_ttl_s`` (10 s), re-read at once
when the Sao Paulo day changes, and on a failed read the **last known** inflow
is kept — never zero, because zero is exactly the number that hid the loss.
Before any successful read the value is ``None``: the admission refuses by
name (``treasury_inflow_unavailable``) and the heartbeat publishes an empty
field, never a guess.

The day anchor rides here too (``ensure_anchor``, moved from ``entries.py``):
``day_start_sol_equity`` is written at the first admission of the day, which
may come hours after a top-up landed (a swap at 00:05, a candidate at 09:00).
Anchoring the raw equity would count that swap twice — once inside the
anchor, once as the day's inflow — and report a loss the desk never had; so
the anchor is ``equity_now - inflow_today``, the capital the day *started*
with. An anchor cannot be written while the inflow is unreadable: the
candidate is refused ``day_anchor_unavailable`` by ``entries.py`` as before.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.logging import get_logger
from hunter_meme_executor import treasury_db
from hunter_meme_executor.admission import day_start_utc
from hunter_meme_executor.journal_db import WORKER_ROLE

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_meme_executor.context import ExecutorContext
    from hunter_meme_executor.kill_switch import DayAnchor

__all__ = ["TreasuryInflowReader", "ensure_anchor", "treasury_inflow_once"]

logger = get_logger(__name__)
_ZERO = Decimal(0)


@dataclass(slots=True)
class TreasuryInflowReader:
    cache_ttl_s: float = 10.0
    inflow_sol: Decimal | None = None
    """The last **successful** reading; ``None`` until the first one."""
    read_at: datetime | None = None
    day_start_utc: datetime | None = None
    """The day the reading was taken for; a different day is a cache miss."""
    read_failures: int = 0
    last_error: str | None = None

    def cached(self, *, day_start_utc: datetime, now: datetime) -> bool:
        return (
            self.read_at is not None
            and self.day_start_utc == day_start_utc
            and (now - self.read_at).total_seconds() < self.cache_ttl_s
        )

    async def refresh(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        day_start_utc: datetime,
        now: datetime,
    ) -> Decimal | None:
        """The inflow since ``day_start_utc``: the cached value inside the TTL,
        one SELECT otherwise, and the last known value when the SELECT fails."""
        if self.cached(day_start_utc=day_start_utc, now=now):
            return self.inflow_sol
        try:
            async with role_session(session_factory, db_role=WORKER_ROLE) as session:
                value = await treasury_db.sol_inflow_since(session, since=day_start_utc)
        except Exception as exc:
            self.read_failures += 1
            self.last_error = type(exc).__name__
            logger.warning(
                "meme_treasury_inflow_read_failed",
                error_type=self.last_error,
                last_known=None if self.inflow_sol is None else str(self.inflow_sol),
            )
            return self.inflow_sol
        self.inflow_sol, self.read_at, self.day_start_utc = value, now, day_start_utc
        self.last_error = None
        return value

    def describe(self) -> dict[str, str]:
        """The reading's provenance (the value itself rides ``heartbeat.daily_loss_fields``)."""
        return {
            "treasury_inflow_read_at": "" if self.read_at is None else self.read_at.isoformat(),
            "treasury_inflow_read_failures": str(self.read_failures),
            "treasury_inflow_error": self.last_error or "",
        }


async def treasury_inflow_once(ctx: ExecutorContext, *, now: datetime) -> Decimal | None:
    """The kill-switch tick's read (after ``treasury_once``, so a swap that
    just landed is counted on the same tick)."""
    return await ctx.treasury_inflow.refresh(
        ctx.session_factory, day_start_utc=day_start_utc(now), now=now
    )


async def ensure_anchor(ctx: ExecutorContext, now: datetime, equity: Decimal) -> DayAnchor | None:
    """Persist today's Sao Paulo midnight equity once — **net of the inflow the
    treasury already added today** — and raise the peak when the equity grows.

    Returns **today's** anchor, or ``None`` when the inflow cannot be read
    (``ctx.kill.anchor`` is left as it was — ``None`` or yesterday's — and the
    caller refuses ``day_anchor_unavailable``; yesterday's anchor is never
    used for today's loss)."""
    start = day_start_utc(now)
    # Read (or hit the 10 s cache) on both branches: after a restart the anchor
    # row is already today's, and the admission still needs the inflow.
    inflow = await ctx.treasury_inflow.refresh(ctx.session_factory, day_start_utc=start, now=now)
    anchor = ctx.kill.anchor
    if anchor is not None and anchor.day_start_utc == start:
        await ctx.kill.raise_peak(equity)
        return ctx.kill.anchor
    if inflow is None:
        logger.warning("meme_day_anchor_deferred", reason="treasury_inflow_unavailable")
        return None
    return await ctx.kill.anchor_day(start, max(_ZERO, equity - inflow))
