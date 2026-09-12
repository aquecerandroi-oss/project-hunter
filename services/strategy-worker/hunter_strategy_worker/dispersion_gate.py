"""The dispersion gate: may *this version* decide while the alts are *this* far
from the BTC?

T3.90 / H-P18. The fourth rule of the eligibility envelope
(:mod:`hunter_strategy_worker.gate_policy`), after the hour of the day (T3.59), the
hourly regime (T3.52) and the universe amplitude (T3.77). The rule the version
*declares* — band and series — is :mod:`hunter_strategy_worker.dispersion_policy`;
this module is what a declared rule does to one bar.

**Where it comes from.** The plantão runs of 2026-09-10 and 2026-09-11: the median
24 h return of the sixteen markets at **-4,80 %** and **-3,85 %** with the **BTC**
at **-1,50 %** and **-1,30 %** — the alts selling off while the reference barely
moved. The hypothesis is that this *discordância*, read before a decision,
separates expectancy. It is a **cell**, not a filter, until EXP-0029 says
otherwise; this module is only the door through which that hypothesis can be
declared in front of the evidence instead of behind it.

**It reads a persisted series, and that is the whole anti-look-ahead argument.**
``market_dispersion`` (``0020``, PIPELINE §4b item 16) is written by the scanner,
one immutable row per closed minute, folded only from candles that closed at or
before that minute. The gate looks up **the row whose ``end_time`` is exactly
``source_bar_close`` in the series the policy names** and nothing else: no
tolerance, no "most recent before", no recomputation. Four consequences worth
stating:

- a replay applies the same rule to the same rows the live bar read, so the two
  populations remain comparable — the entire reason the value is a table and not a
  fold inside this function;
- a producer that is late or dead mutes the version (``dispersion_unavailable``)
  instead of letting it decide on a value from three minutes ago. There is no
  staleness window to tune because there is no window at all;
- because the anchor is exact, this rule cannot be "almost right": it is right for
  the minute it names or it abstains;
- and the **series** is as exact as the minute. The version names
  ``dispersion_24h_v1`` in its stored policy, and since the horizon, the universe
  and the reference market all live inside that string, a build that changed any of
  them could not answer a pre-registered band with a different number — it would
  have to write a version the policy does not name, and a policy naming a series
  this build cannot read is refused at parse time.

**The refusal reason is rounded to two decimals on purpose.** The ``ineligible``
histogram groups by this string, and a reason carrying six decimals would give
almost every refused bar its own bucket — a histogram with one row per bar measures
nothing. Two decimals is ~30 buckets across everything ever measured. The exact
value, unrounded, travels in the envelope's provenance block, which is where a
number is supposed to be exact.

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
from hunter_strategy_worker.dispersion_policy import (
    DISPERSION_KEY,
    SUPPORTED_VERSIONS,
    DispersionPolicy,
    dispersion_clause,
    parse_dispersion_policy,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "DISPERSION_KEY",
    "DISPERSION_REASON_PREFIX",
    "REASON_QUANTUM",
    "REASON_UNAVAILABLE",
    "SUPPORTED_VERSIONS",
    "DispersionGate",
    "DispersionPolicy",
    "DispersionRow",
    "dispersion_clause",
    "evaluate_dispersion_gate",
    "load_dispersion_gate",
    "parse_dispersion_policy",
]
"""The policy's own names are re-exported: the envelope (``gate_policy``) and the
variant CLI ask this module for "the dispersion rule", and which file the rule
happens to live in is not their business."""

DISPERSION_REASON_PREFIX = "dispersion_gate"
REASON_UNAVAILABLE = "dispersion_unavailable"
"""One word for every way the series fails to answer — no row for the minute, a row
the producer itself marked unusable (coverage below its floor, or the reference
without a 24 h return), or no row in *that series* at all. They are told apart by
:attr:`DispersionGate.detail` and by the producer's own ``series_reason``, never by
a second reason grammar."""

REASON_QUANTUM = Decimal("0.01")
"""Two decimals in the refusal string, so ``ineligible`` stays a histogram."""


@dataclass(frozen=True, slots=True)
class DispersionRow:
    """The fields of a ``market_dispersion`` row this gate looks at."""

    id: uuid.UUID
    end_time: datetime
    dispersion: Decimal | None
    usable: bool
    reason: str | None
    covered: int
    universe_size: int


@dataclass(frozen=True, slots=True)
class DispersionGate:
    """The verdict for one (policy, cut): what was read, and what it decided."""

    eligible: bool
    value: Decimal | None
    row_id: uuid.UUID | None
    end_time: datetime | None
    detail: str
    """``allowed`` | ``refused`` | ``no_row`` | ``unusable``."""
    policy: DispersionPolicy
    series_reason: str | None = None
    """The producer's own word for an unusable row (``insufficient_coverage``,
    ``btc_missing``, ``empty_universe``, ``no_alts``), carried through rather than
    restated: the gate must not invent a second diagnosis of a fact the producer
    already named."""

    @property
    def reason(self) -> str:
        """``dispersion_gate:-0.08`` on a refusal by value,
        ``dispersion_unavailable`` when the series could not answer. ``None`` is
        never a reason."""
        if self.value is None:
            return REASON_UNAVAILABLE
        return f"{DISPERSION_REASON_PREFIX}:{self.value.quantize(REASON_QUANTUM)}"

    def to_jsonable(self) -> dict[str, Any]:
        """What the envelope's provenance block carries — the exact value, the row
        it came from and the band (and series) that let it through."""
        return {
            "eligible": self.eligible,
            "value": None if self.value is None else str(self.value),
            "row_id": None if self.row_id is None else str(self.row_id),
            "end_time": None if self.end_time is None else self.end_time.isoformat(),
            "detail": self.detail,
            "series_reason": self.series_reason,
            "policy": self.policy.to_body(),
        }


def evaluate_dispersion_gate(
    policy: DispersionPolicy, row: DispersionRow | None, cut: datetime
) -> DispersionGate:
    """The verdict — pure, so the replay and a test decide it the same way."""
    if row is None:
        return DispersionGate(False, None, None, None, "no_row", policy)
    end = ensure_utc(row.end_time)
    if not row.usable or row.dispersion is None:
        return DispersionGate(False, None, row.id, end, "unusable", policy, row.reason)
    allowed = policy.minimum <= row.dispersion < policy.maximum
    return DispersionGate(
        allowed, row.dispersion, row.id, end, "allowed" if allowed else "refused", policy
    )


_LOOKUP = text(
    "SELECT d.id, d.end_time, d.dispersion, d.usable, d.reason, d.covered, d.universe_size "
    "  FROM market_dispersion d JOIN exchanges e ON e.id = d.exchange_id "
    " WHERE e.code = :exchange AND d.dispersion_version = :version AND d.end_time = :cut"
)
"""One equality probe on ``uq_market_dispersion_reading``'s index (after the venue's
id) — the unique key is the only index ``market_dispersion`` carries, and its three
columns are exactly these three predicates, in this order.

