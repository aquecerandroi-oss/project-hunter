"""Reading the collector's proof, and what it does to the evaluation cut.

Every assertion here is about a *refusal*. The scanner is allowed to publish a
trade window only when the collector proved it stayed connected through it, and
each of these cases is a way that proof can be absent -- with the feature it
costs stated in the test name, because "insufficient_coverage" is the honest
answer and not a bug to be worked around.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast

from hunter_core.redis import keys
from hunter_indicators.features import read_hot_state
from hunter_indicators.features.hotstate import AFTER_CUT, decode_book
from hunter_scanner_worker.context import MAX_CUT_LAG_S, build_market_context, evaluation_cut
from hunter_scanner_worker.coverage import TapeCoverage, read_coverage, refreshed_cut

from .builders import EXCHANGE, SYMBOL, FakeHotState, book_payload

SESSION = datetime(2026, 9, 6, 12, 0, 0, tzinfo=UTC)


def _at(seconds: float) -> datetime:
    return SESSION + timedelta(seconds=seconds)


class FakeRedis:
    def __init__(self, hashes: dict[str, dict[str, str]] | None = None) -> None:
        self.hashes = hashes or {}

    async def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.hashes.get(key, {}))

    async def hmget(self, key: str, fields: list[str]) -> list[str | None]:
        stored = self.hashes.get(key, {})
        return [stored.get(field) for field in fields]


def _published(**fields: str) -> Any:
    return FakeRedis({keys.tape_coverage("binance"): fields})


def _shard_stamp(moment: datetime) -> str:
    return f"{moment.timestamp()}|{moment.isoformat()}"


def _shard_record(
    shard_id: str, *, since: datetime, until: datetime, ts: datetime, symbols: dict[str, datetime]
) -> dict[str, str]:
    """One shard's own fields, wire-identical to
    ``hunter_market_worker.coverage_publish``'s Lua script (T3.46g)."""
    syms = "\n".join(
        f"{sym}\t{when.timestamp()}\t{when.isoformat()}" for sym, when in symbols.items()
    )
    return {
        f"{shard_id}:since": _shard_stamp(since),
        f"{shard_id}:until": _shard_stamp(until),
        f"{shard_id}:ts": str(ts.timestamp()),
        f"{shard_id}:syms": syms,
    }


async def test_a_missing_hash_is_no_coverage_not_an_error() -> None:
    coverage = await read_coverage(FakeRedis(), "binance")  # type: ignore[arg-type]

    assert coverage.live is False
    assert coverage.for_symbol("BTCUSDT") == (None, None)


async def test_an_ended_interval_stops_proving_anything() -> None:
    redis = _published(session_since="", covered_until="", **{"sym:BTCUSDT": SESSION.isoformat()})

    coverage = await read_coverage(redis, "binance")

    # The collector is there and said its interval ended: a scanner that kept
    # reading the last ``covered_until`` would publish windows over an outage.
    assert coverage.live is False


async def test_a_symbol_subscribed_mid_session_is_covered_from_its_subscription() -> None:
    redis = _published(
        session_since=SESSION.isoformat(),
        covered_until=_at(600).isoformat(),
        **{"sym:BTCUSDT": SESSION.isoformat(), "sym:SOLUSDT": _at(300).isoformat()},
    )

    coverage = await read_coverage(redis, "binance")

    assert coverage.for_symbol("BTCUSDT") == (SESSION, _at(600))
    # Not the session: this market was not being collected for the first five
    # minutes, so an hour-long window over it is unprovable.
    assert coverage.for_symbol("SOLUSDT") == (_at(300), _at(600))


async def test_a_symbol_outside_the_subscription_has_no_coverage() -> None:
    redis = _published(
        session_since=SESSION.isoformat(),
        covered_until=_at(600).isoformat(),
        **{"sym:BTCUSDT": SESSION.isoformat()},
    )

    coverage = await read_coverage(redis, "binance")

    assert coverage.for_symbol("DOGEUSDT") == (None, None)


def test_the_cut_moves_onto_the_proof_instead_of_the_clock() -> None:
    coverage = TapeCoverage(
        session_since=SESSION, covered_until=_at(59.5), symbols={"BTCUSDT": SESSION}
    )

    as_of, covers_from, covered_until = evaluation_cut(coverage, "BTCUSDT", now=_at(60))

    # ``trades_between`` requires ``covered_until >= end`` and ``end`` is the cut
    # itself. Evaluating at the clock would make every window unprovable
    # forever, so the cut is the proven instant.
    assert as_of == _at(59.5)
    assert (covers_from, covered_until) == (SESSION, _at(59.5))


def test_a_stale_proof_does_not_drag_the_cut_into_the_past() -> None:
    coverage = TapeCoverage(
        session_since=SESSION, covered_until=_at(0), symbols={"BTCUSDT": SESSION}
    )
    now = _at(MAX_CUT_LAG_S + 1)

    as_of, covers_from, covered_until = evaluation_cut(coverage, "BTCUSDT", now=now)

    # A collector that stopped stamping must not freeze the whole scanner at the
    # last instant it proved: evaluate now, and let the trade windows refuse
    # themselves with a reason.
    assert as_of == now
    assert (covers_from, covered_until) == (None, None)


