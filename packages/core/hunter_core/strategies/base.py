"""The pure decision layer: ``StrategyContext``, ``Decision`` and the ``Strategy`` protocol.

``docs/ARCHITECTURE.md`` §6 and SHADOW-LAB.md "Desenho": ``evaluate`` is a pure
function — no IO, no clock, no Redis, no Postgres. Everything it may look at is
in the context, and the context is **cut at** ``source_bar_close``: it holds only
final 1-minute candles that had already closed at that instant, so a candle that
arrives later (or a candle still forming) cannot change a decision already taken.
That is the anti-look-ahead guarantee, enforced by the type rather than by
discipline.

Two ways in, on purpose:

- :class:`StrategyContext` is **strict** — it states the invariant and refuses
  anything that breaks it, so a worker bug surfaces as an error instead of a
  quietly biased backtest;
- :func:`build_context` is the **filter** the worker (and the tests) use: it
  drops non-final candles and everything at or after the cut, then sorts. The
  invariance tests feed it a polluted series and get the same decision.

Why ``evaluate`` returns ``Decision | None`` *and* ``explain`` returns an
:class:`Evaluation`: the brief keeps ``evaluate`` as the contract with the
worker, and the reason a bar produced nothing ("warmup", "gap", "rvol_low", ...)
goes to the worker's evaluation log — never into the signal envelope, which only
exists when there is a signal.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from hunter_core.domain.enums import Timeframe, TradeDirection
from hunter_core.domain.market import NormalizedCandle, NormalizedFunding, NormalizedOpenInterest
from hunter_core.domain.types import ensure_utc, to_money
from hunter_core.strategies.canonical import canonical_json
from hunter_core.strategies.envelope import (
    PURPOSE_RESEARCH_ONLY,
    AssumedCosts,
    SupportingFeatures,
)

__all__ = [
    "PURPOSE_RESEARCH_ONLY",
    "AssumedCosts",
    "Decision",
    "Evaluation",
    "EvaluationState",
    "Invalidation",
    "Strategy",
    "StrategyContext",
    "build_context",
    "canonical_number",
    "param_decimal",
    "param_int",
]

_ONE_MINUTE = timedelta(minutes=1)


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class EvaluationState(StrEnum):
    """Why an evaluation produced (or did not produce) a decision.

    The worker cannot collapse this to ``decision is None``: SHADOW-LAB.md §4
    re-arms a market only after the previous tracking has ended *and* a later bar
    shows the entry condition **observably false**, and a bar it could not
    evaluate (gap, warm-up, ineligible market) proves nothing either way.
    :data:`NOT_TRIGGERED` is the only state that constitutes that proof; the
    re-arm transition itself is the worker's state machine, not this enum
    (Astra, S1 design review, must-fix 5 and diff review).
    """

    TRIGGERED = "triggered"
    """A decision was produced."""
    NOT_TRIGGERED = "not_triggered"
    """Every required input was available and the entry condition was false."""
    REJECTED = "rejected"
    """The entry condition held but the decision was refused (e.g. geometry).
    Not a false condition: it must not re-arm the market."""
    UNAVAILABLE = "unavailable"
    """Warm-up, gap or an indicator that could not be computed."""
    INELIGIBLE = "ineligible"
    """The market was not in the eligible universe at ``source_bar_close``."""


class Invalidation(_Frozen):
    """A condition that kills the setup at a bar close, independently of the stop.

    ``close_below`` is evaluated by the worker on closed bars of ``timeframe``
    (SHADOW-LAB.md §3: an invalidation observed at a close exits at the next
    eligible open).
    """

    kind: Literal["close_below"]
    level: Decimal
    timeframe: str


class StrategyContext(_Frozen):
    """Everything a strategy may look at, as of ``source_bar_close``."""

    exchange: str
    symbol: str
    """The market this context belongs to. Every candle and every derivative
    observation must carry the same pair: a query that mixed two symbols would
    otherwise pass the "strictly increasing, no gaps" checks and aggregate two
    assets into one bar (Astra, S1 design review, must-fix 4)."""
    source_bar_close: datetime
    """Close of the reference bar. The cut: nothing observed at or after it."""
    candles_1m: tuple[NormalizedCandle, ...] = ()
    """Final 1m candles, strictly increasing by ``open_time``. Gaps are allowed
    and are *declared* by their absence — the aggregator turns them into an
    unavailable window with a reason instead of a shorter one."""
    funding: NormalizedFunding | None = None
    open_interest: NormalizedOpenInterest | None = None
    eligible: bool = True
    eligibility_reason: str | None = None

    @field_validator("source_bar_close", mode="after")
    @classmethod
    def _cut_is_utc(cls, v: datetime) -> datetime:
        return ensure_utc(v)

    @model_validator(mode="after")
    def _check_invariants(self) -> StrategyContext:
        previous: datetime | None = None
        for candle in self.candles_1m:
            if candle.exchange != self.exchange or candle.symbol != self.symbol:
                raise ValueError(
                    f"candle {candle.exchange}:{candle.symbol} does not belong to "
                    f"{self.exchange}:{self.symbol}"
                )
            if candle.timeframe is not Timeframe.M1:
                raise ValueError(f"candles_1m must be 1m candles, got {candle.timeframe}")
            if candle.close_time - candle.open_time != _ONE_MINUTE:
                raise ValueError(f"candle {candle.open_time} does not span exactly one minute")
            if not candle.is_final:
                raise ValueError(f"candles_1m must be final; {candle.open_time} is_final=False")
            if previous is not None and candle.open_time <= previous:
                raise ValueError("candles_1m must be strictly increasing by open_time")
            if candle.close_time > self.source_bar_close:
                raise ValueError(
                    f"candle {candle.open_time} closes after source_bar_close "
                    f"{self.source_bar_close}: the context must be cut at the reference bar"
                )
            previous = candle.open_time
        for name, observation in (("funding", self.funding), ("open_interest", self.open_interest)):
            if observation is None:
                continue
            if observation.ts > self.source_bar_close:
                raise ValueError(f"{name} observed after source_bar_close")
            if observation.exchange != self.exchange or observation.symbol != self.symbol:
                raise ValueError(f"{name} does not belong to {self.exchange}:{self.symbol}")
        return self


def build_context(
    candles: Iterable[NormalizedCandle],
    *,
    exchange: str,
    symbol: str,
    source_bar_close: datetime,
    funding: NormalizedFunding | None = None,
    open_interest: NormalizedOpenInterest | None = None,
    eligible: bool = True,
    eligibility_reason: str | None = None,
) -> StrategyContext:
    """Cut, filter and sort ``candles`` into a :class:`StrategyContext`.

    Drops every non-final candle and everything closing after ``source_bar_close``
    (including the minute still forming), and ignores derivatives observed after
    the cut. Feeding it future or partial data therefore cannot move a decision.

    It does **not** repair data: duplicated ``open_time``s, a foreign symbol or a
    candle that is not one minute long still reach the strict constructor and
    raise, because silently de-duplicating would hide a market-worker bug.
    """
    cut = ensure_utc(source_bar_close)
    kept = sorted(
        (c for c in candles if c.is_final and c.close_time <= cut),
        key=lambda candle: candle.open_time,
    )
    return StrategyContext(
        exchange=exchange,
        symbol=symbol,
        source_bar_close=cut,
        candles_1m=tuple(kept),
        funding=funding if funding is not None and funding.ts <= cut else None,
        open_interest=(
            open_interest if open_interest is not None and open_interest.ts <= cut else None
        ),
        eligible=eligible,
        eligibility_reason=eligibility_reason,
    )


class Decision(_Frozen):
    """A shadow decision: what the strategy would do, with the evidence attached.

    ``decision_at`` and ``cohort`` are absent by design — they belong to the run
    that persists this, not to the observation (SHADOW-LAB.md §2).
    """

    direction: Literal[TradeDirection.LONG]
    """LONG only in v0 (SHADOW-LAB.md §10)."""
    reference_price: Decimal = Field(gt=0)
    """Close of the reference bar. Not an entry price: the entry is the open of a
    later 1m bar, and 1.5 ATR each side of *this* price is "1 R nominal at the
    reference", never 1 R guaranteed at the entry (SHADOW-LAB.md §3)."""
    stop: Decimal = Field(gt=0)
    target1: Decimal = Field(gt=0)
    targets_informational: tuple[Decimal, ...] = ()
    """Further targets kept for the snapshot only; the outcome model uses ``target1``."""
    invalidations: tuple[Invalidation, ...] = ()
    horizon_s: int = Field(gt=0)
    confidence: Decimal = Field(ge=0, le=1)
    reason: str
    supporting_features: SupportingFeatures

    @model_validator(mode="after")
    def _check_geometry(self) -> Decision:
        if not self.stop < self.reference_price < self.target1:
            raise ValueError(
                "stop < reference_price < target1 is required "
                f"(got {self.stop}, {self.reference_price}, {self.target1})"
            )
        return self


