"""The written small-test scope as a counter (``docs/RISK_ENGINE_MEME.md`` §12,
variant; ``docs/ACTIVATION.md`` §9b item 2).

``small_test_authorization.scope`` has three numbers. ``max_sol_per_trade`` is a
ceiling the boot folds into the policy (``config._limits``: ``min`` with the
owner's ``MEME_*``). The other two are **counters** the executor keeps against
its own ledger, never in memory: ``max_trades`` against the buys reserved or
sent (T4.14; since T4.96 ``admitted``/``simulated`` too — a buy in flight holds
its slot) and — since T4.28 — ``max_total_sol`` against the SOL those buys take
from the wallet (the chain's delta on a confirmed fill; the worst-case debit
``scope_reserve_sol`` while one is in flight). Either reached ⇒
``small_test_scope_exhausted``; short of it, the requested size is **clamped**
so the last buy of the scope never overshoots the number the owner wrote.

T4.96 (diary 2026-09-26): the clamp covers the **whole** debit, not only
``sol_final``. A buy takes ``curve + curve fees`` (bounded on chain by the
instruction's ``max_sol_cost = ceil(total × (1 + bps))``) plus the network fee,
the priority fee (``ceil(CU × price / 10⁶)``) and the ATA rent. In lamports:
``B = floor((floor(remaining) − ceil(reserve)) × 10⁴ / (10⁴ + bps))`` gives
``ceil(B × (10⁴ + bps) / 10⁴) + reserve ≤ remaining``. Outside the margin, by
design: the one-time ``user_volume_accumulator`` rent (1 346 200 lamports, paid
once per wallet, R43) and third-party router cuts (a path we never build).
A remainder the profile's floor cannot use is ``small_test_below_min`` — per
profile (the launch floor is lower, ``profile.launch_floor``), never global.
And the scope is **claimed** under one advisory lock in the transaction that
writes the ``admitted`` row, so the two lanes (separate tasks) cannot both
spend the same remainder (:func:`claim_scope`).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_risk_meme.profile import launch_floor

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_core.execution.meme.gates import SmallTestAuthorization
    from hunter_meme_executor.config import ExecutorConfig
    from hunter_meme_executor.context import ExecutorContext
    from hunter_meme_executor.priority_fee import PriorityFeeChoice

# fmt: off
__all__ = [
    "SMALL_TEST_BELOW_MIN", "SMALL_TEST_SCOPE_EXHAUSTED", "ScopeClaimRefused", "ScopeUse",
    "below_min_profiles", "buy_reserve_sol", "claim_scope", "lane_scope", "legacy_extra_sol",
    "read_scope_use", "requested_sol_of", "scope_refusal", "scope_use",
]
# fmt: on

SMALL_TEST_SCOPE_EXHAUSTED: Final = "small_test_scope_exhausted"
SMALL_TEST_BELOW_MIN: Final = "small_test_below_min"
"""T4.96: the remainder is above zero but below this profile's minimum ticket."""
SCOPE_LOCK: Final = (0x4D454D45, 1)
"""``pg_advisory_xact_lock`` (namespace "MEME", key 1): the small-test scope."""

_ZERO = Decimal(0)
_LAMPORTS = Decimal(1_000_000_000)
_BPS = 10_000


def _lamports_down(sol: Decimal) -> int:
    return int((sol * _LAMPORTS).to_integral_value(rounding=ROUND_FLOOR))


def _lamports_up(sol: Decimal) -> int:
    return int((sol * _LAMPORTS).to_integral_value(rounding=ROUND_CEILING))


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


