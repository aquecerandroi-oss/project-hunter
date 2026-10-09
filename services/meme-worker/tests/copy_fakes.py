"""Labeled test doubles of the copy lane: a clock that sleeping advances, and a chain whose curve
changes on a schedule — so a test can show the paper fill is priced at the state **after** the
declared latency, not at the one the decision saw. Nothing here ships."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from hunter_exchanges.pumpfun.models import NormalizedCurveState
from hunter_exchanges.pumpfun.rpc_curves import CurveBatch

from .copy_support import T0


class FakeClock:
    def __init__(self, now: datetime = T0) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)

    def advance(self, **kwargs: float) -> None:
        self.now += timedelta(**kwargs)


@dataclass
class Curve:
    vsol: str = "30"
    vtok: str = "1073000000"
    real_sol: str = "0.5"
    complete: bool = False
    mayhem: bool = False


@dataclass
class FakeChain:
    clock: FakeClock
    schedule: dict[str, list[tuple[datetime, Curve | None]]] = field(
        default_factory=lambda: dict[str, list[tuple[datetime, Curve | None]]]()
    )
    calls: int = 0
    slot_override: dict[str, int] = field(default_factory=lambda: dict[str, int]())
    """A slot to serve for a mint instead of the clock-driven one (a read that is too early)."""

    def set(self, mint: str, curve: Curve | None, *, at: datetime | None = None) -> None:
        self.schedule.setdefault(mint, []).append((at or self.clock.now, curve))
        self.schedule[mint].sort(key=lambda pair: pair[0])

    def _current(self, mint: str) -> Curve | None:
        current: Curve | None = None
        for at, curve in self.schedule.get(mint, ()):
            if at <= self.clock.now:
                current = curve
        return current

    async def get_curve_states(
        self, mints: list[str], *, with_block_time: bool = True, commitment: str = "finalized"
    ) -> CurveBatch:
        self.calls += 1
        batch = CurveBatch()
        for mint in mints:
            curve = self._current(mint)
            if curve is None:
                continue
            batch.states[mint] = NormalizedCurveState(
                mint=mint,
                virtual_sol_reserves=Decimal(curve.vsol),
                virtual_token_reserves=Decimal(curve.vtok),
                real_sol_reserves=Decimal(curve.real_sol),
                real_token_reserves=Decimal("700000000"),
                total_supply=Decimal("1000000000"),
                complete=curve.complete,
                market_cap_sol=Decimal("30"),
                source="solana_rpc",
                mayhem_enabled=curve.mayhem,
                slot=self.slot_override.get(
                    mint, 1_000_000_000 + int((self.clock.now - T0).total_seconds() * 4)
                ),
                observed_at=self.clock.now,
                received_at=self.clock.now,
            )
        return batch
