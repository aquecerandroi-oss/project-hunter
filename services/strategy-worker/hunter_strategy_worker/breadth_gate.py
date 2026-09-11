"""The breadth gate: may *this version* decide while *this much* is falling?

T3.77 / H-P8. The third rule of the eligibility envelope
(:mod:`hunter_strategy_worker.gate_policy`), after the hour of the day (T3.59)
and the hourly regime (T3.52). The rule the version *declares* — band, window and
series — is :mod:`hunter_strategy_worker.breadth_policy`; this module is what a
declared rule does to one bar.

**Where it comes from.** ``.claude/state/notes-D-P9.md`` §4 (KB-0083): at 22:08Z
on 2026-09-09, **194 of the 200 monitored perpetuals fell in the same minute**
(mean -3,71 %) while the BTC moved -0,20 %, and fifteen of the thirty-nine bets
of the family's worst hour died in that minute. The hypothesis is that the share
of the universe falling *before* a decision separates expectancy. It is a
**cell**, not a filter, until EXP-0027 says otherwise — this module is only the
door through which that hypothesis can be declared in front of the evidence
instead of behind it.

**It reads a persisted series, and that is the whole anti-look-ahead argument.**
``market_breadth`` (``0019``, PIPELINE §4b item 14) is written by the scanner, one
immutable row per closed minute, folded only from candles that closed at or
before that minute. The gate looks up **the row whose ``end_time`` is exactly
``source_bar_close`` in the series the policy names** and nothing else: no
tolerance, no "most recent before", no recomputation. Four consequences worth
stating:

- a replay applies the same rule to the same rows the live bar read, so the two
  populations remain comparable — which is the entire reason the value is a table
  and not a fold inside this function;
- a producer that is late or dead mutes the version (``breadth_unavailable``)
  instead of letting it decide on a value from three minutes ago. There is no
  staleness window to tune because there is no window at all;
- because the anchor is exact, this rule cannot be "almost right". It is right
  for the minute it names or it abstains;
- and since T3.88 the **series** is as exact as the minute: the version names
  ``breadth_v1`` or ``breadth_v2`` in its stored policy, and a build that changed
  its own default cannot re-point a pre-registered band at a different universe.
  A version pinned to ``breadth_v2`` whose producer only ever wrote ``breadth_v1``
  rows is muted, which is the fail-closed answer — never "the other series was
  close enough".

**The refusal reason is rounded to two decimals on purpose.** The ``ineligible``
histogram groups by this string, and a reason carrying four decimals would give
almost every refused bar its own bucket — a histogram with one row per bar
measures nothing. The exact value, unrounded, travels in the envelope's
provenance block, which is where a number is supposed to be exact.

**Everything unreadable is refused, never ignored.**
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from hunter_core.domain.types import ensure_utc
from hunter_strategy_worker.breadth_policy import (
    BREADTH_KEY,
    SUPPORTED_VERSIONS,
    SUPPORTED_WINDOWS,
    BreadthPolicy,
    breadth_clause,
    parse_breadth_policy,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "BREADTH_KEY",
    "BREADTH_REASON_PREFIX",
    "REASON_QUANTUM",
    "REASON_UNAVAILABLE",
    "SUPPORTED_VERSIONS",
    "SUPPORTED_WINDOWS",
    "BreadthGate",
    "BreadthPolicy",
    "BreadthRow",
    "breadth_clause",
    "evaluate_breadth_gate",
    "load_breadth_gate",
    "parse_breadth_policy",
]
"""The policy's own names are re-exported: the envelope (``gate_policy``) and the
variant CLI ask this module for "the breadth rule", and which file the parser
happens to live in is not their business."""

BREADTH_REASON_PREFIX = "breadth_gate"
REASON_UNAVAILABLE = "breadth_unavailable"
"""One word for every way the series fails to answer — no row for the minute, a
row the producer itself marked unusable (coverage below its floor), or no row in
*that series* at all. They are told apart by :attr:`BreadthGate.detail`, never by
a second reason grammar."""

REASON_QUANTUM = Decimal("0.01")
"""Two decimals in the refusal string, so ``ineligible`` stays a histogram."""


@dataclass(frozen=True, slots=True)
class BreadthRow:
    """The fields of a ``market_breadth`` row this gate looks at."""

    id: uuid.UUID
    end_time: datetime
    value: Decimal | None
    usable: bool
    reason: str | None
    covered: int
    universe_size: int


@dataclass(frozen=True, slots=True)
class BreadthGate:
    """The verdict for one (policy, cut): what was read, and what it decided."""

    eligible: bool
    value: Decimal | None
    row_id: uuid.UUID | None
    end_time: datetime | None
    detail: str
    """``allowed`` | ``refused`` | ``no_row`` | ``unusable``."""
    policy: BreadthPolicy
    series_reason: str | None = None
    """The producer's own word for an unusable row (``insufficient_coverage``,
    ``empty_universe``), carried through rather than restated: the gate must not
    invent a second diagnosis of a fact the producer already named."""

    @property
    def reason(self) -> str:
        """``breadth_gate:0.97`` on a refusal by value, ``breadth_unavailable``
        when the series could not answer. ``None`` is never a reason."""
        if self.value is None:
            return REASON_UNAVAILABLE
        return f"{BREADTH_REASON_PREFIX}:{self.value.quantize(REASON_QUANTUM)}"

    def to_jsonable(self) -> dict[str, Any]:
        """What the envelope's provenance block carries — the exact value, the
        row it came from and the band (and series) that let it through."""
        return {
            "eligible": self.eligible,
            "value": None if self.value is None else str(self.value),
            "row_id": None if self.row_id is None else str(self.row_id),
            "end_time": None if self.end_time is None else self.end_time.isoformat(),
            "detail": self.detail,
            "series_reason": self.series_reason,
            "policy": self.policy.to_body(),
        }


def evaluate_breadth_gate(
    policy: BreadthPolicy, row: BreadthRow | None, cut: datetime
) -> BreadthGate:
    """The verdict — pure, so the replay and a test decide it the same way."""
    if row is None:
        return BreadthGate(False, None, None, None, "no_row", policy)
    end = ensure_utc(row.end_time)
    if not row.usable or row.value is None:
        return BreadthGate(False, None, row.id, end, "unusable", policy, row.reason)
    allowed = policy.minimum <= row.value < policy.maximum
    return BreadthGate(allowed, row.value, row.id, end, "allowed" if allowed else "refused", policy)


_LOOKUP = text(
    "SELECT b.id, b.end_time, b.value, b.usable, b.reason, b.covered, b.universe_size "
    "  FROM market_breadth b JOIN exchanges e ON e.id = b.exchange_id "
    " WHERE e.code = :exchange AND b.breadth_version = :version "
    "   AND b.window_minutes = :window AND b.end_time = :cut"
)
"""One equality probe on ``uq_market_breadth_reading``'s index (after the venue's
id) — the unique key is the only index ``market_breadth`` carries, and its four
columns are exactly these four predicates, in this order (T3.77c).

