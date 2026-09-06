"""The baselines a consumer is allowed to see at one cut, carried by value.

Why a projection object at all: a detector must stay a **pure function** — no
IO, no clock — so the revisions it compares against are resolved once, by the
scanner, and handed over. That also makes the envelope honest: the projection
knows exactly which ``baseline_id`` answered each lookup, which is what a replay
tomorrow needs to reproduce today's deviation.

**The causal cut is two conditions, not one** (``docs/DATABASE.md`` §17.2):

- ``available_at <= as_of`` — we could not have known a baseline before it
  existed;
- ``window_end < observation_ts`` — a baseline may not contain the very
  observation being judged. A feature of 10:00 processed at 10:02 would pass a
  lone ``available_at <= 10:02`` against a revision published at 10:01 that
  already folded 10:00 in.

The store applies both in SQL; the projection **re-checks them on construction**
and raises. That is not duplication: a projection is also built from a cache, a
test fixture or a replay, and an entry that violates the cut there is a bug that
must surface as an error rather than as a quietly biased score.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from hunter_core.domain.types import ensure_utc
from hunter_indicators.baselines.revision import (
    ALGO_VERSION,
    BaselineGate,
    BaselineKey,
    BaselineRevision,
    StoredBaseline,
)

REASON_NO_BASELINE = "no_baseline"
"""Nothing was published for this bucket at this cut — not even a thin revision."""

REASON_VERSION_MISMATCH = "baseline_version_mismatch"
"""The revision describes another population: another feature version.

The SQL selection pins the versions, but a projection is also built from a cache
or from ``load_ids`` during a replay, and those paths bypass it. The reader
refuses rather than comparing a v1 reading against a v2 median (Astra, T2.3 diff
review, must-fix 7)."""


@dataclass(frozen=True, slots=True)
class BaselineCut:
    """The instant a consumer is reasoning at, and the observation it is judging."""

    as_of: datetime
    observation_ts: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "as_of", ensure_utc(self.as_of))
        object.__setattr__(self, "observation_ts", ensure_utc(self.observation_ts))
        if self.observation_ts > self.as_of:
            raise ValueError(
                f"observation_ts {self.observation_ts} is after as_of {self.as_of}: a cut "
                "cannot judge an observation that had not happened yet"
            )

    def admits(self, revision: BaselineRevision) -> bool:
        return revision.available_at <= self.as_of and revision.window_end < self.observation_ts


@dataclass(frozen=True, slots=True)
class BaselineLookup:
    """The answer to "what do I compare this reading against?", with its reason."""

    key: BaselineKey
    baseline_id: uuid.UUID | None = None
    revision: BaselineRevision | None = None
    reason: str | None = None

    @property
    def usable(self) -> bool:
        return self.revision is not None and self.reason is None

    @property
    def median(self) -> Decimal | None:
        return None if self.revision is None else self.revision.median

    @property
    def mad(self) -> Decimal | None:
        return None if self.revision is None else self.revision.mad


class BaselineProjection:
    """The chosen revision per bucket at one cut, under one gate.

    Immutable by construction and cheap to pass around: the scanner builds one
    per evaluation batch and every detector reads from it.
    """

    __slots__ = ("_algo_version", "_by_key", "_cut", "_gate")

    def __init__(
        self,
        entries: Iterable[StoredBaseline],
        *,
        cut: BaselineCut,
        gate: BaselineGate,
        algo_version: str = ALGO_VERSION,
    ) -> None:
        self._cut = cut
        self._gate = gate
        self._algo_version = algo_version
        by_key: dict[tuple[uuid.UUID, str, int], StoredBaseline] = {}
        for entry in entries:
            revision = entry.revision
            if revision.algo_version != algo_version:
                raise ValueError(
                    f"baseline {entry.baseline_id} was computed by {revision.algo_version}, "
                    f"this projection serves {algo_version}: another population, not a newer "
                    "value of the same one"
                )
            if not cut.admits(revision):
                raise ValueError(
                    f"baseline {entry.baseline_id} (available_at={revision.available_at}, "
                    f"window_end={revision.window_end}) violates the cut as_of={cut.as_of}, "
                    f"observation_ts={cut.observation_ts}"
                )
            index = (revision.key.market_id, revision.key.feature, revision.key.hour_of_day)
            previous = by_key.get(index)
            if previous is not None and previous.baseline_id != entry.baseline_id:
                raise ValueError(
                    f"two revisions offered for {index}: {previous.baseline_id} and "
                    f"{entry.baseline_id}. Selection belongs to the store, not to the reader"
                )
            by_key[index] = entry
        self._by_key = by_key

    @property
    def cut(self) -> BaselineCut:
        return self._cut

    @property
    def gate(self) -> BaselineGate:
        return self._gate

    def __len__(self) -> int:
        return len(self._by_key)

    def resolve(
        self,
        market_id: uuid.UUID,
        feature: str,
        observation_ts: datetime,
        *,
        feature_version: int | None = None,
    ) -> BaselineLookup:
        """The baseline for ``feature`` in the UTC-hour bucket of ``observation_ts``.

        The bucket is the hour of the observation being judged: volume at 03:00
        UTC is not volume at 15:00 UTC (``docs/DATABASE.md`` §17.2).
        ``feature_version`` is the version the *caller* computes with; a revision
        of another version is visible and unusable.
        """
        observation_ts = ensure_utc(observation_ts)
        if observation_ts != self._cut.observation_ts:
            raise ValueError(
                f"this projection was built for observation_ts={self._cut.observation_ts}, "
                f"asked about {observation_ts}"
            )
        key = BaselineKey(market_id=market_id, feature=feature, hour_of_day=observation_ts.hour)
        entry = self._by_key.get((market_id, feature, observation_ts.hour))
        if entry is None:
            return BaselineLookup(key=key, reason=REASON_NO_BASELINE)
        if feature_version is not None and entry.revision.feature_version != feature_version:
            reason = REASON_VERSION_MISMATCH
        else:
            reason = entry.revision.gate_reason(self._gate)
        return BaselineLookup(
            key=key,
            baseline_id=entry.baseline_id,
            revision=entry.revision,
            reason=reason,
        )


__all__ = [
    "REASON_NO_BASELINE",
    "REASON_VERSION_MISMATCH",
    "BaselineCut",
    "BaselineLookup",
    "BaselineProjection",
]
