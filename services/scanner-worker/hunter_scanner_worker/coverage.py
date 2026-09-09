"""Reading the collector's coverage proof — the other half of ``covered_until``.

The market-worker publishes an interval it can stand behind
(``hunter_market_worker.coverage``); this module turns it into the two fields a
``SourceEntry`` carries, per market, and refuses to invent either.

Three refusals worth naming, because each one costs a feature and each one is
the point:

- **no hash, or an expired one** — the collector is gone. Every trade window is
  ``insufficient_coverage``; no zero is published for a market nobody is
  watching;
- **an interval that ended** (``session_since`` empty) — the socket dropped and
  the collector said so. Same answer;
- **a symbol subscribed after the window starts** — coverage begins at the
  subscription, never at the session, so a market added to the universe two
  minutes ago cannot claim an hour of tape.

The scanner also takes its **evaluation cut** from here (:attr:`covered_until`).
A proof is by construction slightly behind the clock, and ``trades_between``
requires ``covered_until >= end`` where ``end`` is the cut itself: evaluating at
``now`` would make every window unprovable forever. Moving the cut back to the
proven instant is the only honest fix — ``MarketContext`` is defined as "one
market, as it was observable at ``as_of``".

**When the cut is read matters as much as what it says (T3.46f).** The proof
only certifies what the collector had already accepted when it was stamped, so
a cut read *before* a snapshot cannot possibly cover that snapshot: a book that
updates 5-10x/s has almost always moved on. :func:`refreshed_cut` is therefore
called after the hot state is in hand (``hunter_scanner_worker.context``), and
the later of the two published values wins. Nothing is anticipated by this:
both values are proofs the collector published about the past, and a snapshot
still ahead of the cut is refused exactly as before.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

from hunter_core.domain.enums import MarketType
from hunter_core.domain.types import ensure_utc, utcnow
from hunter_core.logging import get_logger
from hunter_core.redis import keys

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

logger = get_logger(__name__)

MAX_PROOF_AGE_S = 15.0
"""How stale the published proof may be before it stops proving anything. Well
above the 0.25 s stamp cadence (a loaded collector may skip a few) and well
under the key's own 60 s TTL, so the verdict does not depend on Redis expiry."""

_SESSION_SINCE = "session_since"
_COVERED_UNTIL = "covered_until"
_SYMBOL_PREFIX = "sym:"

CUT_FIELDS = (_SESSION_SINCE, _COVERED_UNTIL)
"""The only two fields :func:`read_cut` asks for.

Not ``HGETALL``: the re-read runs once per market per cycle, and the hash also
carries one ``sym:*`` field per subscribed symbol (200 of them today). Those
change when the universe changes, not between two reads a microsecond apart, so
the per-market read takes the interval and leaves the roster to the per-cycle
:func:`read_coverage`."""


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode()
    return str(value) if value is not None else ""


def _instant(value: Any) -> datetime | None:
    raw = _text(value)
    if not raw:
        return None
    try:
        return ensure_utc(datetime.fromisoformat(raw))
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class TapeCoverage:
    """One exchange's proven interval, as published by its collector."""

    session_since: datetime | None = None
    covered_until: datetime | None = None
    symbols: dict[str, datetime] | None = None
    fetched_at: datetime | None = None

    @property
    def live(self) -> bool:
        return self.session_since is not None and self.covered_until is not None

    def fresh(self, *, now: datetime | None = None, max_age_s: float = MAX_PROOF_AGE_S) -> bool:
        if not self.live or self.covered_until is None:
            return False
        moment = now or utcnow()
        return moment - self.covered_until <= timedelta(seconds=max_age_s)

    def for_symbol(self, symbol: str) -> tuple[datetime | None, datetime | None]:
        """``(covers_from, covered_until)`` for one market, or ``(None, None)``.

        ``covers_from`` is the later of the session and this symbol's own
        subscription: a market that joined mid-session was not being collected
        before it joined, whatever the session says.
        """
        if not self.live or self.session_since is None:
            return (None, None)
        since = (self.symbols or {}).get(symbol)
        if since is None:
            return (None, None)
        return (max(since, self.session_since), self.covered_until)

    def advanced_to(
        self, session_since: datetime | None, covered_until: datetime | None
    ) -> TapeCoverage:
        """This coverage with a **later** cut, when the re-read proves one (T3.46f).

        The re-read happens after the snapshots were taken, so its
        ``covered_until`` is a proof that already covers them. Three refusals,
        all of which keep the value this object was built with:

        - nothing published, or nothing to advance to;
        - a **different session**: the collector reconnected between the two
          reads, so this object's ``session_since`` (and the ``sym:*`` roster
          built from it) no longer describes the interval the new cut belongs
          to. Lifting the cut while keeping the old start would claim coverage
          across the gap the reconnection is;
        - a cut that did not move forward. ``covered_until`` is monotonic within
          a session, so this only happens on a stale replica read; taking the
          later of the two is the same rule either way.
        """
        if not self.live or session_since is None or covered_until is None:
            return self
        if session_since != self.session_since:
            return self
        if self.covered_until is not None and covered_until <= self.covered_until:
            return self
        return replace(self, covered_until=covered_until)


