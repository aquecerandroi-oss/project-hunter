"""T4.97b/R80 must-fix 1: ``poll_once`` (``collect.py``) stops burning the
shared ``pumpfun_rest`` bucket on the by-mint identity read once it has
failed enough in a row — the circuit breaker (``identity_breaker.py``) — and
never touches the plan when the chain is *not* covering the curve, because
then the same route is the only source of price/reserves. No database, no
socket: the same ``_no_role``/fake-session pattern as ``test_identity_sweep.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from hunter_exchanges.pumpfun.models import NormalizedCurveState
from hunter_meme_worker import budget_gap, collect
from hunter_meme_worker.config import MemeConfig
from hunter_meme_worker.context import RadarContext, RadarState
from hunter_meme_worker.identity_breaker import IdentityBreaker
from hunter_meme_worker.repo import GapRow
from hunter_meme_worker.sources import PUMPFUN_REST, SourcesState
from hunter_meme_worker.tracker import MintTracker, TrackedMint

pytestmark = pytest.mark.unit

T0 = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
MINTS = tuple(f"mint{i:02d}" for i in range(10))


class DeadByMintCurves:
    """Every by-mint read 404s, like ``frontend-api-v3.pump.fun`` since
    2026-09-25 17:13Z; ``get_curve_state`` is never legitimately called by the
    RPC path (``ctx.chain``), only by this REST client."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def get_curve_state(self, mint: str) -> NormalizedCurveState:
        self.calls.append(mint)
        raise RuntimeError("404 Cannot GET /coins/" + mint)

    async def list_recent(
        self, *, limit: int = 50, sort: str = "created_timestamp", order: str = "DESC"
    ) -> list[NormalizedCurveState]:
        raise AssertionError("poll_once never calls the listing route")


class OneProbeSucceedsCurves(DeadByMintCurves):
    """Every by-mint read fails except the first one asked for after
    ``succeed_from`` calls — used to prove a successful probe recovers."""

    def __init__(self, succeed_from: int) -> None:
        super().__init__()
        self.succeed_from = succeed_from

    async def get_curve_state(self, mint: str) -> NormalizedCurveState:
        self.calls.append(mint)
        if len(self.calls) >= self.succeed_from:
            return NormalizedCurveState(
                mint=mint,
                virtual_sol_reserves=Decimal("30"),
                virtual_token_reserves=Decimal("1073000000"),
                real_sol_reserves=Decimal("0"),
                real_token_reserves=Decimal("793100000"),
                total_supply=Decimal("1000000000"),
                complete=False,
                market_cap_sol=Decimal("28"),
                source="pumpfun_rest",
                received_at=T0,
                observed_at=T0,
            )
        raise RuntimeError("404 Cannot GET /coins/" + mint)


class _Session:
    def __init__(self) -> None:
        self.statements: list[Any] = []

    async def execute(self, statement: Any, params: Any = None) -> None:
        self.statements.append((str(statement)[:60], params))

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


def _no_role(factory: Any, db_role: str) -> Any:
    return factory()


def _tracker(mints: tuple[str, ...] = MINTS) -> MintTracker:
    tracker = MintTracker(window_minutes=1440, cap=120)
    for mint in mints:
        tracker.observe(TrackedMint(mint=mint, first_seen_at=T0, mcap_sol=Decimal("1")))
    return tracker


def _context(
    curves: Any,
    tracker: MintTracker,
    *,
    covered: bool,
    budget: int = 10,
    breaker: IdentityBreaker | None = None,
    sources: SourcesState | None = None,
) -> RadarContext:
    return RadarContext(
        config=MemeConfig(rest_budget_per_minute=budget, chain_curves_enabled=True),
        session_factory=lambda: _Session(),  # type: ignore[arg-type]
        tracker=tracker,
        state=RadarState(chain_ok_at=T0 if covered else None),
        events=None,  # type: ignore[arg-type]
        curves=curves,
        chain=None,  # type: ignore[arg-type]
        sources=sources if sources is not None else SourcesState(),
        identity_breaker=breaker if breaker is not None else IdentityBreaker(trip_threshold=3),
    )