@dataclass(frozen=True, slots=True)
class Evaluation:
    """The full result of one evaluation: the decision, or why there is none.

    ``state`` is what the worker branches on (re-arm, retry, alert); ``reason``
    is the diagnostic code (``"signal"``, ``"warmup"``, ``"gap"``, ``"rvol_low"``,
    ...) and ``detail`` is small, already-stringified context for the evaluation
    log. None of it is persisted in the signal envelope: an envelope only exists
    when there is a signal.
    """

    decision: Decision | None
    state: EvaluationState
    reason: str
    detail: Mapping[str, str] = field(default_factory=lambda: {})

    def __post_init__(self) -> None:
        triggered = self.state is EvaluationState.TRIGGERED
        if triggered != (self.decision is not None):
            raise ValueError("state TRIGGERED and a decision must come together")


@runtime_checkable
class Strategy(Protocol):
    """A pure strategy — ``docs/ARCHITECTURE.md`` §6.

    The identity members are declared as read-only properties so that an
    implementation may satisfy them with a plain class attribute
    (``key: str = "momentum_v1"``) while nothing that only *reads* a strategy can
    rebind the key, the version or the timeframe of a frozen experiment.
    """

    @property
    def key(self) -> str: ...

    @property
    def version(self) -> str: ...

    @property
    def timeframe(self) -> Timeframe:
        """Only bars of this timeframe are evaluated for new entries (5m or 15m in v0)."""
        ...

    @property
    def parameters_schema(self) -> Mapping[str, Any]:
        """JSON Schema for ``default_parameters``; frozen with the version."""
        ...

    @property
    def default_parameters(self) -> Mapping[str, Any]:
        """Every threshold the strategy uses. Nothing is hardcoded in the code path."""
        ...

    def evaluate(self, ctx: StrategyContext, params: Mapping[str, Any]) -> Decision | None: ...

    def explain(self, ctx: StrategyContext, params: Mapping[str, Any]) -> Evaluation: ...


