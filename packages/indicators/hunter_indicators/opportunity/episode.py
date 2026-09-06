"""The shapes of an episode: thresholds, sample, durable state, decision.

Split from ``status.py`` for the 350-line budget
(``infra/scripts/check_file_size.py``): the data an episode is made of lives
here, the machine that moves it lives there. Import paths through
``hunter_indicators.opportunity`` are unchanged.

``StatusThresholds`` reads ``opportunity_weights.weights`` (``status`` and
``expiry``) and raises on a missing key: a machine that defaulted a threshold
would decide with numbers nobody published.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any

from hunter_core.domain.enums import OpportunityStage, OpportunityStatus, TradeDirection
from hunter_core.domain.types import ensure_utc

REASON_STALE_OBSERVATION = "stale_observation"
REASON_EPISODE_CLOSED = "episode_closed"
REASON_NOT_ELIGIBLE = "not_eligible"
REASON_SUSTAINED_BY_ANOMALY = "sustained_by_anomaly"
REASON_BELOW_FLOOR_PROVEN = "below_floor_proven"


class EpisodeAction(StrEnum):
    """What the caller has to persist."""

    NONE = "none"
    OPEN = "open"
    UPDATE = "update"
    HOLD = "hold"
    """The row stays as it is and only the counters moved — a sample that could
    not be scored may not move a score, but it does break the expiry run."""
    EXPIRE = "expire"


@dataclass(frozen=True, slots=True)
class StatusThresholds:
    """Read from ``opportunity_weights.weights``: ``status`` and ``expiry``."""

    watching_min: Decimal
    hot_min: Decimal
    entry_candidate_min: Decimal
    anomaly_severity_min: Decimal
    score_floor: Decimal
    below_floor_minutes: int
    weights_version: str

    @classmethod
    def from_weights(cls, weights: Mapping[str, Any], *, version: str) -> StatusThresholds:
        status: Mapping[str, Any] = weights["status"]
        expiry: Mapping[str, Any] = weights["expiry"]
        return cls(
            watching_min=Decimal(str(status["watching_min"])),
            hot_min=Decimal(str(status["hot_min"])),
            entry_candidate_min=Decimal(str(status["entry_candidate_min"])),
            anomaly_severity_min=Decimal(str(status["anomaly_severity_min"])),
            score_floor=Decimal(str(expiry["score_floor"])),
            below_floor_minutes=int(expiry["below_floor_minutes"]),
            weights_version=version,
        )

    @property
    def below_floor_window(self) -> timedelta:
        return timedelta(minutes=self.below_floor_minutes)

    @property
    def below_floor_min_readings(self) -> int:
        """Sixteen points span fifteen minutes at the scanner's per-minute cadence.

        Derived from ``below_floor_minutes`` rather than published as a second
        key: the two would drift, and the count exists only to prove the window
        was actually watched (Astra, T2.4 design review, item 8).
        """
        return self.below_floor_minutes + 1


@dataclass(frozen=True, slots=True)
class StatusSample:
    """One evaluation, as the scorer produced it."""

    observation_ts: datetime
    score: Decimal | None = None
    eligible: bool = True
    stage: OpportunityStage = OpportunityStage.NONE
    direction: TradeDirection = TradeDirection.NEUTRAL
    confidence: Decimal | None = None
    anomaly_severity: Decimal | None = None
    """The strongest **eligible** active anomaly, or ``None``."""
    agreeing_signals: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "observation_ts", ensure_utc(self.observation_ts))

    @property
    def usable(self) -> bool:
        return self.eligible and self.score is not None


@dataclass(frozen=True, slots=True)
class EpisodeState:
    """The durable state of one opportunity episode."""

    status: OpportunityStatus
    first_seen_at: datetime
    observation_ts: datetime
    score: Decimal
    peak_score: Decimal
    stage: OpportunityStage = OpportunityStage.NONE
    direction: TradeDirection = TradeDirection.NEUTRAL
    confidence: Decimal | None = None
    below_floor_since: datetime | None = None
    """``opportunities.below_40_since``: the start of the current **proven** run."""
    below_floor_readings: int = 0
    expired_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "first_seen_at", ensure_utc(self.first_seen_at))
        object.__setattr__(self, "observation_ts", ensure_utc(self.observation_ts))
        # Every timestamp of the state, not only the two required ones: a state
        # rehydrated with a naive ``below_floor_since`` would compare against an
        # aware ``observation_ts`` and raise in the middle of the expiry check
        # (Astra, T2.4 diff review, nice-to-have).
        if self.expired_at is not None:
            object.__setattr__(self, "expired_at", ensure_utc(self.expired_at))
        if self.below_floor_since is not None:
            object.__setattr__(self, "below_floor_since", ensure_utc(self.below_floor_since))
        # The same biconditional the table enforces
        # (``expired_at_matches_status``, docs/DATABASE.md §17.3): the partial
        # unique index keys episode identity on ``expired_at`` and every consumer
        # reads ``status``, so a state where the two disagree would be an episode
        # that is open for the index and closed for the Radar. Refusing it here
        # keeps the invariant one layer earlier than the database.
        if (self.status is OpportunityStatus.EXPIRED) != (self.expired_at is not None):
            raise ValueError(
                f"status={self.status} and expired_at={self.expired_at} disagree about "
                "whether this episode is closed"
            )

    @property
    def open(self) -> bool:
        return self.expired_at is None

    def as_wire(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "first_seen_at": self.first_seen_at,
            "observation_ts": self.observation_ts,
            "score": self.score,
            "peak_score": self.peak_score,
            "stage": self.stage.value,
            "direction": self.direction.value,
            "confidence": self.confidence,
            "below_floor_since": self.below_floor_since,
            "below_floor_readings": self.below_floor_readings,
            "expired_at": self.expired_at,
        }

    @classmethod
    def from_wire(cls, wire: Mapping[str, Any]) -> EpisodeState:
        """Rebuild a state after a restart — from JSON or from Python objects."""
        return cls(
            status=OpportunityStatus(wire["status"]),
            first_seen_at=_ts(wire["first_seen_at"]),
            observation_ts=_ts(wire["observation_ts"]),
            score=Decimal(str(wire["score"])),
            peak_score=Decimal(str(wire["peak_score"])),
            stage=OpportunityStage(wire["stage"]),
            direction=TradeDirection(wire["direction"]),
            confidence=None if wire["confidence"] is None else Decimal(str(wire["confidence"])),
            below_floor_since=_optional_ts(wire["below_floor_since"]),
            below_floor_readings=int(wire["below_floor_readings"]),
            expired_at=_optional_ts(wire["expired_at"]),
        )


def _ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        return ensure_utc(value)
    return ensure_utc(datetime.fromisoformat(str(value).replace("Z", "+00:00")))


def _optional_ts(value: Any) -> datetime | None:
    return None if value is None else _ts(value)


@dataclass(frozen=True, slots=True)
class StatusDecision:
    """What one sample did to one episode."""

    action: EpisodeAction
    status: OpportunityStatus
    candidate: OpportunityStatus
    state_in: EpisodeState | None
    state_out: EpisodeState | None
    thresholds_version: str
    reason: str | None = None

    def as_wire(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "status": self.status.value,
            "candidate": self.candidate.value,
            "reason": self.reason,
            "thresholds_version": self.thresholds_version,
            "state_in": None if self.state_in is None else self.state_in.as_wire(),
            "state_out": None if self.state_out is None else self.state_out.as_wire(),
        }


__all__ = [
    "REASON_BELOW_FLOOR_PROVEN",
    "REASON_EPISODE_CLOSED",
    "REASON_NOT_ELIGIBLE",
    "REASON_STALE_OBSERVATION",
    "REASON_SUSTAINED_BY_ANOMALY",
    "EpisodeAction",
    "EpisodeState",
    "StatusDecision",
    "StatusSample",
    "StatusThresholds",
]
