"""Component/aggregate ``data_quality`` computation for markets.

Split out of ``services/markets.py`` (post-review fix pass on T1.4) to keep
that module under CLAUDE.md's 350-line file budget once the F1-F8 fixes were
added — the binding aggregate rule itself (precedence, required components)
is still documented verbatim in ``schemas/markets.py``'s module docstring;
this module only implements it.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from hunter_api.schemas.markets import ComponentQuality, ComponentStatusOut
from hunter_core.domain.market import DataQuality

CLOCK_SKEW_TOLERANCE_S = 2.0
"""A timestamp up to this far ahead of ``now`` is ordinary clock jitter and
may still read ``ok``; further ahead than this is a skewed producer clock,
reported ``stale`` regardless of how fresh a naive ``now - ts`` looks (F3).

(G6) Reduced from 5s to 2s: with a 10s ``stale_after_s`` (the M1 default),
a 5s tolerance let a frozen publication whose clock also drifted forward by
just under 5s keep reading ``ok`` for up to 15 real seconds (10s staleness
budget + 5s of tolerated skew) before ever going ``stale`` -- almost half
again the advertised threshold. The API and the worker that writes these
timestamps run on the same NTP-synced host, so clock drift between them
should be near zero; 2s is already generous headroom for jitter, not for a
genuinely stuck publisher.
"""


def spread_pct(bid: Decimal | None, ask: Decimal | None) -> Decimal | None:
    if bid is None or ask is None:
        return None
    mid = (bid + ask) / 2
    if mid <= 0:
        return None
    return (ask - bid) / mid


def age_ms(ts: datetime | None, now: datetime) -> int | None:
    """``now - ts`` in milliseconds, clamped at 0 (F3): a producer clock ahead
    of ``now`` must never surface as a negative age. Clamping alone would
    hide the skew, though -- :func:`component_status` still reflects it in
    ``quality``, this only keeps the *number* honest-looking.
    """
    if ts is None:
        return None
    return max(int((now - ts).total_seconds() * 1000), 0)


def component_status(
    ts: datetime | None, *, now: datetime, stale_after_s: float
) -> ComponentStatusOut:
    """(F3) ``age_s`` negative beyond ``CLOCK_SKEW_TOLERANCE_S`` (``ts`` more
    than the tolerance ahead of ``now``) is clock skew, not freshness -- the
    component reads ``stale`` even though a naive ``now - ts <= stale_after_s``
    check would pass (a negative number is always <= a positive threshold).
    """
    if ts is None:
        quality = ComponentQuality.ABSENT
    else:
        age_s = (now - ts).total_seconds()
        skewed_into_the_future = age_s < -CLOCK_SKEW_TOLERANCE_S
        fresh = not skewed_into_the_future and age_s <= stale_after_s
        quality = ComponentQuality.OK if fresh else ComponentQuality.STALE
    return ComponentStatusOut(ts=ts, age_ms=age_ms(ts, now), quality=quality)


def aggregate_data_quality(
    *, ticker: ComponentQuality, book: ComponentQuality, mark: ComponentQuality, has_gap: bool
) -> DataQuality:
    """Binding rule (M1.md "Decisões deste plano" + dialogue-M1.md rodada 4):
    ticker/book/mark are required, evaluated in this precedence. Individual
    component qualities are never overridden — a ``degraded`` market can
    still carry an ``ok`` ticker; this only picks the market-level badge.
    """
    required = (ticker, book, mark)
    if all(q is ComponentQuality.ABSENT for q in required):
        return DataQuality.UNAVAILABLE
    if has_gap or any(q is ComponentQuality.ABSENT for q in required):
        return DataQuality.DEGRADED
    if any(q is ComponentQuality.STALE for q in required):
        return DataQuality.STALE
    return DataQuality.OK
