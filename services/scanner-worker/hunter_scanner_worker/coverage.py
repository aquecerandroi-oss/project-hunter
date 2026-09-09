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

**The aggregate ``min`` answers the wrong question for one market (T3.46g).**
Correct for "is the whole exchange covered", pessimistic for "is *this*
market": a symbol on a fresh shard was bounded by whichever sibling lagged
most. Its owning shard's own record already carries its own ``until``
(``mkt:{exchange}:coverage:shards``), so :func:`refreshed_cut` routes a mapped
symbol there — mapping and ``until`` read from the *same* live records in the
same call, so neither can describe a topology already moved on. Zero or
two-plus live claimants (a rebalance in flight) keeps the aggregate ``min``
instead — conservative, never a guess at which claimant is right.
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

_SHARD_PARTS = ("since", "until", "ts", "syms")
"""``hunter_market_worker.coverage_publish``'s own field names, duplicated like
``_SESSION_SINCE``/``_COVERED_UNTIL`` above — never imported directly."""

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


def _shard_instant(value: Any) -> datetime | None:
    """A shard field is ``epoch|iso`` (T3.46g); only the iso half is read."""
    raw = _text(value)
    if "|" not in raw:
        return None
    return _instant(raw.partition("|")[2])


def _shard_symbols(value: Any) -> frozenset[str]:
    """The plain names out of a shard's own ``name\\tepoch\\tiso`` roster."""
    raw = _text(value)
    if not raw:
        return frozenset()
    return frozenset(line.partition("\t")[0] for line in raw.split("\n") if line)


def _live_shard_cuts(
    fields: dict[str, str], *, now: datetime, max_age_s: float
) -> tuple[dict[str, str], dict[str, tuple[datetime | None, datetime | None]]]:
    """``(symbol -> owning shard id, shard id -> its own (since, until))``,
    both from the *same* ``HGETALL`` (mandatory reserve: one consistent
    snapshot, never a cached mapping paired with a fresher proof). A record
    older than ``max_age_s`` is dropped, same budget as
    ``coverage_publish.SHARD_RECORD_TTL_S``."""
    raw: dict[str, dict[str, str]] = {}
    for field, value in fields.items():
        shard_id, sep, part = field.rpartition(":")
        if not sep or part not in _SHARD_PARTS:
            continue
        raw.setdefault(shard_id, {})[part] = value
    cuts: dict[str, tuple[datetime | None, datetime | None]] = {}
    claims: dict[str, list[str]] = {}
    for shard_id, parts in raw.items():
        stamped = _text(parts.get("ts"))
        try:
            age = now.timestamp() - float(stamped)
        except ValueError:
            continue
        if age > max_age_s:
            continue
        cuts[shard_id] = (_shard_instant(parts.get("since")), _shard_instant(parts.get("until")))
        for symbol in _shard_symbols(parts.get("syms")):
            claims.setdefault(symbol, []).append(shard_id)
    # Exactly one live claimant or none of it -- see the module docstring.
    owner = {symbol: shards[0] for symbol, shards in claims.items() if len(shards) == 1}
    return owner, cuts


@dataclass(frozen=True, slots=True)
class TapeCoverage:
    """One exchange's proven interval, as published by its collector."""

    session_since: datetime | None = None
    covered_until: datetime | None = None
    symbols: dict[str, datetime] | None = None
    fetched_at: datetime | None = None
    shard_owner: dict[str, str] | None = None
    """T3.46g: ``symbol -> its one live owning shard``, or absent."""
    shard_cuts: dict[str, tuple[datetime | None, datetime | None]] | None = None
    """T3.46g: ``shard id -> that shard's own (since, until)``, see :meth:`shard_baseline`."""

    @property
    def live(self) -> bool:
        return self.session_since is not None and self.covered_until is not None

    def shard_baseline(self, symbol: str) -> TapeCoverage | None:
        """This coverage through ``symbol``'s **owning shard** (T3.46g), or
        ``None`` with no single live claimant. Roster (:attr:`symbols`) stays
        the aggregate's -- a subscription instant outlives shard ownership."""
        if not self.shard_owner or not self.shard_cuts:
            return None
        shard_id = self.shard_owner.get(symbol)
        cut = self.shard_cuts.get(shard_id) if shard_id is not None else None
        if cut is None:
            return None
        since, until = cut
        return replace(self, session_since=since, covered_until=until)

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


