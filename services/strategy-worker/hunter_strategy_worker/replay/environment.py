"""The two things a historical replay does not get from the world: a clock and a hot state.

T3.19b. The replay engine does **not** re-implement the live evaluation: it
calls :func:`hunter_strategy_worker.decide.evaluate_slot`, the same function the
consumer calls for a bar that just closed. What it has to supply are the two
seams that function reads from the outside world, because the outside world is
in the wrong instant:

- **the clock.** ``evaluate_slot`` already takes ``clock`` as a parameter for
  exactly this reason (its own docstring: "so a replay cohort (and a test) can
  place the bar relative to its own timeline"). :class:`ReplayClock` answers
  ``bar_close + lag``, so the staleness gate, ``plan_entry`` and
  ``confirm_or_lapse`` all see the bar as freshly closed. The clock never
  reaches the strategy — the observation is still cut at ``source_bar_close``,
  which is what forbids look-ahead;

- **the hot state.** Redis holds the minutes the market-worker has not flushed
  yet and the newest derivatives reading; for a bar that closed days ago both
  are empty *by construction* (``hot_state.read_tail`` drops everything at or
  after the cut). :class:`ReplayHotState` answers "nothing" to the three calls
  the live path makes, so a replay reads only the durable series — which is the
  whole point of replaying over persisted candles.

The third call, ``eligibility.universe_changed_after``, is answered "no change"
and that is **a declared assumption, not a proof**: the monitored set is
overwritten in place and the schema keeps no per-bar membership history, so a
replay cannot know whether a market was in the universe a week ago. It reads
``markets.is_monitored`` **as of the run** and says so — the envelope's
``provenance.eligibility_observed_at`` carries the run's wall clock, hours or
days after the bar. Answering the probe honestly (with the live stream, where
every historical bar is behind some universe change) would make every replayed
bar ``unavailable`` and there would be no replay at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

from hunter_core.domain.types import ensure_utc

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

__all__ = [
    "REPLAY_DECISION_LAG_S",
    "ReplayClock",
    "ReplayHotState",
    "as_redis",
]

REPLAY_DECISION_LAG_S = 2
"""Seconds between a bar's close and the replayed decision on it.

The live lag is whatever the worker took (stream delivery plus evaluation);
a replay has to pick one, and the number is *not* free: ``plan_entry`` chooses
the first 1m open strictly after ``decision_at``, so any lag under 60 s puts the
entry at ``bar_close + 1min`` — the same bar the live path picks on a healthy
day — and ``delay_s`` is 60, comfortably inside the frozen
``max_entry_delay_s`` (120 s in both v1 strategies). A lag of 60 s or more
would move the entry a minute later and quietly change the population; a lag of
zero would make ``decision_at == bar_close``, which no real run ever achieves.

Two seconds is the assumption, it is written into every replay's ledger row,
and it is the only place a replayed ``no_entry: late`` could come from — so a
replay produces *fewer* late refusals than the live path, and the two
populations are compared knowing that (notes-T3.19b, "premissas numéricas").
"""


@dataclass(frozen=True, slots=True)
class ReplayClock:
    """``bar_close + lag``, frozen for the whole evaluation of one bar.

    Deterministic on purpose: ``evaluate_slot`` reads the clock twice (the
    staleness gate and ``decision_at``) and ``confirm_or_lapse`` a third time,
    and a replay that answered a moving wall clock could emit two different
    ``entry_bar_open`` for the same bar on two runs. Same bar, same answer.
    """

    bar_close: datetime
    lag_s: int = REPLAY_DECISION_LAG_S

    def __call__(self) -> datetime:
        return ensure_utc(self.bar_close) + timedelta(seconds=self.lag_s)


class ReplayHotState:
    """The empty answers a historical cut would have got from Redis anyway.

    Only the three calls the live decision path makes are implemented
    (``xrevrange`` for the universe probe, ``lrange`` for the candle tail,
    ``hgetall`` for the derivatives hash). Anything else raises
    ``AttributeError`` rather than silently answering ``None``: a new Redis read
    on the live path must be a deliberate decision here too, not an empty result
    a replay invented.
    """

    __slots__ = ()

    async def xrevrange(self, *_args: Any, **_kwargs: Any) -> list[Any]:
        """No ``market.universe.changed`` entry — see the module docstring."""
        return []

    async def lrange(self, *_args: Any, **_kwargs: Any) -> list[bytes]:
        """No unflushed tail: every candle before the cut is already durable."""
        return []

    async def hgetall(self, *_args: Any, **_kwargs: Any) -> dict[bytes, bytes]:
        """No live derivatives reading; funding and OI come from Postgres."""
        return {}


def as_redis(hot_state: ReplayHotState) -> redis_asyncio.Redis:
    """The stand-in, typed as the client the live signature declares.

    A cast and not a subclass: ``redis.asyncio.Redis`` carries hundreds of
    commands a replay must never be able to call by accident (this object can
    read three keys' worth of nothing and write none). The cast is the honest
    spelling of "this fills the same hole", and every call it can service is
    enumerated above.
    """
    return cast("redis_asyncio.Redis", hot_state)
