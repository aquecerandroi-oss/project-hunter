"""The durable state of one hypothetical trade: :class:`Bar`, :class:`TrackingPlan`
and :class:`Progress`.

SHADOW-LAB.md "Decisão conjunta" §3/§4/§5. :class:`Progress` is persisted
verbatim in ``signal_outcomes.meta.progress`` and is the whole durable state of
one hypothetical trade: where the tracking is, what it entered at, how far it
has been folded, and the raw material the excursions are built from.

Split from :mod:`.walker` for the 350-line budget, and along the right seam:
this module is *state and its serialisation*, that one is the *rules* that
advance it. Three invariants live here rather than there:

- ``finished`` — ``terminal``, ``no_entry`` and ``censored`` never reopen;
- ``next_expected_open`` — the only 1m bar this tracking may consume next, which
  is what makes a redelivery a no-op and a hole a refusal;
- the JSON round trip — the level read back after a restart is the level that
  was written.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from hunter_core.domain.enums import OutcomeResult, ShadowTrackingState, Timeframe
from hunter_core.domain.types import ensure_utc, to_money
from hunter_core.strategies.envelope import AssumedCosts
from hunter_strategy_worker.excursions import build_excursions

MINUTE = timedelta(minutes=1)

__all__ = ["MINUTE", "Bar", "Progress", "TrackingPlan"]

_FINISHED = frozenset(
    {
        ShadowTrackingState.TERMINAL,
        ShadowTrackingState.NO_ENTRY,
        ShadowTrackingState.CENSORED,
    }
)


@dataclass(frozen=True, slots=True)
class Bar:
    """One final 1-minute candle. ``Decimal`` everywhere, UTC ``open_time``."""

    open_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal

    @property
    def close_time(self) -> datetime:
        return self.open_time + MINUTE


@dataclass(frozen=True, slots=True)
class TrackingPlan:
    """The frozen parameters of one tracking, all decided before the entry."""

    entry_bar_open: datetime
    stop: Decimal
    target1: Decimal
    horizon_s: int
    costs: AssumedCosts
    reference_price: Decimal | None = None
    invalidation_level: Decimal | None = None
    invalidation_timeframe: Timeframe | None = None

    @property
    def horizon_open(self) -> datetime:
        """The open at which the trade expires — ``entry_bar_open + horizon``."""
        return self.entry_bar_open + timedelta(seconds=self.horizon_s)


def _dec(value: Any) -> Decimal | None:
    return None if value is None else to_money(value)


def _ts(value: Any) -> datetime | None:
    return None if value is None else ensure_utc(datetime.fromisoformat(value))


@dataclass(frozen=True, slots=True)
class Progress:
    """Durable tracking progress — persisted as ``meta.progress``."""

    tracking_state: ShadowTrackingState
    result: OutcomeResult
    entry: Decimal | None = None
    entry_ts: datetime | None = None
    last_bar_open: datetime | None = None
    first_bar_open: datetime | None = None
    window_last_open: datetime | None = None
    bars_in_position: int = 0
    pending_invalidation: bool = False
    complete_high: Decimal | None = None
    complete_low: Decimal | None = None
    complete_high_ts: datetime | None = None
    complete_low_ts: datetime | None = None
    exit_base: Decimal | None = None
    """The synthetic exit price the trade is credited at."""
    exit_observed: Decimal | None = None
    """What the market printed at the exit instant. Equals ``exit_base`` except
    on a favourable gap, where the credit is capped at ``target1`` but the
    market really was higher."""
    exit_ts: datetime | None = None
    exit_at_open: bool = False
    exit_bar_open: datetime | None = None
    """Open of the bar the exit happened in — the window the exit instant is
    known to lie in, which is not the same as knowing the instant."""
    exit_bar_high: Decimal | None = None
    exit_bar_low: Decimal | None = None
    no_entry_reason: str | None = None
    censored_reason: str | None = None

    @classmethod
    def start(cls) -> Progress:
        """A tracking that has been decided and is waiting for its entry bar."""
        return cls(tracking_state=ShadowTrackingState.PENDING_ENTRY, result=OutcomeResult.OPEN)

    @property
    def finished(self) -> bool:
        """``terminal``, ``no_entry`` and ``censored`` never reopen."""
        return self.tracking_state in _FINISHED

    def next_expected_open(self, plan: TrackingPlan) -> datetime:
        """The only 1m bar this tracking may consume next."""
        if self.last_bar_open is None:
            return plan.entry_bar_open
        return self.last_bar_open + MINUTE

    def censor(self, reason: str) -> Progress:
        """A bar this outcome needed cannot be recovered — never ``expired``."""
        if self.finished:
            return self
        return replace(
            self,
            tracking_state=ShadowTrackingState.CENSORED,
            result=OutcomeResult.OPEN,
            censored_reason=reason[:64],
        )

    def excursions(self, plan: TrackingPlan) -> dict[str, Any]:
        """The honest MFE/MAE reading — see :mod:`.excursions`."""
        return build_excursions(self, plan)

    def to_jsonable(self) -> dict[str, Any]:
        """Canonical JSON: ``Decimal`` as normalised string, times ISO-8601 UTC."""
        return {
            "tracking_state": self.tracking_state.value,
            "result": self.result.value,
            "entry": _text(self.entry),
            "entry_ts": _iso(self.entry_ts),
            "last_bar_open": _iso(self.last_bar_open),
            "first_bar_open": _iso(self.first_bar_open),
            "window_last_open": _iso(self.window_last_open),
            "bars_in_position": self.bars_in_position,
            "pending_invalidation": self.pending_invalidation,
            "complete_high": _text(self.complete_high),
            "complete_low": _text(self.complete_low),
            "complete_high_ts": _iso(self.complete_high_ts),
            "complete_low_ts": _iso(self.complete_low_ts),
            "exit_base": _text(self.exit_base),
            "exit_observed": _text(self.exit_observed),
            "exit_bar_open": _iso(self.exit_bar_open),
            "exit_ts": _iso(self.exit_ts),
            "exit_at_open": self.exit_at_open,
            "exit_bar_high": _text(self.exit_bar_high),
            "exit_bar_low": _text(self.exit_bar_low),
            "no_entry_reason": self.no_entry_reason,
            "censored_reason": self.censored_reason,
        }

    @classmethod
    def from_jsonable(cls, data: dict[str, Any]) -> Progress:
        """Inverse of :meth:`to_jsonable` — the level read back is the level written."""
        return cls(
            tracking_state=ShadowTrackingState(data["tracking_state"]),
            result=OutcomeResult(data["result"]),
            entry=_dec(data["entry"]),
            entry_ts=_ts(data["entry_ts"]),
            last_bar_open=_ts(data["last_bar_open"]),
            first_bar_open=_ts(data["first_bar_open"]),
            window_last_open=_ts(data["window_last_open"]),
            bars_in_position=int(data["bars_in_position"]),
            pending_invalidation=bool(data["pending_invalidation"]),
            complete_high=_dec(data["complete_high"]),
            complete_low=_dec(data["complete_low"]),
            complete_high_ts=_ts(data["complete_high_ts"]),
            complete_low_ts=_ts(data["complete_low_ts"]),
            exit_base=_dec(data["exit_base"]),
            exit_observed=_dec(data.get("exit_observed")),
            exit_bar_open=_ts(data.get("exit_bar_open")),
            exit_ts=_ts(data["exit_ts"]),
            exit_at_open=bool(data["exit_at_open"]),
            exit_bar_high=_dec(data["exit_bar_high"]),
            exit_bar_low=_dec(data["exit_bar_low"]),
            no_entry_reason=data["no_entry_reason"],
            censored_reason=data["censored_reason"],
        )


def _text(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()