Written as SQL rather than through the ORM for the reason ``regime_gate.load_gate``
gives for living outside ``repo.py``: ``end_time = :cut`` **is** the anchoring
rule, and a query that spelled it loosely would be a different gate. Since T3.88
``:version`` comes from the policy the version stored, so this probe cannot land
in a series the experiment did not name.
"""


async def load_breadth_gate(
    session: AsyncSession, policy: BreadthPolicy, *, cut: datetime, exchange: str
) -> BreadthGate:
    """Read the reading anchored exactly at ``cut`` for ``exchange`` and decide.

    ``exchange`` is the venue of the market being decided on: the universe that
    matters to a Binance perpetual is Binance's. The policy deliberately does not
    name a venue — a version that decides on two venues would otherwise have to
    pick one universe for both, which is a claim nobody has evidence for.

    The series, by contrast, **is** the policy's (``policy.version``): there is no
    ``version=`` parameter left to default, because a default here was exactly how
    a band could be silently re-pointed at another universe by a deploy.

    An unusable row is fetched, not filtered out in SQL, for ``load_gate``'s own
    reason: "the producer could not see the universe" and "nobody produced this
    minute" are different operator problems and must not arrive as one.
    """
    cut_utc = ensure_utc(cut)
    found = (
        await session.execute(
            _LOOKUP,
            {
                "exchange": exchange,
                "version": policy.version,
                "window": policy.window_m,
                "cut": cut_utc,
            },
        )
    ).first()
    row = (
        None
        if found is None
        else BreadthRow(
            id=found.id,
            end_time=found.end_time,
            value=found.value,
            usable=found.usable,
            reason=found.reason,
            covered=found.covered,
            universe_size=found.universe_size,
        )
    )
    return evaluate_breadth_gate(policy, row, cut_utc)
