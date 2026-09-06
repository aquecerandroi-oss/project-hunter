"""Reading the collector's proof, and what it does to the evaluation cut.

Every assertion here is about a *refusal*. The scanner is allowed to publish a
trade window only when the collector proved it stayed connected through it, and
each of these cases is a way that proof can be absent -- with the feature it
costs stated in the test name, because "insufficient_coverage" is the honest
answer and not a bug to be worked around.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from hunter_core.redis import keys
from hunter_scanner_worker.context import MAX_CUT_LAG_S, evaluation_cut
from hunter_scanner_worker.coverage import TapeCoverage, read_coverage

SESSION = datetime(2026, 9, 6, 12, 0, 0, tzinfo=UTC)


def _at(seconds: float) -> datetime:
    return SESSION + timedelta(seconds=seconds)


class FakeRedis:
    def __init__(self, hashes: dict[str, dict[str, str]] | None = None) -> None:
        self.hashes = hashes or {}

    async def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.hashes.get(key, {}))


def _published(**fields: str) -> Any:
    return FakeRedis({keys.tape_coverage("binance"): fields})


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