async def read_cut(
    redis: redis_asyncio.Redis,
    exchange: str,
    *,
    market_type: MarketType = MarketType.PERPETUAL,
) -> tuple[datetime | None, datetime | None]:
    """``(session_since, covered_until)`` as published *right now* (T3.46f).

    The cheap half of :func:`read_coverage`, for the one caller that needs the
    proof re-read after the data it certifies instead of before it.
    """
    key = keys.tape_coverage(exchange, market_type)
    values: list[Any] = list(await cast(Any, redis).hmget(key, list(CUT_FIELDS)) or ())
    if len(values) < len(CUT_FIELDS):
        return (None, None)
    return (_instant(values[0]), _instant(values[1]))


async def refreshed_cut(
    redis: redis_asyncio.Redis,
    coverage: TapeCoverage,
    *,
    exchange: str,
    market_type: MarketType = MarketType.PERPETUAL,
) -> TapeCoverage:
    """``coverage`` with the cut re-read from Redis, later value wins (T3.46f).

    A coverage that proves nothing is returned untouched: there is no cut to
    advance, and a market with no roster entry stays uncovered either way.
    """
    if not coverage.live:
        return coverage
    session_since, covered_until = await read_cut(redis, exchange, market_type=market_type)
    return coverage.advanced_to(session_since, covered_until)


async def read_coverage(
    redis: redis_asyncio.Redis,
    exchange: str,
    *,
    now: datetime | None = None,
    market_type: MarketType = MarketType.PERPETUAL,
) -> TapeCoverage:
    """Read ``mkt:{exchange}:coverage``. A missing key is no coverage, not an error.

    One hash per venue *and* market type (T3.0b), so the ``sym:*`` fields stay
    plain symbols and no collector's proof is ever read as another's.
    """
    key = keys.tape_coverage(exchange, market_type)
    fields: dict[Any, Any] = await cast(Any, redis).hgetall(key)
    if not fields:
        return TapeCoverage(fetched_at=now or utcnow())
    decoded = {_text(key): value for key, value in fields.items()}
    session_since = _instant(decoded.get(_SESSION_SINCE))
    covered_until = _instant(decoded.get(_COVERED_UNTIL))
    if session_since is None or covered_until is None:
        return TapeCoverage(fetched_at=now or utcnow())
    symbols: dict[str, datetime] = {}
    for key, value in decoded.items():
        if not key.startswith(_SYMBOL_PREFIX):
            continue
        moment = _instant(value)
        if moment is not None:
            symbols[key[len(_SYMBOL_PREFIX) :]] = moment
    return TapeCoverage(
        session_since=session_since,
        covered_until=covered_until,
        symbols=symbols,
        fetched_at=now or utcnow(),
    )


__all__ = [
    "CUT_FIELDS",
    "MAX_PROOF_AGE_S",
    "TapeCoverage",
    "read_coverage",
    "read_cut",
    "refreshed_cut",
]
