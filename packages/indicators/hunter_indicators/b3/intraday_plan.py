"""The trade-plan contract of the WIN intraday family (H-039, H-040, H-041).

Its own contract for the same reason as H-038's :class:`~hunter_indicators.b3.contract.Signal`
(plan ``docs/plans/MERCADO-TRADICIONAL.md`` §1.6): the Lab's ``Decision`` is LONG-only and
demands a target. A :class:`TradePlan` is what a rule decides at ``decided_at`` (the end of
the decision bar): side, stop (an absolute level known at the decision **or** a fraction of
the entry fill), an optional target in multiples of the initial risk, and a time exit. The
fill itself belongs to whoever executes or simulates it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import MappingProxyType

from hunter_indicators.b3.contract import Side, utc


@dataclass(frozen=True, slots=True)
class IntradayWindow:
    """One session as the rules see it: O (cash-market open) and the time exit, in UTC."""

    trading_date: date
    open_at: datetime
    exit_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "open_at", utc(self.open_at, "open_at"))
        object.__setattr__(self, "exit_at", utc(self.exit_at, "exit_at"))
        if not self.open_at < self.exit_at:
            raise ValueError("need open_at < exit_at")


@dataclass(frozen=True, slots=True)
class NoPlan:
    """A session with no trade for a rule, and why — every reason is a funnel line."""

    trading_date: date
    reason: str


def _fmt(value: Decimal | None) -> str:
    return "-" if value is None else format(value, "f")


@dataclass(frozen=True, slots=True)
class TradePlan:
    strategy: str
    trading_date: date
    side: Side
    decided_at: datetime
    exit_at: datetime
    stop_level: Decimal | None
    stop_fraction: Decimal | None
    target_r: Decimal | None
    reason: str
    supporting_features: Mapping[str, str] = field(default_factory=dict[str, str])
    invalidations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "decided_at", utc(self.decided_at, "decided_at"))
        object.__setattr__(self, "exit_at", utc(self.exit_at, "exit_at"))
        if (self.stop_level is None) == (self.stop_fraction is None):
            raise ValueError("a plan needs exactly one of stop_level and stop_fraction")
        if not self.decided_at < self.exit_at:
            raise ValueError("need decided_at < exit_at")
        if self.target_r is not None and self.target_r <= 0:
            raise ValueError("target_r must be positive")
        object.__setattr__(
            self, "supporting_features", MappingProxyType(dict(self.supporting_features))
        )

    @property
    def expected_holding(self) -> timedelta:
        return self.exit_at - self.decided_at

    def identity(self) -> str:
        """Everything that decides the trade — one line per plan in the sha256 freeze."""
        return "|".join(
            (
                self.strategy,
                self.trading_date.isoformat(),
                self.side.value,
                self.decided_at.isoformat(),
                self.exit_at.isoformat(),
                f"stop={_fmt(self.stop_level)}",
                f"frac={_fmt(self.stop_fraction)}",
                f"target_r={_fmt(self.target_r)}",
            )
        )
