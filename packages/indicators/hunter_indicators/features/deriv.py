"""Derivative features: funding and open interest, current and changed.

The hot state holds only the **current** reading of each field
(``mkt:*:deriv``), so a "change over the last hour" needs a reference the
context was given (``deriv_history``, filled by the scanner from the durable
tables). Without a reference the feature is ``missing_input`` — never "change
since the first value this process happened to see", which after a restart is a
number about the process, not about the market (Astra, T2.2 design review, 1c).

The reference must also *land* on the lookback: the closest observation inside
``tolerance_minutes`` of ``as_of - lookback`` is used, and if none does the
feature is ``warmup``. A 30-minute-old reading is not a 1-hour change.

Open interest changes are **relative** (a fraction of the reference); funding
changes are an **absolute difference** — funding crosses zero, and a relative
change against a near-zero rate explodes without meaning anything.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import localcontext

from hunter_core.domain.enums import FeatureCategory
from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.features.context import (
    INPUT_DERIV_HISTORY,
    INPUT_FUNDING,
    INPUT_OI,
    DerivObservation,
    MarketContext,
)
from hunter_indicators.features.definitions import FeatureCalculator, FeatureDefinition
from hunter_indicators.features.state import FeatureState
from hunter_indicators.features.vector import FeatureValue, Reason

DEFAULT_TOLERANCE_MINUTES = 6


def _reference(
    history: Sequence[DerivObservation],
    target: datetime,
    tolerance: timedelta,
    field: str,
) -> DerivObservation | None:
    """The observation closest to ``target`` that carries ``field``, within tolerance."""
    candidates = [
        observation
        for observation in history
        if getattr(observation, field) is not None and abs(observation.ts - target) <= tolerance
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda o: abs(o.ts - target))


@dataclass(frozen=True, slots=True)
class FundingRate:
    """The current funding rate, as the exchange publishes it (a fraction)."""

    @property
    def definition(self) -> FeatureDefinition:
        return FeatureDefinition(
            key="funding_rate",
            version=1,
            category=FeatureCategory.DERIVATIVES,
            inputs=(INPUT_FUNDING,),
            params={"unit": "fraction"},
            description="current funding rate of the perpetual, as a fraction per interval",
        )

    def compute(self, ctx: MarketContext, state: FeatureState) -> FeatureValue:
        definition = self.definition
        snapshot = ctx.deriv.value
        if snapshot is None or snapshot.funding_rate is None:
            return FeatureValue.unavailable(
                definition.key, Reason.MISSING_INPUT, inputs=definition.inputs
            )
        return FeatureValue.ok(definition.key, snapshot.funding_rate, inputs=definition.inputs)


@dataclass(frozen=True, slots=True)
class OpenInterestChange:
    """``(oi_now - oi_ref) / oi_ref`` over ``hours``, as a fraction."""

    hours: int
    tolerance_minutes: int = DEFAULT_TOLERANCE_MINUTES

    @property
    def definition(self) -> FeatureDefinition:
        return FeatureDefinition(
            key=f"open_interest_change_{self.hours}h",
            version=1,
            category=FeatureCategory.DERIVATIVES,
            inputs=(INPUT_OI, INPUT_DERIV_HISTORY),
            params={"hours": self.hours, "tolerance_minutes": self.tolerance_minutes},
            description=(
                f"open interest against its reading {self.hours} h earlier "
                f"(+/- {self.tolerance_minutes} min), as a fraction"
            ),
        )

    def compute(self, ctx: MarketContext, state: FeatureState) -> FeatureValue:
        definition = self.definition
        snapshot = ctx.deriv.value
        history = ctx.deriv_history.value
        if snapshot is None or snapshot.open_interest is None or history is None:
            return FeatureValue.unavailable(
                definition.key, Reason.MISSING_INPUT, inputs=definition.inputs
            )
        reference = _reference(
            history,
            ctx.as_of - timedelta(hours=self.hours),
            timedelta(minutes=self.tolerance_minutes),
            "open_interest",
        )
        if reference is None:
            return FeatureValue.unavailable(definition.key, Reason.WARMUP, inputs=definition.inputs)
        previous = reference.open_interest
        if previous is None or previous <= 0:
            return FeatureValue.unavailable(
                definition.key, Reason.ZERO_DIVISOR, inputs=definition.inputs
            )
        with localcontext(CONTEXT):
            value = (snapshot.open_interest - previous) / previous
        return FeatureValue.ok(definition.key, value, inputs=definition.inputs)


@dataclass(frozen=True, slots=True)
class FundingChange:
    """``funding_now - funding_ref`` over ``hours`` — a difference, not a ratio."""

    hours: int = 8
    tolerance_minutes: int = 48

    @property
    def definition(self) -> FeatureDefinition:
        return FeatureDefinition(
            key=f"funding_change_{self.hours}h",
            version=1,
            category=FeatureCategory.DERIVATIVES,
            inputs=(INPUT_FUNDING, INPUT_DERIV_HISTORY),
            params={
                "hours": self.hours,
                "tolerance_minutes": self.tolerance_minutes,
                "operation": "difference",
            },
            description=(
                f"funding rate minus its reading {self.hours} h earlier "
                f"(+/- {self.tolerance_minutes} min), in rate points"
            ),
        )

    def compute(self, ctx: MarketContext, state: FeatureState) -> FeatureValue:
        definition = self.definition
        snapshot = ctx.deriv.value
        history = ctx.deriv_history.value
        if snapshot is None or snapshot.funding_rate is None or history is None:
            return FeatureValue.unavailable(
                definition.key, Reason.MISSING_INPUT, inputs=definition.inputs
            )
        reference = _reference(
            history,
            ctx.as_of - timedelta(hours=self.hours),
            timedelta(minutes=self.tolerance_minutes),
            "funding_rate",
        )
        if reference is None or reference.funding_rate is None:
            return FeatureValue.unavailable(definition.key, Reason.WARMUP, inputs=definition.inputs)
        with localcontext(CONTEXT):
            value = snapshot.funding_rate - reference.funding_rate
        return FeatureValue.ok(definition.key, value, inputs=definition.inputs)


def deriv_calculators() -> tuple[FeatureCalculator, ...]:
    """The frozen v1 derivatives set, ordered by key."""
    calculators: list[FeatureCalculator] = [
        FundingRate(),
        FundingChange(hours=8, tolerance_minutes=48),
        OpenInterestChange(hours=1, tolerance_minutes=6),
        OpenInterestChange(hours=4, tolerance_minutes=24),
    ]
    return tuple(sorted(calculators, key=lambda c: c.definition.key))


__all__ = [
    "DEFAULT_TOLERANCE_MINUTES",
    "FundingChange",
    "FundingRate",
    "OpenInterestChange",
    "deriv_calculators",
]
