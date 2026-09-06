"""The ``BaselineStore`` port and the in-memory implementation the tests use.

Append-only, like the table behind it: a revision is written once and never
updated, and a recomputation is a **new** revision with a later ``available_at``.
``append`` therefore returns what is actually stored — a retry that collides on
``uq_feature_baselines_revision`` gets back the id already in the archive, never
the uuid this process happened to mint. Handing the caller an id that was never
inserted would put a dangling ``baseline_id`` into an opportunity envelope
(Astra, T2.3 design review, must-fix 1).

The port is ``async`` because the real implementation talks to Postgres; the
**detectors never touch it**. They receive a :class:`BaselineProjection` already
resolved, which is what keeps ``evaluate`` a pure function.

One store instance serves one ``(algo_version, sampling)`` profile. A median
computed by another algorithm is another population, not a newer value of the
same one, so mixing them in one lookup is a category error rather than a
configuration option.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

from hunter_core.domain.enums import BaselineSampling
from hunter_core.domain.types import uuid7
from hunter_indicators.baselines.projection import BaselineCut
from hunter_indicators.baselines.revision import (
    ALGO_VERSION,
    BaselineRevision,
    StoredBaseline,
)

_Identity = tuple[uuid.UUID, str, int, int, str, str, str, str]
"""``uq_feature_baselines_revision``: market, feature, hour, feature_version,
algo_version, window_end, source, input_fingerprint."""


def revision_identity(revision: BaselineRevision) -> _Identity:
    """The unique-constraint tuple of ``revision``, spelled once for both stores."""
    return (
        revision.key.market_id,
        revision.key.feature,
        revision.key.hour_of_day,
        revision.feature_version,
        revision.algo_version,
        revision.window_end.isoformat(),
        revision.source.value,
        revision.input_fingerprint,
    )


@dataclass(frozen=True, slots=True)
class BaselineRequest:
    """One bucket a consumer wants, with the feature version it is compatible with."""

    market_id: uuid.UUID
    feature: str
    feature_version: int
    hour_of_day: int


class BaselineStore(Protocol):
    """Append-only access to ``feature_baselines`` — the port, not the adapter."""

    async def append(self, revisions: Sequence[BaselineRevision]) -> tuple[StoredBaseline, ...]:
        """Insert ``revisions``, returning what is stored (existing row on retry)."""
        ...

    async def load(
        self, requests: Sequence[BaselineRequest], *, cut: BaselineCut
    ) -> tuple[StoredBaseline, ...]:
        """The newest admissible revision of each requested bucket, under the cut."""
        ...

    async def load_ids(self, ids: Sequence[uuid.UUID]) -> tuple[StoredBaseline, ...]:
        """Exactly these revisions — the replay door: an envelope names its
        ``baseline_ids`` and reproducing yesterday's deviation must read the very
        rows yesterday read, not whatever is newest today."""
        ...


class InMemoryBaselineStore:
    """The port over a dict — for tests and for a scanner running against fakes.

    Shares :func:`revision_identity` and ``StoredBaseline.selection_key`` with the
    SQL adapter, so "which revision wins" cannot drift between the two.
    """

    def __init__(
        self,
        *,
        algo_version: str = ALGO_VERSION,
        sampling: BaselineSampling = BaselineSampling.PER_MINUTE,
    ) -> None:
        self.algo_version = algo_version
        self.sampling = sampling
        self._by_identity: dict[_Identity, StoredBaseline] = {}
        self._by_id: dict[uuid.UUID, StoredBaseline] = {}

    def _profile_matches(self, revision: BaselineRevision) -> bool:
        return revision.algo_version == self.algo_version and revision.sampling is self.sampling

    async def append(self, revisions: Sequence[BaselineRevision]) -> tuple[StoredBaseline, ...]:
        stored: list[StoredBaseline] = []
        for revision in revisions:
            if not self._profile_matches(revision):
                raise ValueError(
                    f"this store serves {self.algo_version}/{self.sampling.value}; "
                    f"{revision.algo_version}/{revision.sampling.value} is another population"
                )
            identity = revision_identity(revision)
            existing = self._by_identity.get(identity)
            if existing is not None:
                stored.append(existing)
                continue
            entry = StoredBaseline(baseline_id=uuid7(), revision=revision)
            self._by_identity[identity] = entry
            self._by_id[entry.baseline_id] = entry
            stored.append(entry)
        return tuple(stored)

    def _candidates(self, request: BaselineRequest, cut: BaselineCut) -> list[StoredBaseline]:
        return [
            entry
            for entry in self._by_id.values()
            if entry.revision.key.market_id == request.market_id
            and entry.revision.key.feature == request.feature
            and entry.revision.key.hour_of_day == request.hour_of_day
            and entry.revision.feature_version == request.feature_version
            and self._profile_matches(entry.revision)
            and cut.admits(entry.revision)
        ]

    async def load(
        self, requests: Sequence[BaselineRequest], *, cut: BaselineCut
    ) -> tuple[StoredBaseline, ...]:
        chosen: list[StoredBaseline] = []
        for request in requests:
            candidates = self._candidates(request, cut)
            if candidates:
                chosen.append(max(candidates, key=lambda entry: entry.selection_key))
        return tuple(chosen)

    async def load_ids(self, ids: Sequence[uuid.UUID]) -> tuple[StoredBaseline, ...]:
        return tuple(self._by_id[key] for key in ids if key in self._by_id)

    def requests_for(
        self, market_id: uuid.UUID, features: Iterable[tuple[str, int]], hour_of_day: int
    ) -> tuple[BaselineRequest, ...]:
        """Convenience for callers assembling a batch (``feature``, version) list."""
        return tuple(
            BaselineRequest(
                market_id=market_id,
                feature=feature,
                feature_version=version,
                hour_of_day=hour_of_day,
            )
            for feature, version in features
        )


__all__ = [
    "BaselineRequest",
    "BaselineStore",
    "InMemoryBaselineStore",
    "revision_identity",
]