Written as SQL rather than through the ORM for the reason ``regime_gate.load_gate``
gives for living outside ``repo.py``: ``end_time = :cut`` **is** the anchoring rule,
and a query that spelled it loosely would be a different gate. ``:version`` comes
from the policy the version stored, so this probe cannot land in a series the
experiment did not name.
"""


async def load_dispersion_gate(
    session: AsyncSession, policy: DispersionPolicy, *, cut: datetime, exchange: str
) -> DispersionGate:
    """Read the reading anchored exactly at ``cut`` for ``exchange`` and decide.

    ``exchange`` is the venue of the market being decided on: the universe that
    matters to a Binance perpetual is Binance's, and so is the BTC it is compared
    with. The policy deliberately does not name a venue — a version that decides on
    two venues would otherwise have to pick one universe for both, which is a claim
    nobody has evidence for.

    The series, by contrast, **is** the policy's (``policy.version``): there is no
    ``version=`` parameter left to default, because a default there is exactly how a
    band gets silently re-pointed at another universe by a deploy (T3.88's finding
    on ``breadth``, applied before this series has a single row).

    An unusable row is fetched, not filtered out in SQL, for ``load_gate``'s own
    reason: "the producer could not see the universe" and "nobody produced this
    minute" are different operator problems and must not arrive as one.
    """
    cut_utc = ensure_utc(cut)
    found = (
        await session.execute(
            _LOOKUP, {"exchange": exchange, "version": policy.version, "cut": cut_utc}
        )
    ).first()
    row = (
        None
        if found is None
        else DispersionRow(
            id=found.id,
            end_time=found.end_time,
            dispersion=found.dispersion,
            usable=found.usable,
            reason=found.reason,
            covered=found.covered,
            universe_size=found.universe_size,
        )
    )
    return evaluate_dispersion_gate(policy, row, cut_utc)
