"""``beta_v1`` — a market's slope against the BTC, versioned and with an expiry.

Pure and self-contained: candles in, an estimate out, no IO and no clock. The
scanner (per closed hour) and the Risk Engine (per decision) are the callers;
neither is touched here — see ``.claude/state/notes-T3.2.md`` for where the call
goes and for the ``market_betas`` schema this proposes to the database-architect.

The contract in one paragraph: thirty days of hourly simple returns built from
final 1-minute candles, paired strictly bar-for-bar with the reference; ordinary
least squares **with an intercept**; valid only with at least twenty unbroken
days of pairs reaching the cut; ``valid_until = as_of + 1h`` because it is
recomputed every closed hour; the BTC is ``1`` by definition rather than by
estimation; and every row carries the ``beta_version`` that produced it so a
consumer can refuse a number it does not recognise.
"""

from hunter_indicators.beta.estimate import compute_beta, invalidates, reference_beta
from hunter_indicators.beta.model import (
    BETA_METHOD_VERSION,
    BETA_QUANTUM,
    DEFAULT_SPEC,
    KNOWN_BETA_VERSIONS,
    NUMERIC_POLICY,
    R2_QUANTUM,
    REASON_BTC_MISSING,
    REASON_DEGENERATE_VARIANCE,
    REASON_GAPS,
    REASON_INSUFFICIENT_HISTORY,
    BetaEstimate,
    BetaEstimator,
    BetaSpec,
    HourlyReturn,
    ReturnKind,
    beta_version,
    is_known_version,
)
from hunter_indicators.beta.returns import floor_bar, hourly_closes, hourly_returns, window_bounds

__all__ = [
    "BETA_METHOD_VERSION",
    "BETA_QUANTUM",
    "DEFAULT_SPEC",
    "KNOWN_BETA_VERSIONS",
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
    "compute_beta",
    "floor_bar",
    "hourly_closes",
    "hourly_returns",
    "invalidates",
    "is_known_version",
    "reference_beta",
    "window_bounds",
]
