"""Look-ahead check for the WIN rules: scrambling the future must not move a past decision.

For every plan a scan emits, every bar that ends **after** the plan's ``decided_at`` is
replaced by a bar with different prices; the plans decided at or before that instant must
come out identical. A rule that peeks at a later bar fails here — the test suite keeps a
deliberate cheat to prove the check bites.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from decimal import Decimal

from hunter_indicators.b3.bars import Bar
from hunter_indicators.b3.intraday_plan import TradePlan

Scan = Callable[[Sequence[Bar]], Sequence[TradePlan]]


def scramble(bar: Bar) -> Bar:
    """Same instant, different prices: +500 pts on even minutes, −500 on odd ones, range ×3."""
    shift = Decimal(500) if bar.start.minute % 2 == 0 else Decimal(-500)
    mid = bar.open + shift
    wide = (bar.high - bar.low) * 3 + Decimal(10)
    close = bar.close + shift
    return Bar(
        bar.start,
        bar.minutes,
        open=mid,
        high=max(mid, close) + wide,
        low=min(mid, close) - wide,
        close=close,
    )


def lookahead_violations(scan: Scan, bars: Sequence[Bar]) -> list[str]:
    """Identities of the plans whose past changed when the future was scrambled."""
    base = list(scan(bars))
    bad: list[str] = []
    for plan in base:
        cut = plan.decided_at
        future = [b if b.end <= cut else scramble(b) for b in bars]
        again = [q for q in scan(future) if q.decided_at <= cut]
        expected = [q for q in base if q.decided_at <= cut]
        if again != expected:
            bad.append(plan.identity())
    return bad
