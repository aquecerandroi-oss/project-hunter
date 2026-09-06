"""``FeatureValue`` and ``FeatureVector`` — a number is never separated from why.

Three states, and only three: ``ok`` (computed from inputs inside their
freshness budget), ``degraded`` (computed, but an input was late — the number is
there and the consumer decides) and ``unavailable`` (no number at all). A
missing feature is **never** a zero: ``0`` is a legitimate reading of some
features (a market with no trades in the window has ``trade_velocity_1m = 0``)
and inventing it would put a fabricated value in a score.

The wire form is what goes into ``feature_snapshots.features`` and into the
opportunity envelope, serialised through
:func:`hunter_core.strategies.canonical.canonical_json`: sorted keys, numbers as
normalised decimal strings, timestamps as ISO-8601 ``Z``. Recomputing a stored
sample must produce the same bytes.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from hunter_core.domain.types import ensure_utc
from hunter_core.strategies.canonical import canonical_json
from hunter_core.strategies.numeric import CONTEXT

_MICROS = Decimal(10**6)


def seconds_between(start: datetime, end: datetime) -> Decimal:
    """``end - start`` in exact seconds, from the integer fields of the delta.

    Every age in a sample goes through here. ``total_seconds()`` is a binary
    float, so the seconds it reports approximate the arithmetic; and the
    arithmetic itself runs under ``CONTEXT``, because ``prec = 6`` in the worker
    would round a 10.000001 s old book back to 10 s and put it inside its
    freshness budget (Astra, fix-pass review, must-fix 1).
    """
    delta = end - start
    with localcontext(CONTEXT):
        return Decimal(delta.days * 86400 + delta.seconds) + Decimal(delta.microseconds) / _MICROS


class Quality(StrEnum):
    """How much the number can be trusted, worst last."""

    OK = "ok"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


_RANK = {Quality.OK: 0, Quality.DEGRADED: 1, Quality.UNAVAILABLE: 2}


def worst(*qualities: Quality) -> Quality:
    """The worst of ``qualities`` (``ok`` when none is given)."""
    return max(qualities, key=lambda q: _RANK[q], default=Quality.OK)


class Reason(StrEnum):
    """Why a feature is not ``ok``. Maturity of a baseline is *not* here: an
    immature baseline makes a **detector** unavailable, not the feature that
    feeds it (``docs/plans/M2.md`` §Baselines; Astra, T2.2 review, 2b)."""

    WARMUP = "warmup"
    """The required window does not exist yet."""
    GAP = "gap"
    """A minute inside the required window is missing."""
    MISSING_INPUT = "missing_input"
    """The source or the field is not there at all."""
    STALE_INPUT = "stale_input"
    """Computable, but an input is older than its freshness budget."""
    ZERO_DIVISOR = "zero_divisor"
    """The denominator is zero — undefined, not zero."""
    INSUFFICIENT_SAMPLE = "insufficient_sample"
    """Fewer observations than the definition requires."""
    INSUFFICIENT_COVERAGE = "insufficient_coverage"
    """A ring buffer cannot prove it covers the requested window."""
    MISALIGNED = "misaligned"
    """The requested cut does not sit on a bar boundary."""
    CORRUPT_INPUT = "corrupt_input"
    """The input parses but cannot describe a market (a crossed book, say).

    Distinct from ``missing_input`` on purpose: "Redis had no book" and "the
    book we got quotes a bid above the ask" are different facts, and the value
    is withheld in both cases — corruption looks like an absent book, never like
    a different book."""
    AFTER_CUT = "after_cut"
    """The only observation available is newer than ``as_of``."""


@dataclass(frozen=True, slots=True)
class FeatureValue:
    """One feature of one vector."""

    key: str
    value: Decimal | None
    quality: Quality
    reason: Reason | None = None
    inputs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.quality is Quality.UNAVAILABLE:
            if self.value is not None:
                raise ValueError(f"{self.key}: an unavailable feature carries no value")
            if self.reason is None:
                raise ValueError(f"{self.key}: an unavailable feature must carry a reason")
        elif self.value is None:
            raise ValueError(f"{self.key}: a {self.quality} feature must carry a value")

    @classmethod
    def ok(cls, key: str, value: Decimal, *, inputs: Sequence[str] = ()) -> FeatureValue:
        return cls(key=key, value=value, quality=Quality.OK, inputs=tuple(inputs))

    @classmethod
    def unavailable(cls, key: str, reason: Reason, *, inputs: Sequence[str] = ()) -> FeatureValue:
        return cls(
            key=key,
            value=None,
            quality=Quality.UNAVAILABLE,
            reason=reason,
            inputs=tuple(inputs),
        )

    def degraded_to(self, quality: Quality, reason: Reason) -> FeatureValue:
        """The same reading under a worse quality (an input was late/absent)."""
        if _RANK[quality] <= _RANK[self.quality]:
            return self
        return FeatureValue(
            key=self.key,
            value=None if quality is Quality.UNAVAILABLE else self.value,
            quality=quality,
            reason=reason,
            inputs=self.inputs,
        )

    def as_wire(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "quality": self.quality.value,
            "reason": self.reason.value if self.reason else None,
            "inputs": list(self.inputs),
        }


@dataclass(frozen=True, slots=True)
class InputProvenance:
    """What was known about one input at ``as_of`` — shared by every feature.

    Per-feature ``inputs`` point here, so an explanation ("degraded because the
    open interest was 30 minutes old") can be reconstructed from the stored
    sample alone (Astra, T2.2 review, 2b: provenance per entry).
    """

    input: str
    available: bool
    quality: Quality
    reason: Reason | None = None
    ts: datetime | None = None
    age_s: Decimal | None = None
    covers_from: datetime | None = None
    covered_until: datetime | None = None
    """The instant up to which the source proved continuous coverage."""
    truncated: bool = False

    def as_wire(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "quality": self.quality.value,
            "reason": self.reason.value if self.reason else None,
            "ts": self.ts,
            "age_s": self.age_s,
            "covers_from": self.covers_from,
            "covered_until": self.covered_until,
            "truncated": self.truncated,
        }


@dataclass(frozen=True, slots=True)
class FeatureVector:
    """Every feature of one market at one instant, with its provenance."""

    exchange: str
    symbol: str
    ts: datetime
    feature_set_version: str
    values: Mapping[str, FeatureValue]
    provenance: Mapping[str, InputProvenance] = MappingProxyType({})
    quality_policy_version: str = "quality_v1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "ts", ensure_utc(self.ts))
        for key, value in self.values.items():
            if key != value.key:
                raise ValueError(f"vector key {key!r} indexes feature {value.key!r}")
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))
        object.__setattr__(self, "provenance", MappingProxyType(dict(self.provenance)))

    def number(self, key: str) -> Decimal | None:
        """The value of ``key`` when it is usable, else ``None``."""
        value = self.values.get(key)
        return None if value is None else value.value

    def quality_of(self, key: str) -> Quality:
        value = self.values.get(key)
        return Quality.UNAVAILABLE if value is None else value.quality

    def as_wire(self) -> dict[str, Any]:
        """The dict that goes to JSONB (``Decimal``/``datetime`` still typed)."""
        return {
            "exchange": self.exchange,
            "symbol": self.symbol,
            "ts": self.ts,
            "feature_set_version": self.feature_set_version,
            "quality_policy_version": self.quality_policy_version,
            "values": {key: value.as_wire() for key, value in sorted(self.values.items())},
            "provenance": {key: entry.as_wire() for key, entry in sorted(self.provenance.items())},
        }

    def canonical_bytes(self) -> bytes:
        """The canonical UTF-8 bytes of :meth:`as_wire` — byte-stable."""
        return canonical_json(self.as_wire())

    def as_json(self) -> dict[str, Any]:
        """:meth:`as_wire` with every value already in its canonical JSON shape."""
        decoded: Any = json.loads(self.canonical_bytes())
        return dict(decoded)


__all__ = [
    "FeatureValue",
    "FeatureVector",
    "InputProvenance",
    "Quality",
    "Reason",
    "seconds_between",
    "worst",
]