def test_freshness_is_measured_against_the_proof_not_the_read() -> None:
    coverage = TapeCoverage(session_since=SESSION, covered_until=_at(0), symbols={})

    assert coverage.fresh(now=_at(5)) is True
    assert coverage.fresh(now=_at(600)) is False


# --- T3.46f: the read order ------------------------------------------------


class TickingCollector(FakeHotState):
    """A collector that keeps working while the scanner reads it.

    Every read costs one tick, and one tick is what the two loops of the
    market-worker do together: the coalescer writes a newer book snapshot and
    the housekeeping loop stamps a ``covered_until`` that covers it. Five lines,
    and they are the whole race -- a perpetual's book updates 5-10x/s, so a cut
    read *before* the snapshot has always been left behind by the time the two
    are compared.
    """

    def __init__(self, *, start: datetime, step_ms: int = 250) -> None:
        super().__init__()
        self.moment = start
        self.step = timedelta(milliseconds=step_ms)
        self.load(candles=[], as_of=start, trades=0, with_book=False, with_deriv=False)
        self.tick()

    def tick(self) -> None:
        self.moment += self.step
        self.strings[keys.book(EXCHANGE, SYMBOL)] = book_payload(ts=self.moment)
        self.publish_coverage(session_since=SESSION, covered_until=self.moment)

    async def get(self, key: str) -> bytes | None:
        value = await super().get(key)
        self.tick()  # the collector does not stop while the scanner decodes
        return value

    async def hgetall(self, key: str) -> dict[str, str]:
        fields = await super().hgetall(key)
        self.tick()
        return fields

    async def hmget(self, key: str, fields: list[str]) -> list[str | None]:
        values = await super().hmget(key, fields)
        self.tick()
        return values


async def test_a_cut_read_before_the_book_is_already_behind_it() -> None:
    """The old order, kept as the oracle of what is being fixed."""
    redis = TickingCollector(start=SESSION)

    coverage = await read_coverage(cast("Any", redis), EXCHANGE)
    as_of, _, _ = evaluation_cut(coverage, SYMBOL, now=redis.moment)
    raw = await read_hot_state(cast("Any", redis), EXCHANGE, SYMBOL)

    # Exactly what production did until T3.46f: the cut proves an instant the
    # book had already left, and the whole snapshot is refused.
    assert decode_book(raw.book, as_of).reason == AFTER_CUT


async def test_the_cut_read_after_the_snapshots_covers_them() -> None:
    redis = TickingCollector(start=SESSION)
    coverage = await read_coverage(cast("Any", redis), EXCHANGE)

    build = await build_market_context(
        cast("Any", redis), exchange=EXCHANGE, symbol=SYMBOL, coverage=coverage, now=SESSION
    )

    book = build.context.book
    assert book.reason is None, "the book the collector had already written was refused"
    assert book.value is not None
    # The proof re-read after the snapshot covers it, so the book is usable and
    # the cut is still a published proof -- never the clock, never a tolerance.
    assert book.ts is not None and book.ts <= build.context.as_of
    assert build.covered is True


def test_the_re_read_never_lifts_the_cut_across_a_reconnection() -> None:
    coverage = TapeCoverage(
        session_since=SESSION, covered_until=_at(10), symbols={"BTCUSDT": SESSION}
    )

    # The collector reconnected between the two reads: this object's roster and
    # session start describe an interval that ended, and lifting its cut onto
    # the new session would claim coverage straight across the gap.
    advanced = coverage.advanced_to(_at(30), _at(40))

    assert advanced == coverage


def test_the_re_read_never_moves_the_cut_backwards() -> None:
    coverage = TapeCoverage(
        session_since=SESSION, covered_until=_at(10), symbols={"BTCUSDT": SESSION}
    )

    assert coverage.advanced_to(SESSION, _at(5)) == coverage
    assert coverage.advanced_to(SESSION, None) == coverage
    assert coverage.advanced_to(None, _at(20)) == coverage
    assert coverage.advanced_to(SESSION, _at(20)).covered_until == _at(20)


async def test_an_absent_proof_stays_absent_after_the_re_read() -> None:
    redis = TickingCollector(start=SESSION)
    redis.hashes.pop(keys.tape_coverage(EXCHANGE), None)

    coverage = await refreshed_cut(
        cast("Any", redis), TapeCoverage(), exchange=EXCHANGE, symbol=SYMBOL
    )

    # Nothing published is not "a cut of zero": a market nobody proved stays
    # uncovered, and its trade windows keep saying ``insufficient_coverage``.
    assert coverage.live is False


# --- T3.46g: routing a mapped symbol to its owning shard --------------------

AGGREGATE_MIN = _at(100)
FRESH_SHARD_UNTIL = _at(150)
SHARDS_KEY = f"{keys.tape_coverage('binance')}:shards"


