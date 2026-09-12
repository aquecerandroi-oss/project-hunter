"""``dispersion_24h`` — how far the alts moved *away from the BTC*, as a number.

T3.90 / H-P18. On 2026-09-10 and 2026-09-11 the median 24 h return of the sixteen
markets the shadow universe admits was **-4,80 %** and **-3,85 %** while the BTC
was at **-1,50 %** and **-1,30 %** (plantão runs of 10/09 and 11/09,
``obsidian/00-INBOX/Hipoteses-do-plantao.md``). The hypothesis H-P18 is that this
*discordância* — the alts selling off while the reference barely moves — is a
state a decision can be cut by, and this module is the number and nothing else.
Whether a version may decide inside a band of it is
:mod:`hunter_strategy_worker.dispersion_gate`, and whether that band helps is
EXP-0029, which has not been run.

**Not** :mod:`hunter_indicators.breadth.series`. That one counts how many markets
fell over five minutes, each against *its own* earlier close, with a strict
``<``: no reference market, no horizon, no returns compared to one another. This
one needs all three. Reinterpreting one as the other is exactly the mistake two
modules, two versions and two tables exist to prevent (the sentence
``hunter_indicators.breadth`` already writes about
``hunter_indicators.regime.breadth``, kept).

**What one market contributes.** Its 24 h close-to-close return,
``close(T) / close(T - 24h) - 1``. A close at instant ``t`` is the close of the
1-minute candle whose ``open_time`` is ``t - 1 min``, so the reading needs
**exactly two** candles per market, named by :func:`endpoint_open_times`. **No
candle with ``open_time + 1 min > end_time`` may enter** — that is the whole of
the anti-look-ahead rule here, and it is why the caller resolves instants from
that function instead of asking for "the last candle".

**Two closes, not 1 441 — and that is a decision, not an oversight.**
``compute_breadth`` refuses a market that is missing any candle of its window,
because "it moved over five minutes" is a claim about five minutes somebody
observed. The same rule at a 24 h horizon would ask for 1 441 consecutive final
candles per market and one missing minute anywhere in a day would drop that
market; the series would be about feed completeness rather than about prices. A
close-to-close return **is** a two-point claim, so this version requires the two
points and says so in its name and in its docstring. A version that also demands
the interior is a **new version** (``dispersion_24h_v2``), never an edit here.

**No nearest-close fallback.** The two instants are exact. A return measured from
23 h 58 min ago is not a 24 h return, and a fallback would make the series depend
on which minutes happened to be missing rather than on prices. The cost is
declared: one missing minute costs the one reading whose endpoint it is.

**Coverage refuses; it never leans.** Below :data:`MIN_COVERAGE` of the declared
universe the answer is ``None`` with a reason, never a median of whoever happened
to answer — a dispersion computed over three markets would say "the alts are
capitulating" when the truth is "we could not look" (the rule
:mod:`hunter_indicators.breadth.series` already states for its own coverage).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, localcontext
from typing import TYPE_CHECKING

from hunter_core.strategies.numeric import CONTEXT

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import datetime

# The version *strings*, the universe each one folds and which market is the
# reference live in ``hunter_indicators.dispersion.spec`` (the shape T3.88 gave
# ``breadth``), not here: this module is the frozen numeric protocol (this
# horizon, this two-endpoint rule, this median, this strict ``<``). Changing any
# of them is a new version string, never an edit.

HORIZON_MINUTES = 1_440
"""Twenty-four hours, the horizon the plantão measured the discordância over.
A policy asking for another one finds no series and is refused; it does not get
this one relabelled."""

MIN_COVERAGE = Decimal("0.80")
"""Four fifths of the declared universe. Below it the reading is unavailable.
The same fraction ``breadth`` uses and a **separate constant** on purpose: the
day one series relaxes its floor the other must not move with it."""

RETURN_QUANTUM = Decimal("0.000001")
"""Six decimals — one ten-thousandth of a percent — for every return, for the
median and for the dispersion. Enough that ``-4,80 %`` and ``-3,85 %`` are
exact, and coarse enough that two recomputations of the same minute cannot
disagree in the tail of a division."""

RATIO_QUANTUM = Decimal("0.0001")
"""Four decimals for ``share_below_btc``, the same quantum a ratio carries in
``hunter_indicators.regime.model``. 12/15 is 0,8000 exactly."""

REASON_INSUFFICIENT_COVERAGE = "insufficient_coverage"
REASON_EMPTY_UNIVERSE = "empty_universe"
REASON_REFERENCE_MISSING = "btc_missing"
"""The reference has no 24 h return — it is outside the universe, or one of its
two closes is missing. One word for both, because the consequence is one: there
is nothing to measure dispersion *against*. The word is ``market_betas``'s
(``beta_repo``'s frozen vocabulary), reused rather than reinvented."""
REASON_NO_ALTS = "no_alts"
"""The reference answered and nobody else did: a median of nothing."""

__all__ = [
    "HORIZON_MINUTES",
    "MIN_COVERAGE",
    "RATIO_QUANTUM",
    "REASON_EMPTY_UNIVERSE",
    "REASON_INSUFFICIENT_COVERAGE",
    "REASON_NO_ALTS",
    "REASON_REFERENCE_MISSING",
    "RETURN_QUANTUM",
    "DispersionReading",
    "compute_dispersion",
    "endpoint_open_times",
    "median",
]


def endpoint_open_times(
    end_time: datetime, horizon_minutes: int = HORIZON_MINUTES
) -> tuple[datetime, datetime]:
    """The ``open_time`` of the two candles the reading needs, oldest first.

    ``(end_time - horizon - 1 min, end_time - 1 min)``: the newest candle
    admitted is the one that *closed* exactly at ``end_time``, and the oldest is
    the one that closed exactly ``horizon`` minutes before that. The candle
    opening at ``end_time`` closes after it and is not in this pair — the
    anti-look-ahead guarantee expressed as a pair of instants rather than as a
    filter somebody has to remember to write.
    """
    if horizon_minutes < 1:
        raise ValueError(f"horizon_minutes must be at least 1, got {horizon_minutes}")
    minute = timedelta(minutes=1)
    return (end_time - minute * (horizon_minutes + 1), end_time - minute)


def median(values: Sequence[Decimal]) -> Decimal:
    """The middle of ``values``; the mean of the two middles when even.

    Robust by construction — the plantão's number is a **median** and not a mean
    for the reason every baseline in this repo is (``docs/PIPELINE.md`` §3): one
    memecoin printing +400 % must not become "the alts". Quantized to
    :data:`RETURN_QUANTUM` so that the difference against an equally quantized
    reference is exact at six decimals and the database can carry the identity
    ``dispersion = median_alt_r24h - btc_r24h`` as a CHECK.
    """
    if not values:
        raise ValueError("median of an empty sequence")
    ordered = sorted(values)
    middle = len(ordered) // 2
    with localcontext(CONTEXT):
        if len(ordered) % 2 == 1:
            return ordered[middle].quantize(RETURN_QUANTUM)
        return ((ordered[middle - 1] + ordered[middle]) / 2).quantize(RETURN_QUANTUM)


@dataclass(frozen=True, slots=True)
class DispersionReading:
    """One ``dispersion_24h`` value, with everything needed to audit it."""

    end_time: datetime
    horizon_minutes: int
    universe_size: int
    """The markets the universe *declared*, not the ones that answered."""
    covered: int
    """Markets with both endpoint closes — the reference included when it has
    them."""
    alts_covered: int
    """Covered markets other than the reference: the median's own ``n``."""
    alts_below_btc: int
    """Covered alts whose 24 h return is strictly below the reference's. ``0``
    when there is no reference return, because nobody is below a number that
    does not exist — a count, never a verdict."""
    btc_r24h: Decimal | None
    median_alt_r24h: Decimal | None
    dispersion: Decimal | None
    """``median_alt_r24h - btc_r24h``. Negative is the *discordância* H-P18 is
    about: the alts below the reference."""
    share_below_btc: Decimal | None
    """``alts_below_btc / alts_covered``, ``None`` when the reading is
    unusable — never a fraction of a universe nobody could see."""
    coverage: Decimal
    """``covered / universe_size``."""
    usable: bool
    reason: str | None
    """Non-null exactly when ``usable`` is false — the same
    ``valid = (reason IS NULL)`` shape ``market_betas`` makes a constraint."""


def _returns[MarketKey](
    closes: Mapping[MarketKey, Mapping[datetime, Decimal]],
    *,
    old_open: datetime,
    new_open: datetime,
) -> dict[MarketKey, Decimal]:
    """``market -> r24h`` for every market that has **both** endpoint closes.

    A non-positive old close is treated as a missing one: it is not a price, and
    a return divided by it is not a number. Excluding it is the same answer the
    absent candle gets, which is the only answer that does not invent one.
    """
    out: dict[MarketKey, Decimal] = {}
    with localcontext(CONTEXT):
        for key, series in closes.items():
            old, new = series.get(old_open), series.get(new_open)
            if old is None or new is None or old <= 0:
                continue
            out[key] = (new / old - 1).quantize(RETURN_QUANTUM)
    return out


def compute_dispersion[MarketKey](
    closes: Mapping[MarketKey, Mapping[datetime, Decimal]],
    *,
    end_time: datetime,
    reference: MarketKey | None,
    universe_size: int,
    horizon_minutes: int = HORIZON_MINUTES,
    min_coverage: Decimal = MIN_COVERAGE,
) -> DispersionReading:
    """How far the median alt's 24 h return sits from the reference's.

    ``MarketKey`` is whatever the caller names a market by — a ``UUID`` in the
    job, a string in the tests. The arithmetic never looks at it, except to tell
    the reference apart from the alts.

    ``closes`` is ``market -> {open_time: close}`` over at least the two instants
    :func:`endpoint_open_times` names; anything else in it is ignored rather than
    trusted, so a caller that over-fetched cannot move the horizon by accident.

    ``reference`` is ``None`` when the universe has no reference market at all,
    which is the same answer as a reference whose closes are missing:
    :data:`REASON_REFERENCE_MISSING`.

    The refusal order is ``market_betas``'s, kept: no universe, then no
    reference, then no coverage, then no alts. The reference comes before
    coverage because "the thing everything is measured against did not answer" is
    the more specific fact, and it is the one an operator acts on.
    """
    old_open, new_open = endpoint_open_times(end_time, horizon_minutes)
    returns = _returns(closes, old_open=old_open, new_open=new_open)
    btc = returns.get(reference) if reference is not None else None
    alts = [value for key, value in returns.items() if key != reference]
    covered = len(returns)
    below = 0 if btc is None else sum(1 for value in alts if value < btc)
    with localcontext(CONTEXT):
        coverage = (
            Decimal(0)
            if universe_size <= 0
            else (Decimal(covered) / Decimal(universe_size)).quantize(RATIO_QUANTUM)
        )
        reason = _refusal(
            universe_size=universe_size,
            btc=btc,
            coverage=coverage,
            min_coverage=min_coverage,
            alts=alts,
        )
        middle = None if reason is not None else median(alts)
        share = (
            None
            if reason is not None
            else (Decimal(below) / Decimal(len(alts))).quantize(RATIO_QUANTUM)
        )
    return DispersionReading(
        end_time=end_time,
        horizon_minutes=horizon_minutes,
        universe_size=universe_size,
        covered=covered,
        alts_covered=len(alts),
        alts_below_btc=below,
        btc_r24h=None if reason is not None else btc,
        median_alt_r24h=middle,
        dispersion=None if reason is not None or middle is None or btc is None else middle - btc,
        share_below_btc=share,
        coverage=coverage,
        usable=reason is None,
        reason=reason,
    )


def _refusal(
    *,
    universe_size: int,
    btc: Decimal | None,
    coverage: Decimal,
    min_coverage: Decimal,
    alts: Sequence[Decimal],
) -> str | None:
    """The one reason this reading is not usable, or ``None``. Precedence only."""
    if universe_size <= 0:
        return REASON_EMPTY_UNIVERSE
    if btc is None:
        return REASON_REFERENCE_MISSING
    if coverage < min_coverage:
        return REASON_INSUFFICIENT_COVERAGE
    if not alts:
        return REASON_NO_ALTS
    return None
