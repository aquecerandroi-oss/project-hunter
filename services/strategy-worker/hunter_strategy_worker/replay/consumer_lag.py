"""The live decision consumer's own backlog, read straight from Redis (T3.74b).

Split from :mod:`.budget` for the same reason :mod:`hunter_strategy_worker.roster`
was split from ``catalogue``: one cohesive read (parse ``XINFO GROUPS``, find one
entry, pull its ``lag``) with its own failure modes, kept out of the gate that
consumes it so ``budget.py`` stays under the 350-line budget.

``lag`` (Redis 7+) is entries the stream has added minus entries the group has
read — the backlog the group has not even picked up yet. It is independent of
``outbox_lag_s`` (:mod:`hunter_strategy_worker.heartbeat`), which measures what
happens *after* a decision is already made; T3.74 found the live lane's worst
measured decision lag (125 s+) with ``outbox_lag_s`` reading ``0.0`` throughout
(notes-T3.74.md §3), so this is a second, independent signal, not a rename.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from hunter_core.events.streams import Streams
from hunter_core.logging import get_logger
from hunter_strategy_worker.config import CONSUMER_GROUP

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

logger = get_logger(__name__)

LIVE_CONSUMER_STREAM = Streams.MARKET_CANDLES_CLOSED
LIVE_CONSUMER_GROUP = CONSUMER_GROUP

__all__ = [
    "LIVE_CONSUMER_GROUP",
    "LIVE_CONSUMER_STREAM",
    "group_lag",
    "topology_group_lag",
]


def _find_lag(groups: list[dict[Any, Any]], name: str) -> int | None:
    """The ``lag`` of the entry named ``name``, comparing ``name`` against
    whichever type Redis sent it as (``str`` or ``bytes``) instead of decoding
    an *other* group's name — a group this gate never asked about may carry
    anything, and decoding it just to reject it is a needless way to raise."""
    wanted = (name, name.encode("utf-8"))
    for entry in groups:
        fields = {(k.decode() if isinstance(k, bytes) else str(k)): v for k, v in entry.items()}
        if fields.get("name") not in wanted:
            continue
        raw_lag = fields.get("lag")
        if raw_lag is None:
            return None
        try:
            return int(raw_lag)
        except (TypeError, ValueError):
            return None
    return None


async def group_lag(
    redis: redis_asyncio.Redis,
    *,
    stream: str = LIVE_CONSUMER_STREAM,
    group: str = LIVE_CONSUMER_GROUP,
) -> int | None:
    """``lag`` for ``group`` on ``stream``, or ``None`` when it cannot be read.

    ``None`` covers four cases the caller must treat alike (fail closed, never
    as zero): the ``XINFO GROUPS`` call itself failing, ``group`` not existing on
    ``stream`` at all, a group entry with no ``lag`` field or an explicit
    ``lag: null`` (both mean Redis cannot compute it, e.g. a group whose first
    entry was trimmed by ``MAXLEN`` before it read anything — a group Redis
    cannot name is not proof the group is fine, it is proof nothing was
    established), and — Astra, T3.74b review — a parsing failure on some
    *other* group's entry (an un-decodable name), which must not raise past
    this function and crash the gate over a group nobody asked about.
    """
    try:
        groups: list[dict[Any, Any]] = await cast("Any", redis).xinfo_groups(stream)
        lag = _find_lag(groups, group)
    except Exception:
        logger.warning("replay_consumer_lag_unreadable", stream=stream)
        return None
    if lag is None:
        logger.warning("replay_consumer_lag_unreadable", stream=stream)
    return lag


def _decode(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _group_names(groups: list[dict[Any, Any]]) -> list[str]:
    """Every group name present on the stream, decoded defensively.

    ``errors="replace"`` (never a raised ``UnicodeDecodeError``): a group this
    gate never asked about can carry anything, and the whole point of orphan
    detection is to *notice* stray groups, not to crash trying to read one --
    same principle ``_find_lag`` already applies by comparing raw bytes."""
    names: list[str] = []
    for entry in groups:
        fields = {_decode(k): v for k, v in entry.items()}
        name = fields.get("name")
        if name is not None:
            names.append(_decode(name))
    return names


def find_orphan_groups(
    groups: list[dict[Any, Any]], expected: tuple[str, ...], *, prefix: str
) -> tuple[str, ...]:
    """Every group on the stream whose name starts with ``prefix`` (this
    lane's own consumer-group family) but is not one of ``expected`` (T3.87).

    The bug this answers: ``strategy-worker.shadow`` (the pre-shard, unsuffixed
    name) kept existing on ``market.candles.closed`` after ``STRATEGY_SHARDS``
    sharded the live worker into ``strategy-worker.shadow.{i}of{N}`` groups --
    nobody read it or advanced it, so its ``lag`` only ever grew (50 000 and
    climbing, notes-T3.84.md §3.2), and the old gate used exactly that literal
    as *the* live group, refusing every replay forever. A group outside the
    current topology is never counted toward the gate's own lag reading (it is
    not live, so its backlog says nothing about the live lane's health) --
    only named here so an operator can ``XGROUP DESTROY`` it."""
    return tuple(
        name for name in _group_names(groups) if name.startswith(prefix) and name not in expected
    )


async def topology_group_lag(
    redis: redis_asyncio.Redis,
    *,
    stream: str = LIVE_CONSUMER_STREAM,
    groups: tuple[str, ...],
    prefix: str = LIVE_CONSUMER_GROUP,
) -> tuple[int | None, tuple[str, ...]]:
    """The worst (maximum) ``lag`` across every group in ``groups``, or
    ``None`` when any of them is unreadable (fail closed, same rule
    :func:`group_lag` already applies to the single-group case) -- plus every
    orphan group found on the stream (T3.87, :func:`find_orphan_groups`).

    One ``XINFO GROUPS`` call covers every shard's own group: the whole
    topology shares one stream, so reading it once and looking up each
    expected name is cheaper than one round trip per shard.
    """
    try:
        raw_groups: list[dict[Any, Any]] = await cast("Any", redis).xinfo_groups(stream)
    except Exception:
        logger.warning("replay_consumer_lag_unreadable", stream=stream)
        return None, ()
    lags: list[int] = []
    for group in groups:
        lag = _find_lag(raw_groups, group)
        if lag is None:
            logger.warning("replay_consumer_lag_unreadable", stream=stream, group=group)
            return None, ()
        lags.append(lag)
    return max(lags), find_orphan_groups(raw_groups, groups, prefix=prefix)
