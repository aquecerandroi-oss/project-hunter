"""The contract of ``beta_v1``: parameters, identity, and what an estimate is.

Data only, so ``returns.py`` (candles -> hourly returns) and ``estimate.py`` (the
regression and the validity protocol) share one shape without depending on each
other.

**Why the identity is declared instead of hashed from the source.** The brief
asked for "a digest of the module + parameters". The repository already answered
that question twice — ``FeatureDefinition`` deliberately keeps the *description*
out of ``feature_set_version`` (``features/definitions.py``) and
``RegimeThresholds.identity`` hashes the parameters, not the file — and the
reason is the one that matters here: a beta stored last week must keep meaning
what it meant, and reformatting a comment must not retroactively invalidate
every row the Risk Engine is holding. So :func:`beta_version` hashes the
**declared numerical contract** (estimator, return kind, window, contiguity,
freshness, arithmetic policy, quantums) and :data:`BETA_METHOD_VERSION` is bumped
**by hand** when a formula changes — with the previous implementation kept, never
edited in place, exactly like a feature version. Source provenance is a different
question (which build produced the row) and belongs to the deployment record, not
to the mathematical identity: hashing this file would still not cover
``hunter_core``'s arithmetic context, so it would buy false confidence.

**Numerics.** Everything below is ``Decimal`` under
``hunter_core.strategies.numeric.CONTEXT`` (28 digits, ``ROUND_HALF_EVEN``).
There is no ``float`` and no NumPy anywhere in this package — see the note in
:mod:`hunter_indicators.beta.estimate` for the measurement that decision rests
on.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from enum import StrEnum
from typing import Any

from hunter_core.domain.types import ensure_utc
from hunter_core.strategies.canonical import canonical_json

BETA_METHOD_VERSION = "beta_v1"
"""``market_betas.beta_version``. A formula change is a **new string**, never an
edit of this one."""

KNOWN_BETA_VERSIONS: frozenset[str] = frozenset({BETA_METHOD_VERSION})
"""What a consumer accepts by default. The Risk Engine refuses anything else:
a beta produced under parameters nobody shipped must not size a position."""

BETA_QUANTUM = Decimal("0.00000001")
"""Eight decimals. A storage resolution, not a claim about statistical precision."""

R2_QUANTUM = Decimal("0.000001")

MINUTES_PER_DAY = 1440

REASON_INSUFFICIENT_HISTORY = "insufficient_history"
"""The history never reached back far enough — warm-up, not damage."""

REASON_GAPS = "gaps"
"""The history reaches back but the recent run is broken (or does not reach the
cut). The same distinction ``features/windows.py`` makes between ``warmup`` and
``gap``."""

REASON_BTC_MISSING = "btc_missing"
"""No hour of the reference could be paired at all."""

REASON_DEGENERATE_VARIANCE = "degenerate_variance"
"""A constant series: either the slope is not identifiable (``Sxx = 0``) or
``R^2`` is ``0/0`` (``Syy = 0``). Never replaced by a zero or by a one."""


class BetaEstimator(StrEnum):
    OLS_WITH_INTERCEPT = "ols_with_intercept"
    """``beta = Sxy/Sxx`` on **centred** returns, with ``alpha`` reported.

    Chosen over regression through the origin, and the reason is measurable:
    ``beta_origin = beta_ols + alpha*sum(x)/sum(x^2)``, so a market that drifted
    while the BTC drifted the other way gets a slope biased by its own mean.
    Hourly means are small but not zero, and this is also what ``regr_slope``
    computes — the function both KB-0060 and KB-0071 measured the universe with,
    so the operational number stays comparable to the published one.
    """

    DEFINITION = "definition"
    """The reference against itself: ``beta = 1`` because of what beta *is*."""


class ReturnKind(StrEnum):
    SIMPLE = "simple"
    """``c_t/c_{t-1} - 1``. Log returns are what KB-0060/KB-0071 measured, and
    they are **not** what this consumer needs: the directive's cap is
    ``sum |notional * beta| <= 0.5 * equity``, a statement about money, and only
    the simple return makes ``delta_value = notional * r`` exact. At an hourly
    horizon a 50% drop is ``-0.5`` simple and ``-0.693`` log — a difference
    concentrated precisely in the high-influence observations of a regression."""


@dataclass(frozen=True, slots=True)
class BetaSpec:
    """Every parameter that decides the number. Overriding any of them renames it."""

    window_days: int = 30
    """The rolling window the pairs are drawn from (directive proposal, item 4)."""
    min_contiguous_days: int = 20
    """Days of **unbroken** paired bars required, ending at the cut."""
    bar_minutes: int = 60
    """One sample = one complete UTC hour of 1-minute candles."""
    max_bar_lag: int = 1
    """How many bars the newest pair may be behind ``window_end``.

    One hour of slack, so a scanner that runs at ``:00:02`` while the last
    minute is still landing does not flip an asset out of the portfolio and back
    every hour. Combined with ``valid_for_minutes`` the worst case is a beta
    computed on data two hours old — immaterial for a thirty-day slope, and the
    alternative (zero slack) would make validity depend on persistence latency."""
    estimator: BetaEstimator = BetaEstimator.OLS_WITH_INTERCEPT
    return_kind: ReturnKind = ReturnKind.SIMPLE
    valid_for_minutes: int = 60
    """``valid_until = window_end + this``: one hour, recomputed every closed hour.

    Anchored to ``window_end`` rather than to ``as_of``, which is a **deviation
    from the brief's literal wording** (``as_of + 1h``) taken on Astra's diff
    review and recorded in ``.claude/state/notes-T3.2.md``. The two agree
    whenever the job runs on the hour, which is the nominal case; they diverge
    when it runs late, and then ``as_of + 1h`` is wrong in the dangerous
    direction — a run at 12:59 over the 11:00-12:00 bar would stay valid until
    13:59, an hour past the recomputation that was supposed to replace it, for a
    worst-case data age of 2h59 instead of the intended 2h."""
    beta_quantum: Decimal = BETA_QUANTUM
    r2_quantum: Decimal = R2_QUANTUM

    def __post_init__(self) -> None:
        if self.bar_minutes < 1 or MINUTES_PER_DAY % self.bar_minutes:
            raise ValueError("bar_minutes must divide a day")
        if self.min_contiguous_days < 1:
            raise ValueError("min_contiguous_days must be >= 1")
        if self.window_days < self.min_contiguous_days:
            raise ValueError("window_days must cover min_contiguous_days")
        if self.max_bar_lag < 0:
            raise ValueError("max_bar_lag must be >= 0")
        if self.valid_for_minutes < 1:
            raise ValueError("valid_for_minutes must be >= 1")

    @property
    def bar(self) -> timedelta:
        return timedelta(minutes=self.bar_minutes)

    @property
    def window(self) -> timedelta:
        return timedelta(days=self.window_days)

    @property
    def valid_for(self) -> timedelta:
        return timedelta(minutes=self.valid_for_minutes)

    @property
    def required_bars(self) -> int:
        """``min_contiguous_days`` expressed in bars — 480 hours by default."""
        return self.min_contiguous_days * MINUTES_PER_DAY // self.bar_minutes

    def as_wire(self) -> dict[str, Any]:
        return {
            "window_days": self.window_days,
            "min_contiguous_days": self.min_contiguous_days,
            "bar_minutes": self.bar_minutes,
            "max_bar_lag": self.max_bar_lag,
            "estimator": self.estimator.value,
            "return_kind": self.return_kind.value,
            "valid_for_minutes": self.valid_for_minutes,
            "beta_quantum": self.beta_quantum,
            "r2_quantum": self.r2_quantum,
        }


DEFAULT_SPEC = BetaSpec()

NUMERIC_POLICY: dict[str, Any] = {
    "arithmetic": "decimal",
    "precision": 28,
    "rounding": ROUND_HALF_EVEN,
    "accumulation": "two_pass_centred_chronological",
}
"""Folded into the version digest: two estimates that agree on every parameter
but not on how they added the numbers are not the same estimator."""


def beta_version(spec: BetaSpec = DEFAULT_SPEC) -> str:
    """``beta_v1``, or ``beta_v1+<digest>`` when a parameter was overridden."""
    if spec == DEFAULT_SPEC:
        return BETA_METHOD_VERSION
    payload = {"params": spec.as_wire(), "numeric": NUMERIC_POLICY}
    digest = hashlib.sha256(canonical_json(payload)).hexdigest()[:12]
    return f"{BETA_METHOD_VERSION}+{digest}"


def is_known_version(version: str, *, allowed: frozenset[str] = KNOWN_BETA_VERSIONS) -> bool:
    """Whether a consumer may act on a beta carrying ``version``."""
    return version in allowed


@dataclass(frozen=True, slots=True)
class HourlyReturn:
    """One simple return over the bar that **starts** at ``hour_start``."""

    hour_start: datetime
    value: Decimal

    def __post_init__(self) -> None:
        if not self.value.is_finite():
            # A NaN reached the regression and surfaced as ``InvalidOperation``
            # deep inside it (Astra, T3.2 diff review). Refused at the boundary
            # instead: a non-finite return is a broken input, not an estimate.
            raise ValueError(f"{self.value} is not a finite return")
        object.__setattr__(self, "hour_start", ensure_utc(self.hour_start))


@dataclass(frozen=True, slots=True)
class BetaEstimate:
    """One market's sensitivity to the reference, with the evidence behind it."""

    version: str
    estimator: BetaEstimator
    as_of: datetime
    window_start: datetime
    window_end: datetime
    input_start: datetime
    """Oldest minute the estimate *depends on* — one bar before ``window_start``.

    The first return of the window needs the close that precedes it, so the data
    the regression reads reaches one bar further back than the window it
    reports. Published rather than implied, because it is the interval a new gap
    has to be tested against (:func:`~hunter_indicators.beta.invalidates`)."""
    last_pair_end: datetime | None
    """End of the newest paired bar. The observed freshness, which ``window_end``
    stops telling the truth about as soon as ``max_bar_lag`` allows any slack."""
    valid_until: datetime
    beta: Decimal | None
    alpha: Decimal | None
    r_squared: Decimal | None
    n: int
    """Paired bars used by the regression — every valid pair inside the window."""
    contiguous_bars: int
    """Length of the unbroken run of pairs ending at the cut. Maturity, not size."""
    valid: bool
    reason: str | None
    spec: BetaSpec
    market: str | None = None
    reference: str | None = None

    def as_wire(self) -> dict[str, Any]:
        """The ``market_betas`` row / audit payload, canonicalisable as it stands."""
        return {
            "version": self.version,
            "estimator": self.estimator.value,
            "market": self.market,
            "reference": self.reference,
            "as_of": self.as_of,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "input_start": self.input_start,
            "last_pair_end": self.last_pair_end,
            "valid_until": self.valid_until,
            "beta": self.beta,
            "alpha": self.alpha,
            "r_squared": self.r_squared,
            "n": self.n,
            "contiguous_bars": self.contiguous_bars,
            "valid": self.valid,
            "reason": self.reason,
            "params": self.spec.as_wire(),
            "numeric": NUMERIC_POLICY,
        }


__all__ = [
    "BETA_METHOD_VERSION",
    "BETA_QUANTUM",
    "DEFAULT_SPEC",
    "KNOWN_BETA_VERSIONS",
    "MINUTES_PER_DAY",
    "NUMERIC_POLICY",
    "R2_QUANTUM",
    "REASON_BTC_MISSING",
    "REASON_DEGENERATE_VARIANCE",
    "REASON_GAPS",
    "REASON_INSUFFICIENT_HISTORY",
    "BetaEstimate",
    "BetaEstimator",
    "BetaSpec",
    "HourlyReturn",
    "ReturnKind",
    "beta_version",
    "is_known_version",
]
