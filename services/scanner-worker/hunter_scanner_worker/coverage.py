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
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

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


async def read_coverage(
    redis: redis_asyncio.Redis, exchange: str, *, now: datetime | None = None
) -> TapeCoverage:
    """Read ``mkt:{exchange}:coverage``. A missing key is no coverage, not an error."""
    fields: dict[Any, Any] = await cast(Any, redis).hgetall(keys.tape_coverage(exchange))
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


__all__ = ["MAX_PROOF_AGE_S", "TapeCoverage", "read_coverage"]