def param_decimal(params: Mapping[str, Any], key: str) -> Decimal:
    """A ``Decimal`` parameter, accepting the canonical string form from JSONB.

    ``float`` is refused (``to_money``): a threshold that went through binary
    floating point is not the threshold that was frozen.
    """
    return to_money(params[key])


def param_int(params: Mapping[str, Any], key: str) -> int:
    """An integer parameter (window lengths, seconds); refuses a fractional value."""
    value = params[key]
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise TypeError(f"{key} must be an integer, got {type(value).__name__}")
    try:
        as_decimal = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{key} is not an integer: {value!r}") from exc
    if as_decimal != as_decimal.to_integral_value():
        raise ValueError(f"{key} must be a whole number, got {value!r}")
    return int(as_decimal)


def assumed_costs(params: Mapping[str, Any]) -> AssumedCosts:
    """The declared cost hypothesis, read from the frozen parameters."""
    return AssumedCosts(
        spread_bps=param_decimal(params, "assumed_spread_bps"),
        slippage_bps=param_decimal(params, "slippage_bps"),
        fee_bps=param_decimal(params, "fee_bps"),
        max_entry_delay_s=param_int(params, "max_entry_delay_s"),
    )


def canonical_number(value: Decimal) -> str:
    """``value`` in the canonical ``params_format = 1`` spelling (``1.50`` -> ``1.5``).

    Used for the human-readable ``reason`` and for the evaluation log, so the
    same number is always written the same way.
    """
    rendered: str = json.loads(canonical_json(value))
    return rendered
