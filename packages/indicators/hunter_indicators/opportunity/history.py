"""``should_record_history``: which samples are worth keeping, and why.

``opportunity_history`` is a record of **decisions**, not a fixed-rate sampling of
them (``docs/DATABASE.md`` §17.3), so a sample is preserved when it changed
something a reader could act on. The rule is versioned (``history_v1``) and pure:
it compares the sample against the **last one actually persisted**, never against
the last one computed — otherwise a series of 2.9-point steps would keep resetting
the comparison and a market could drift twenty points without leaving a trace.

What triggers a row, and why each one is here:

- the first sample of an episode — there is nothing to compare against;
- a score delta of at least three points against the last persisted score (the
  joint decision's number);
- a change of status or of stage — both are what the Radar filters on;
- a change of **direction**, of the stage's published direction or of the regime
  pair: a flip from long to short at the same score, status and stage would
  otherwise be invisible for up to five minutes (Astra, T2.4 design review,
  item 10);
- a change of any version (scorer, components, weights, features, normalisation,
  stage, regime, quality policy, explanation templates): the same inputs now mean
  something else, and the trajectory has to show where that happened;
- a change of eligibility — "we stopped being able to score this" is a fact about
  the market's data, not a gap in the series;
- a change of the **quality signature**: which components were available and how
  many of their inputs were read. Global eligibility alone is too coarse — losing
  the book degrades liquidity and order flow while the score barely moves, and an
  outage that starts and ends between two periodic samples would vanish from the
  history (Astra, T2.4 diff review, must-fix 5);
- five minutes since the last persisted sample, so a quiet episode still has a
  heartbeat.

**``history_v2`` (27/09/2026, the disk decision).** ``history_v1`` wrote ~50 rows
an hour per opportunity (``docs/design/retencao-e-disco-2026-09-27.md`` §1: 63 G
in September). :func:`sparse_history_policy` keeps only the first sample, a
change of status or stage (what the Radar filters on — a HOT excursion between two
heartbeats would otherwise vanish) and the heartbeat, whose interval the scanner
reads as a cadence (``SCANNER_HISTORY_INTERVAL_S``). The other triggers still
compute but no longer write a row by themselves: each preserved sample stays whole
(envelope included), what happens *between* samples is no longer fully observable.

**``history_v2`` (27/09/2026, the disk decision).** ``history_v1`` wrote ~50 rows
an hour per opportunity (``docs/design/retencao-e-disco-2026-09-27.md`` §1: 63 G
in September). :func:`sparse_history_policy` keeps only the first sample, a
change of status or stage (what the Radar filters on — a HOT excursion between two
heartbeats would otherwise vanish) and the heartbeat, whose interval the scanner
reads as a cadence (``SCANNER_HISTORY_INTERVAL_S``). The other triggers still
compute but no longer write a row by themselves: each preserved sample stays whole
(envelope included), what happens *between* samples is no longer fully observable.

What deliberately does **not** trigger one: a new ``baseline_id`` (the hourly
refresh would write a row for every market every hour) and a confidence that
merely wobbles.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from types import MappingProxyType
from typing import Any

from hunter_core.domain.enums import OpportunityStage, OpportunityStatus, TradeDirection
from hunter_core.domain.types import ensure_utc
from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.opportunity.model import ComponentScore

HISTORY_POLICY_VERSION = "history_v1"
HISTORY_POLICY_V2 = "history_v2"

REASON_FIRST = "first_sample"
REASON_SCORE_DELTA = "score_delta"
REASON_STATUS = "status_changed"
REASON_STAGE = "stage_changed"
REASON_DIRECTION = "direction_changed"
REASON_STAGE_DIRECTION = "stage_direction_changed"
REASON_REGIME = "regime_changed"
REASON_VERSION = "version_changed"
REASON_ELIGIBILITY = "eligibility_changed"
REASON_QUALITY = "quality_changed"
REASON_INTERVAL = "interval_elapsed"
REASON_STALE = "stale_sample"

NO_VERSIONS: Mapping[str, str] = MappingProxyType({})

_ORDER = (
    REASON_FIRST,
    REASON_SCORE_DELTA,
    REASON_STATUS,
    REASON_STAGE,
    REASON_DIRECTION,
    REASON_STAGE_DIRECTION,
    REASON_REGIME,
    REASON_VERSION,
    REASON_ELIGIBILITY,
    REASON_QUALITY,
    REASON_INTERVAL,
)
"""Declared order, so two runs report the same reasons in the same sequence."""


@dataclass(frozen=True, slots=True)
class HistoryPolicy:
    """The versioned sampling parameters."""

    min_score_delta: Decimal = Decimal("3")
    interval: timedelta = timedelta(minutes=5)
    version: str = HISTORY_POLICY_VERSION
    triggers: frozenset[str] | None = None
    """The reasons allowed to write a row; ``None`` = every one (``history_v1``)."""
    triggers: frozenset[str] | None = None
    """The reasons allowed to write a row; ``None`` = every one (``history_v1``)."""


DEFAULT_HISTORY_POLICY = HistoryPolicy()
"""The shipped ``history_v1`` policy, as a module singleton (a call in a default
argument is evaluated once anyway, and ruff's B008 asks for it to be visible)."""


def sparse_history_policy(interval: timedelta) -> HistoryPolicy:
    """``history_v2``: first sample, status or stage change, or ``interval`` elapsed."""
    if interval <= timedelta(0):
        raise ValueError(f"history interval must be positive, got {interval}")
    return HistoryPolicy(
        interval=interval,
        version=HISTORY_POLICY_V2,
        triggers=frozenset({REASON_STATUS, REASON_STAGE, REASON_INTERVAL}),
    )


@dataclass(frozen=True, slots=True)
class HistoryMark:
    """The part of a sample the sampling rule looks at."""

    ts: datetime
    score: Decimal | None
    status: OpportunityStatus
    stage: OpportunityStage = OpportunityStage.NONE
    direction: TradeDirection = TradeDirection.NEUTRAL
    stage_direction: TradeDirection = TradeDirection.NEUTRAL
    regime: str = ""
    """The published regime **pair**, spelled by the caller (``bull/normal``)."""
    quality: str = ""
    """Which components could be read, from :func:`quality_signature`."""
    eligible: bool = True
    versions: Mapping[str, str] = NO_VERSIONS

    def __post_init__(self) -> None:
        object.__setattr__(self, "ts", ensure_utc(self.ts))

    def as_wire(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "score": self.score,
            "status": self.status.value,
            "stage": self.stage.value,
            "direction": self.direction.value,
            "stage_direction": self.stage_direction.value,
            "regime": self.regime,
            "quality": self.quality,
            "eligible": self.eligible,
            "versions": dict(sorted(self.versions.items())),
        }


@dataclass(frozen=True, slots=True)
class HistoryVerdict:
    """Whether to write the row, and every reason that argued for it."""

    record: bool
    reasons: tuple[str, ...] = ()
    policy_version: str = HISTORY_POLICY_VERSION
    interval_s: int | None = None
    """The heartbeat of the policy that judged the sample, in whole seconds — a
    sparse series says under which interval each of its rows was kept (F2)."""

    def as_wire(self) -> dict[str, Any]:
        return {
            "record": self.record,
            "reasons": list(self.reasons),
            "policy_version": self.policy_version,
            "interval_s": self.interval_s,
        }


def _verdict(policy: HistoryPolicy, reasons: tuple[str, ...], *, record: bool) -> HistoryVerdict:
    return HistoryVerdict(
        record=record,
        reasons=reasons,
        policy_version=policy.version,
        interval_s=int(policy.interval.total_seconds()),
    )


def should_record_history(
    previous: HistoryMark | None,
    now: HistoryMark,
    policy: HistoryPolicy = DEFAULT_HISTORY_POLICY,
) -> HistoryVerdict:
    """Pure: ``previous`` is the last **persisted** sample, ``now`` the candidate."""
    if previous is None:
        return _verdict(policy, (REASON_FIRST,), record=True)
    if now.ts <= previous.ts:
        return _verdict(policy, (REASON_STALE,), record=False)
    found: set[str] = set()
    if previous.score is not None and now.score is not None:
        with localcontext(CONTEXT):  # the subtraction rounds under the ambient context
            moved = abs(now.score - previous.score) >= policy.min_score_delta
        if moved:
            found.add(REASON_SCORE_DELTA)
    if now.status is not previous.status:
        found.add(REASON_STATUS)
    if now.stage is not previous.stage:
        found.add(REASON_STAGE)
    if now.direction is not previous.direction:
        found.add(REASON_DIRECTION)
    if now.stage_direction is not previous.stage_direction:
        found.add(REASON_STAGE_DIRECTION)
    if now.regime != previous.regime:
        found.add(REASON_REGIME)
    if dict(now.versions) != dict(previous.versions):
        found.add(REASON_VERSION)
    if now.eligible is not previous.eligible:
        found.add(REASON_ELIGIBILITY)
    if now.quality != previous.quality:
        found.add(REASON_QUALITY)
    if now.ts - previous.ts >= policy.interval:
        found.add(REASON_INTERVAL)
    if policy.triggers is not None:
        found &= policy.triggers
    reasons = tuple(reason for reason in _ORDER if reason in found)
    return _verdict(policy, reasons, record=bool(reasons))


def quality_signature(components: Sequence[ComponentScore]) -> str:
    """A deterministic fingerprint of *what could be read* in this sample.

    ``name:available:used/expected`` per component, sorted — so a degraded spread
    that empties the liquidity component changes the signature even though the
    score, the status and the stage did not move. Built from the decomposition
    the sample already carries, never from a second source of truth.
    """
    return "|".join(
        f"{item.name}:{int(item.available)}:{item.used}/{item.expected}"
        for item in sorted(components, key=lambda entry: entry.name)
    )


__all__ = [
    "DEFAULT_HISTORY_POLICY",
    "HISTORY_POLICY_V2",
    "HISTORY_POLICY_VERSION",
    "REASON_DIRECTION",
    "REASON_ELIGIBILITY",
    "REASON_FIRST",
    "REASON_INTERVAL",
    "REASON_QUALITY",
    "REASON_REGIME",
    "REASON_SCORE_DELTA",
    "REASON_STAGE",
    "REASON_STAGE_DIRECTION",
    "REASON_STALE",
    "REASON_STATUS",
    "REASON_VERSION",
    "HistoryMark",
    "HistoryPolicy",
    "HistoryVerdict",
    "quality_signature",
    "should_record_history",
    "sparse_history_policy",
]
