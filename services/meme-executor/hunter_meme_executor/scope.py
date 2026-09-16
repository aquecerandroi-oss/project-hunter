"""The written small-test scope as a counter (``docs/RISK_ENGINE_MEME.md`` §12,
variant; ``docs/ACTIVATION.md`` §9b item 2).

``small_test_authorization.scope`` has three numbers. ``max_sol_per_trade`` is a
ceiling the boot folds into the policy (``config._limits``: ``min`` with the
owner's ``MEME_*``). The other two are **counters** the executor keeps against
its own ledger, never in memory: ``max_trades`` against the buys sent
(``submitted_unconfirmed`` + ``confirmed``, T4.14) and — since T4.28 —
``max_total_sol`` against the SOL those buys took from the wallet (the chain's
delta on a confirmed fill; the ``max_sol_cost`` reservation while one is still
in flight). Either reached ⇒ ``small_test_scope_exhausted``; short of it, the
requested size is **clamped to what is left**, so the last buy of the scope
never overshoots the number the owner wrote.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_core.execution.meme.gates import SmallTestAuthorization

__all__ = ["ScopeUse", "read_scope_use", "requested_sol_of", "scope_use"]

_ZERO = Decimal(0)


def requested_sol_of(decision: Mapping[str, Any]) -> Decimal:
    """``decision.size_sol`` as a Decimal; unreadable or absent is **zero** (the
    engine then refuses ``below_min_sol`` — a bad row never takes the loop down)."""
    raw: Any = decision.get("size_sol")
    if raw is None or isinstance(raw, bool):
        return _ZERO
    try:
        value = Decimal(str(raw))
    except InvalidOperation:
        return _ZERO
    return value if value.is_finite() and value > 0 else _ZERO


_USED = text(
    "SELECT count(*) AS trades, "
    "  coalesce(sum(coalesce((fill->>'buy_total_lamports')::numeric / 1000000000, "
    "                        (intent->>'max_sol_cost_sol')::numeric, 0)), 0) AS used_sol "
    "FROM meme_live_orders WHERE side = 'buy' "
    "  AND status IN ('submitted_unconfirmed', 'confirmed')"
)
"""One read for both counters: the buys that reached the chain (a signature was
sent, whether or not the fill is known yet) and what they cost — the fill's
real wallet delta once confirmed, the reservation while unconfirmed."""


@dataclass(frozen=True, slots=True)
class ScopeUse:
    max_trades: int
    trades_done: int
    max_total_sol: Decimal
    used_sol: Decimal
    requested_sol: Decimal

    @property
    def remaining_sol(self) -> Decimal:
        return max(_ZERO, self.max_total_sol - self.used_sol)

    @property
    def exhausted(self) -> str | None:
        """Which counter closed the tap, or ``None``."""
        if self.trades_done >= self.max_trades:
            return "max_trades"
        if self.remaining_sol <= _ZERO:
            return "max_total_sol"
        return None

    @property
    def requested_cap_sol(self) -> Decimal:
        """The size the admission is asked for: never more than what is left."""
        return min(self.requested_sol, self.remaining_sol)

    @property
    def requested_clamped(self) -> bool:
        return self.requested_cap_sol < self.requested_sol

    def as_json(self) -> dict[str, Any]:
        return {
            "max_trades": self.max_trades,
            "trades_done": self.trades_done,
            "max_total_sol": str(self.max_total_sol),
            "used_sol": str(self.used_sol),
            "remaining_sol": str(self.remaining_sol),
            "requested_sol": str(self.requested_sol),
            "requested_cap_sol": str(self.requested_cap_sol),
            "requested_clamped": self.requested_clamped,
            "exhausted": self.exhausted,
        }


def scope_use(
    small_test: SmallTestAuthorization,
    *,
    trades_done: int,
    used_sol: Decimal,
    requested_sol: Decimal,
) -> ScopeUse:
    return ScopeUse(
        max_trades=small_test.max_trades,
        trades_done=trades_done,
        max_total_sol=small_test.max_total_sol,
        used_sol=used_sol,
        requested_sol=requested_sol,
    )


async def read_scope_use(
    session: AsyncSession, small_test: SmallTestAuthorization, *, requested_sol: Decimal
) -> ScopeUse:
    row = (await session.execute(_USED)).mappings().one()
    return scope_use(
        small_test,
        trades_done=int(row["trades"] or 0),
        used_sol=Decimal(str(row["used_sol"] or 0)),
        requested_sol=requested_sol,
    )
