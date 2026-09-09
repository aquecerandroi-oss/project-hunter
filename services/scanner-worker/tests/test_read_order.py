"""The order the scanner reads Redis in, against a real Redis (T3.46f).

Why testcontainers for something as small as two reads: the property being
proved is *ordering between round trips*, and a hand-written double decides that
ordering itself. Here the bytes come back from a real server, in the order a
real client asked for them -- the hot-state pipeline first, the coverage proof
after it -- and the collector's stamp lands in between exactly as the
market-worker's housekeeping loop lands between the coalescer's book write and
the scanner's next read.

The fixture is synthetic and labelled as such: one book snapshot and one
coverage hash, written by the test, nothing recorded from an exchange.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

import pytest

from hunter_core.redis import keys
from hunter_indicators.features import read_hot_state
from hunter_indicators.features.hotstate import AFTER_CUT, decode_book
from hunter_scanner_worker.context import build_market_context, evaluation_cut
from hunter_scanner_worker.coverage import read_coverage

from .builders import EXCHANGE, SYMBOL, book_payload

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

pytestmark = pytest.mark.integration

SESSION = datetime(2026, 9, 8, 22, 0, 0, tzinfo=UTC)
CUT_AT_CYCLE_START = SESSION + timedelta(seconds=30)
BOOK_TS = CUT_AT_CYCLE_START + timedelta(milliseconds=339)
"""The measured p50 of ``book.ts - covered_until`` on the live venue
(notes-T3.46d section 1.2): the book is not a corner case, it is 339 ms ahead of
a cut read half a cycle earlier."""
STAMPED_AFTER = BOOK_TS + timedelta(milliseconds=12)
"""What the collector publishes while the scanner is reading: a proof that
already covers the book it wrote before it."""


class StampingWhileRead:
    """The real client, plus a collector that stamps between the two reads.

    Every attribute except ``pipeline`` is the real Redis client's. The wrapped
    pipeline runs the four hot-state reads for real and *then* publishes a newer
    ``covered_until``, which is what the market-worker's housekeeping loop does
    while the scanner decodes: the proof the scanner re-reads afterwards is a
    proof of data the collector had already accepted, never a guess.
    """

    def __init__(self, client: Any, *, stamp: datetime) -> None:
        self.client = client
        self.stamp = stamp

    def __getattr__(self, name: str) -> Any:
        return getattr(self.client, name)

    def pipeline(self, *args: Any, **kwargs: Any) -> Any:
        return _Pipeline(self.client.pipeline(*args, **kwargs), self)


class _Pipeline:
    def __init__(self, inner: Any, owner: StampingWhileRead) -> None:
        self.inner = inner
        self.owner = owner

    async def __aenter__(self) -> _Pipeline:
        await self.inner.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.inner.__aexit__(*args)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    async def execute(self) -> list[Any]:
        result = cast("list[Any]", await self.inner.execute())
        await self.owner.client.hset(
            keys.tape_coverage(EXCHANGE),
            mapping={"covered_until": self.owner.stamp.isoformat()},
        )
        return result


@pytest.fixture
async def seeded(redis_client: Any) -> AsyncIterator[Any]:
    """One book 339 ms ahead of the cut the cycle started with."""
    await redis_client.set(keys.book(EXCHANGE, SYMBOL), book_payload(ts=BOOK_TS))
    await redis_client.hset(
        keys.tape_coverage(EXCHANGE),
        mapping={
            "session_since": SESSION.isoformat(),
            "covered_until": CUT_AT_CYCLE_START.isoformat(),
            f"sym:{SYMBOL}": SESSION.isoformat(),
        },
    )
    yield redis_client


async def test_the_cycle_start_cut_refuses_a_book_written_after_it(seeded: Any) -> None:
    """The old order, against the same real bytes: the oracle of the fix."""
    coverage = await read_coverage(seeded, EXCHANGE)
    as_of, _, _ = evaluation_cut(coverage, SYMBOL, now=BOOK_TS)
    raw = await read_hot_state(seeded, EXCHANGE, SYMBOL)

    assert as_of == CUT_AT_CYCLE_START
    assert decode_book(raw.book, as_of).reason == AFTER_CUT


async def test_the_proof_re_read_after_the_snapshot_makes_the_book_usable(seeded: Any) -> None:
    coverage = await read_coverage(seeded, EXCHANGE)
    redis = StampingWhileRead(seeded, stamp=STAMPED_AFTER)

    build = await build_market_context(
        cast("Any", redis),
        exchange=EXCHANGE,
        symbol=SYMBOL,
        coverage=coverage,
        now=STAMPED_AFTER,
    )

    assert build.context.as_of == STAMPED_AFTER
    book = build.context.book
    assert book.reason is None
    assert book.value is not None and book.value.ts == BOOK_TS
    # The roster still comes from the per-cycle read: the re-read moves the cut
    # and nothing else, so a market outside ``sym:*`` stays uncovered.
    assert build.covered is True


async def test_a_book_still_ahead_of_the_re_read_cut_is_refused(seeded: Any) -> None:
    """No tolerance was added: a genuine race is still a refusal."""
    coverage = await read_coverage(seeded, EXCHANGE)
    redis = StampingWhileRead(seeded, stamp=BOOK_TS - timedelta(milliseconds=1))

    build = await build_market_context(
        cast("Any", redis), exchange=EXCHANGE, symbol=SYMBOL, coverage=coverage, now=BOOK_TS
    )

    assert build.context.book.reason == AFTER_CUT


async def test_a_symbol_owned_by_a_fresh_shard_uses_that_shards_own_cut(seeded: Any) -> None:
    """T3.46g, against real Redis: the aggregate ``min`` a lagging sibling set
    (``CUT_AT_CYCLE_START``) would still refuse this book; the owning shard's
    own record already covers it, and the mapping comes from the same
    ``:shards`` hash the ``until`` does -- never a formula, never a guess.
    """
    shard_until = BOOK_TS + timedelta(milliseconds=1)
    await seeded.hset(
        f"{keys.tape_coverage(EXCHANGE)}:shards",
        mapping={
            "0of2:since": f"{SESSION.timestamp()}|{SESSION.isoformat()}",
            "0of2:until": f"{shard_until.timestamp()}|{shard_until.isoformat()}",
            "0of2:ts": str(BOOK_TS.timestamp()),
            "0of2:syms": f"{SYMBOL}\t{SESSION.timestamp()}\t{SESSION.isoformat()}",
        },
    )

    coverage = await read_coverage(seeded, EXCHANGE, now=BOOK_TS)
    assert coverage.shard_owner == {SYMBOL: "0of2"}
    assert coverage.covered_until == CUT_AT_CYCLE_START  # the aggregate alone is still stale

    build = await build_market_context(
        seeded, exchange=EXCHANGE, symbol=SYMBOL, coverage=coverage, now=BOOK_TS
    )

    assert build.context.book.reason is None
    assert build.context.as_of == shard_until