def _redis_with(shard_fields: dict[str, str]) -> Any:
    """The aggregate hash (``covered_until`` = the min a lagging shard set)
    plus the ``:shards`` hash the mandatory reserve reads from."""
    aggregate = {
        "session_since": SESSION.isoformat(),
        "covered_until": AGGREGATE_MIN.isoformat(),
        "sym:BTCUSDT": SESSION.isoformat(),
        "sym:DOGEUSDT": SESSION.isoformat(),
    }
    return FakeRedis({keys.tape_coverage("binance"): aggregate, SHARDS_KEY: shard_fields})


async def test_a_symbol_mapped_to_one_live_shard_uses_that_shards_own_until() -> None:
    """The fresh shard's own record, not the aggregate min a laggard set."""
    redis = _redis_with(
        {
            **_shard_record(
                "0of2",
                since=SESSION,
                until=FRESH_SHARD_UNTIL,
                ts=AGGREGATE_MIN,
                symbols={"BTCUSDT": SESSION},
            ),
            **_shard_record(
                "1of2", since=SESSION, until=AGGREGATE_MIN, ts=AGGREGATE_MIN, symbols={}
            ),
        }
    )

    coverage = await read_coverage(redis, "binance", now=_at(101))
    assert coverage.shard_owner == {"BTCUSDT": "0of2"}

    refreshed = await refreshed_cut(redis, coverage, exchange="binance", symbol="BTCUSDT")

    assert refreshed.covered_until == FRESH_SHARD_UNTIL


async def test_a_symbol_on_the_lagging_shard_keeps_its_own_lagging_cut() -> None:
    """Ownership routes to *this* symbol's shard, never opportunistically to
    whichever shard happens to be freshest."""
    redis = _redis_with(
        {
            **_shard_record(
                "0of2", since=SESSION, until=FRESH_SHARD_UNTIL, ts=AGGREGATE_MIN, symbols={}
            ),
            **_shard_record(
                "1of2",
                since=SESSION,
                until=AGGREGATE_MIN,
                ts=AGGREGATE_MIN,
                symbols={"BTCUSDT": SESSION},
            ),
        }
    )

    coverage = await read_coverage(redis, "binance", now=_at(101))
    refreshed = await refreshed_cut(redis, coverage, exchange="binance", symbol="BTCUSDT")

    assert refreshed.covered_until == AGGREGATE_MIN


async def test_an_unmapped_symbol_falls_back_to_the_aggregate_min() -> None:
    redis = _redis_with(
        _shard_record(
            "0of2",
            since=SESSION,
            until=FRESH_SHARD_UNTIL,
            ts=AGGREGATE_MIN,
            symbols={"BTCUSDT": SESSION},
        )
    )

    coverage = await read_coverage(redis, "binance", now=_at(101))
    assert "DOGEUSDT" not in coverage.shard_owner  # type: ignore[operator]

    refreshed = await refreshed_cut(redis, coverage, exchange="binance", symbol="DOGEUSDT")

    assert refreshed.covered_until == AGGREGATE_MIN


async def test_a_symbol_claimed_by_two_live_shards_falls_back_to_the_aggregate_min() -> None:
    """Mandatory reserve: a rebalance in flight (two live shards both still
    claiming the symbol) has no single owner to trust -- never guess."""
    redis = _redis_with(
        {
            **_shard_record(
                "0of2",
                since=SESSION,
                until=FRESH_SHARD_UNTIL,
                ts=AGGREGATE_MIN,
                symbols={"BTCUSDT": SESSION},
            ),
            **_shard_record(
                "1of2",
                since=SESSION,
                until=AGGREGATE_MIN,
                ts=AGGREGATE_MIN,
                symbols={"BTCUSDT": SESSION},
            ),
        }
    )

    coverage = await read_coverage(redis, "binance", now=_at(101))
    assert "BTCUSDT" not in coverage.shard_owner  # type: ignore[operator]

    refreshed = await refreshed_cut(redis, coverage, exchange="binance", symbol="BTCUSDT")

    assert refreshed.covered_until == AGGREGATE_MIN


async def test_a_stale_shard_record_is_excluded_from_ownership() -> None:
    """A shard that stopped stamping more than ``MAX_PROOF_AGE_S`` ago is not
    a live owner, exactly like ``coverage_publish.SHARD_RECORD_TTL_S`` drops
    it from the aggregate itself."""
    redis = _redis_with(
        _shard_record(
            "0of2",
            since=SESSION,
            until=FRESH_SHARD_UNTIL,
            ts=SESSION,  # stamped 100s before ``now`` below -- long stale
            symbols={"BTCUSDT": SESSION},
        )
    )

    coverage = await read_coverage(redis, "binance", now=_at(101))

    assert coverage.shard_owner == {}
    refreshed = await refreshed_cut(redis, coverage, exchange="binance", symbol="BTCUSDT")
    assert refreshed.covered_until == AGGREGATE_MIN