async def read_shard_cut(
    redis: redis_asyncio.Redis,
    exchange: str,
    shard_id: str,
    *,
    market_type: MarketType = MarketType.PERPETUAL,
) -> tuple[datetime | None, datetime | None]:
    """``shard_id``'s own ``(session_since, covered_until)`` (T3.46g) — the
    shard-scoped twin of :func:`read_cut`, same cost, routed to ``:shards``."""
    key = f"{keys.tape_coverage(exchange, market_type)}:shards"
    fields = [f"{shard_id}:since", f"{shard_id}:until"]
    values: list[Any] = list(await cast(Any, redis).hmget(key, fields) or ())
    if len(values) < 2:
        return (None, None)
    return (_shard_instant(values[0]), _shard_instant(values[1]))


async def refreshed_cut(
    redis: redis_asyncio.Redis,
    coverage: TapeCoverage,
    *,
    exchange: str,
    symbol: str,
    market_type: MarketType = MarketType.PERPETUAL,
) -> TapeCoverage:
    """``coverage`` with the cut re-read from Redis, later value wins (T3.46f).
    Proves-nothing input is returned untouched. T3.46g: a symbol mapped to one
    live shard (:meth:`TapeCoverage.shard_baseline`) re-reads *that shard's*
    record instead, never lower than the aggregate ``min`` it bounds from
    above; unmapped keeps the old, aggregate-only path."""
    if not coverage.live:
        return coverage
    baseline = coverage.shard_baseline(symbol)
    if baseline is not None:
        shard_id = cast(dict[str, str], coverage.shard_owner)[symbol]
        since, until = await read_shard_cut(redis, exchange, shard_id, market_type=market_type)
        floor = baseline.advanced_to(since, until).covered_until
        if floor is not None and (coverage.covered_until is None or floor > coverage.covered_until):
            return replace(coverage, covered_until=floor)
        return coverage
    session_since, covered_until = await read_cut(redis, exchange, market_type=market_type)
    return coverage.advanced_to(session_since, covered_until)


async def _read_shard_map(
    redis: redis_asyncio.Redis, exchange: str, *, market_type: MarketType, now: datetime
) -> tuple[dict[str, str], dict[str, tuple[datetime | None, datetime | None]]]:
    """One ``HGETALL`` of ``:shards`` per cycle (T3.46g), parsed into the
    owner map and per-shard cuts :func:`refreshed_cut` routes to."""
    shards_key = f"{keys.tape_coverage(exchange, market_type)}:shards"
    fields: dict[Any, Any] = await cast(Any, redis).hgetall(shards_key)
    decoded = {_text(field): _text(value) for field, value in fields.items()}
    return _live_shard_cuts(decoded, now=now, max_age_s=MAX_PROOF_AGE_S)


async def read_coverage(
    redis: redis_asyncio.Redis,
    exchange: str,
    *,
    now: datetime | None = None,
    market_type: MarketType = MarketType.PERPETUAL,
) -> TapeCoverage:
    """Read ``mkt:{exchange}:coverage``. A missing key is no coverage, not an
    error. One hash per venue *and* market type (T3.0b). Also reads
    ``:shards`` once (T3.46g) for :func:`refreshed_cut`'s per-symbol routing."""
    moment = now or utcnow()
    key = keys.tape_coverage(exchange, market_type)
    fields: dict[Any, Any] = await cast(Any, redis).hgetall(key)
    shard_owner, shard_cuts = await _read_shard_map(
        redis, exchange, market_type=market_type, now=moment
    )
    if not fields:
        return TapeCoverage(fetched_at=moment, shard_owner=shard_owner, shard_cuts=shard_cuts)
    decoded = {_text(key): value for key, value in fields.items()}
    session_since = _instant(decoded.get(_SESSION_SINCE))
    covered_until = _instant(decoded.get(_COVERED_UNTIL))
    if session_since is None or covered_until is None:
        return TapeCoverage(fetched_at=moment, shard_owner=shard_owner, shard_cuts=shard_cuts)
    symbols: dict[str, datetime] = {}
    for key, value in decoded.items():
        if not key.startswith(_SYMBOL_PREFIX):
            continue
        instant = _instant(value)
        if instant is not None:
            symbols[key[len(_SYMBOL_PREFIX) :]] = instant
    return TapeCoverage(
        session_since=session_since,
        covered_until=covered_until,
        symbols=symbols,
        fetched_at=moment,
        shard_owner=shard_owner,
        shard_cuts=shard_cuts,
    )


__all__ = [
    "CUT_FIELDS",
    "MAX_PROOF_AGE_S",
    "TapeCoverage",
    "read_coverage",
    "read_cut",
    "read_shard_cut",
    "refreshed_cut",
]