def buy_reserve_sol(cfg: ExecutorConfig, fee: PriorityFeeChoice, *, creates_ata: bool) -> Decimal:
    """What a buy takes besides the curve leg: the network fee, the priority fee
    as Solana charges it (``ceil``) and the ATA rent when the buy creates it —
    the same inputs the admission's fixed costs use (``sizing.fixed_costs``)."""
    limits = cfg.limits
    priority = -(-cfg.compute_unit_limit * fee.micro_lamports // 1_000_000)
    rent = limits.ata_rent_sol if creates_ata else _ZERO
    return limits.network_fee_sol + Decimal(priority) / _LAMPORTS + rent


def legacy_extra_sol(cfg: ExecutorConfig) -> Decimal:
    """An in-flight row written before T4.96 carries only ``max_sol_cost_sol``:
    it is charged the reserve's upper bound (network + rent + the priority cap)."""
    return cfg.limits.network_fee_sol + cfg.limits.ata_rent_sol + cfg.send.priority_fee_max_sol


_USED = text(
    "SELECT count(*) AS trades, "
    "  coalesce(sum(coalesce((fill->>'buy_total_lamports')::numeric / 1000000000, "
    "                        (intent->>'scope_reserve_sol')::numeric, "
    "                        (intent->>'max_sol_cost_sol')::numeric + :legacy_extra, 0)), 0) "
    "  AS used_sol "
    "FROM meme_live_orders WHERE side = 'buy' "
    "  AND status IN ('admitted', 'simulated', 'submitted_unconfirmed', 'confirmed')"
)
"""One read for both counters: every buy reserved or sent (a stuck ``admitted``
row keeps its reservation, as the wallet brake's ``pending_attempts`` does) and
what it cost — the fill's real wallet delta once confirmed, the worst-case
debit while in flight."""
_LOCK = text("SELECT pg_advisory_xact_lock(:namespace, :key)")


@dataclass(frozen=True, slots=True)
class ScopeUse:
    max_trades: int
    trades_done: int
    max_total_sol: Decimal
    used_sol: Decimal
    requested_sol: Decimal
    debit_reserve_sol: Decimal = _ZERO
    """T4.96: network + priority + rent of *this* buy (zero = a lower bound)."""
    buy_slippage_bps: int = 0
    """T4.96: the instruction's tolerance on the curve leg (``max_sol_cost``)."""

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
    def usable_sol(self) -> Decimal:
        """The largest ``sol_final`` whose worst-case debit fits what is left."""
        room = _lamports_down(self.remaining_sol) - _lamports_up(self.debit_reserve_sol)
        if room <= 0:
            return _ZERO
        return Decimal(room * _BPS // (_BPS + self.buy_slippage_bps)) / _LAMPORTS

    @property
    def requested_cap_sol(self) -> Decimal:
        """The size the admission is asked for: never more than what is usable."""
        return min(self.requested_sol, self.usable_sol)

    @property
    def requested_clamped(self) -> bool:
        return self.requested_cap_sol < self.requested_sol

    def for_buy(self, reserve_sol: Decimal, slippage_bps: int) -> ScopeUse:
        return replace(self, debit_reserve_sol=reserve_sol, buy_slippage_bps=slippage_bps)

    def as_json(self) -> dict[str, Any]:
        return {
            "max_trades": self.max_trades,
            "trades_done": self.trades_done,
            "max_total_sol": str(self.max_total_sol),
            "used_sol": str(self.used_sol),
            "remaining_sol": str(self.remaining_sol),
            "debit_reserve_sol": str(self.debit_reserve_sol),
            "buy_slippage_bps": self.buy_slippage_bps,
            "usable_sol": str(self.usable_sol),
            "requested_sol": str(self.requested_sol),
            "requested_cap_sol": str(self.requested_cap_sol),
            "requested_clamped": self.requested_clamped,
            "exhausted": self.exhausted,
        }


def scope_refusal(scope: ScopeUse | None, floor: Decimal) -> tuple[str, dict[str, Any]] | None:
    """The named refusal of a lane whose floor is ``floor``, with the scope as
    evidence; ``None`` without a written scope or when a buy still fits."""
    if scope is None:
        return None
    if scope.exhausted is not None:
        return SMALL_TEST_SCOPE_EXHAUSTED, scope.as_json()
    if scope.usable_sol < floor:
        return SMALL_TEST_BELOW_MIN, scope.as_json()
    return None


def below_min_profiles(scope: ScopeUse, cfg: ExecutorConfig) -> list[str]:
    """The profiles whose floor the remainder **certainly** cannot pay — with a
    lower bound of the reserve (the network fee; + the rent on the launch lane,
    which always creates the ATA), so a name here means the admission refuses.
    Empty when exhausted (that state has its own name) or when a buy fits."""
    if scope.exhausted is not None:
        return []
    limits, out = cfg.limits, list[str]()
    full = scope.for_buy(limits.network_fee_sol, cfg.send.buy_slippage_bps())
    if full.usable_sol < limits.min_trade_sol:
        out.append("full")
    if cfg.launch.enabled:
        reserve = limits.network_fee_sol + limits.ata_rent_sol
        launch = scope.for_buy(reserve, cfg.launch.buy_slippage_bps())
        if launch.usable_sol < launch_floor(limits, cfg.launch.profile(limits)):
            out.append("launch")
    return out


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
    session: AsyncSession,
    small_test: SmallTestAuthorization,
    *,
    requested_sol: Decimal,
    legacy_extra: Decimal,
) -> ScopeUse:
    row = (await session.execute(_USED, {"legacy_extra": legacy_extra})).mappings().one()
    return scope_use(
        small_test,
        trades_done=int(row["trades"] or 0),
        used_sol=Decimal(str(row["used_sol"] or 0)),
        requested_sol=requested_sol,
    )


def _small_test(ctx: ExecutorContext) -> SmallTestAuthorization | None:
    return ctx.mode.gates.small_test if ctx.mode.gates is not None else None


async def lane_scope(ctx: ExecutorContext, *, requested_sol: Decimal) -> ScopeUse | None:
    """The scope as a lane reads it before the chain reads; ``None`` without one."""
    small = _small_test(ctx)
    if small is None:
        return None
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        return await read_scope_use(
            session, small, requested_sol=requested_sol, legacy_extra=legacy_extra_sol(ctx.config)
        )


class ScopeClaimRefused(Exception):
    """Raised inside the insert's transaction (it rolls back: nothing is written)."""

    def __init__(self, reason: str, detail: dict[str, Any]) -> None:
        super().__init__(reason)
        self.reason, self.detail = reason, detail


async def claim_scope(session: AsyncSession, ctx: ExecutorContext, *, debit_sol: Decimal) -> None:
    """Inside the transaction that writes the ``admitted`` row: take the scope's
    lock, re-read both counters and raise :class:`ScopeClaimRefused` if this
    buy's worst-case debit no longer fits (another lane spent the remainder
    meanwhile). The lock is held until that transaction commits, so the next
    reader sees this reservation. No written scope: nothing to claim."""
    small = _small_test(ctx)
    if small is None:
        return
    namespace, key = SCOPE_LOCK
    await session.execute(_LOCK, {"namespace": namespace, "key": key})
    use = await read_scope_use(
        session, small, requested_sol=debit_sol, legacy_extra=legacy_extra_sol(ctx.config)
    )
    if use.exhausted is not None or debit_sol > use.remaining_sol:
        detail = {**use.as_json(), "claimed_debit_sol": str(debit_sol)}
        raise ScopeClaimRefused(SMALL_TEST_SCOPE_EXHAUSTED, detail)