@pytest.fixture(autouse=True)
def _stub_db(  # pyright: ignore[reportUnusedFunction] - pytest autouse fixture
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(collect, "role_session", _no_role)
    monkeypatch.setattr(budget_gap, "role_session", _no_role)
    monkeypatch.setattr(collect, "utcnow", lambda: T0)

    async def _no_open_bets(ctx: RadarContext) -> frozenset[str]:
        return frozenset()

    monkeypatch.setattr(collect, "refresh_open_bets", _no_open_bets)


async def test_the_breaker_trips_mid_cycle_and_stops_spending_the_budget() -> None:
    curves = DeadByMintCurves()
    ctx = _context(curves, _tracker(), covered=True, budget=10)
    read = await collect.poll_once(ctx)
    assert read == 0
    # trip_threshold=3: the 3rd failure trips it, and the loop breaks right there.
    assert len(curves.calls) == 3
    assert ctx.identity_breaker.is_open
    # every mint not attempted this cycle is an honest not_polled, never silent.
    unattempted = set(MINTS) - set(curves.calls)
    assert len(unattempted) == 7
    assert all(ctx.state.absences[m] == "not_polled" for m in unattempted)


async def test_once_open_the_next_cycle_only_spends_one_sparse_probe() -> None:
    curves = DeadByMintCurves()
    breaker = IdentityBreaker(trip_threshold=1, probe_interval=timedelta(minutes=5))
    breaker.record_failure()
    assert breaker.is_open
    ctx = _context(curves, _tracker(), covered=True, budget=10, breaker=breaker)
    read = await collect.poll_once(ctx)
    assert read == 0
    assert len(curves.calls) == 1, "only the probe is attempted — the rest is suspended untouched"


async def test_a_successful_probe_closes_the_breaker_and_the_next_cycle_is_full_again() -> None:
    breaker = IdentityBreaker(trip_threshold=1, probe_interval=timedelta(minutes=5))
    breaker.record_failure()
    curves = OneProbeSucceedsCurves(succeed_from=1)
    ctx = _context(curves, _tracker(("mint00",)), covered=True, budget=10, breaker=breaker)
    read = await collect.poll_once(ctx)
    assert read == 1
    assert not ctx.identity_breaker.is_open


async def test_an_uncovered_chain_never_lets_the_breaker_touch_the_plan() -> None:
    """The by-mint route is the *only* source of price/reserves when the
    chain loop is not covering the curve — the breaker must never suspend it,
    however many consecutive failures it has already recorded."""
    curves = DeadByMintCurves()
    breaker = IdentityBreaker(trip_threshold=1)
    breaker.record_failure()
    assert breaker.is_open
    ctx = _context(curves, _tracker(), covered=False, budget=10, breaker=breaker)
    read = await collect.poll_once(ctx)
    assert read == 0
    assert len(curves.calls) == len(MINTS), "every mint is still attempted; nothing suspended"
    # T4.97b review round 2 (Astra): the outcome still updates the breaker's
    # own bookkeeping even though it never filtered this cycle's plan.
    assert ctx.identity_breaker.consecutive_failures == 1 + len(MINTS)


async def test_a_success_while_uncovered_still_closes_the_breaker_for_later() -> None:
    """Astra's must-fix (T4.97b review round 2): breaker open + probe spent →
    the chain loses coverage → the by-mint route answers → the chain regains
    coverage. The breaker must already be closed by the time coverage
    returns, not stuck suspending reads on a recovery it already observed."""
    breaker = IdentityBreaker(trip_threshold=1, probe_interval=timedelta(minutes=5))
    breaker.record_failure()
    assert breaker.is_open
    curves = OneProbeSucceedsCurves(succeed_from=1)
    ctx = _context(curves, _tracker(("mint00",)), covered=False, budget=10, breaker=breaker)
    read = await collect.poll_once(ctx)
    assert read == 1
    assert not ctx.identity_breaker.is_open, "the success closed it even though covered=False"


async def test_the_gap_row_names_the_breaker_suspended_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: list[GapRow] = []

    async def _spy(session: Any, gap: GapRow) -> None:
        recorded.append(gap)

    monkeypatch.setattr(budget_gap, "record_gap", _spy)
    curves = DeadByMintCurves()
    ctx = _context(curves, _tracker(), covered=True, budget=10)
    await collect.poll_once(ctx)
    assert len(recorded) == 1
    assert recorded[0].detail is not None
    assert recorded[0].detail["breaker_suspended"] == 7


async def test_a_generic_error_records_the_truncated_message_not_the_exception_class() -> None:
    """Astra's nit (T4.97/R80 review, must-fix 2): ``record_error`` should
    carry something an operator can act on, not ``RuntimeError`` for every
    kind of failure."""
    curves = DeadByMintCurves()
    breaker = IdentityBreaker(trip_threshold=100)  # never trips in this test
    sources = SourcesState()
    ctx = _context(
        curves, _tracker(("mint00",)), covered=True, budget=10, breaker=breaker, sources=sources
    )
    await collect.poll_once(ctx)
    assert sources[PUMPFUN_REST].last_error == "404 Cannot GET /coins/mint00"
