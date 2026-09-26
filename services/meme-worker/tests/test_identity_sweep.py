"""T4.97/R80: the identity sweep reads ``/coins`` sorted by creation instead of
polling ``/coins/{mint}`` per mint — the by-mint route 404s for every mint since
2026-09-25 17:13Z (notes-R80.md §1). No database, no socket: the same
``_no_role``/fake-session pattern as ``test_reconcile_derives_curve.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from hunter_exchanges.pumpfun.models import NormalizedCurveState
from hunter_meme_worker import collect, identity_sweep
from hunter_meme_worker.config import MemeConfig
from hunter_meme_worker.context import RadarContext, RadarState
from hunter_meme_worker.sources import PUMPFUN_REST, SourcesState
from hunter_meme_worker.tracker import MintTracker, TrackedMint

pytestmark = pytest.mark.unit

T0 = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
TRACKED_NEEDS_IDENTITY = "3aYHwMeoXeEqtLnap1TByBfmh2CHnVexX9pqMUHFpump"
TRACKED_ALREADY_IDENTIFIED = "9Y6knoPfLhJHCofaUc9dp2ZYUUba8GGj3oHkAyjg3yKC"
UNTRACKED = "F9SzDFRqpZZeNZUo5ZksYNpqXqVKzhfNpEbUyMdhpump"


def _state(mint: str, *, twitter: str | None) -> NormalizedCurveState:
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
        twitter=twitter,
    )


class FakeCurves:
    def __init__(self, states: list[NormalizedCurveState]) -> None:
        self.states = states
        self.calls: list[dict[str, Any]] = []

    async def get_curve_state(self, mint: str) -> NormalizedCurveState:
        raise AssertionError("the identity sweep never reads by mint")

    async def list_recent(
        self, *, limit: int = 50, sort: str = "created_timestamp", order: str = "DESC"
    ) -> list[NormalizedCurveState]:
        self.calls.append({"limit": limit, "sort": sort, "order": order})
        return self.states


class FailingCurves:
    async def get_curve_state(self, mint: str) -> NormalizedCurveState:
        raise AssertionError("not used")

    async def list_recent(
        self, *, limit: int = 50, sort: str = "created_timestamp", order: str = "DESC"
    ) -> list[NormalizedCurveState]:
        raise RuntimeError("pumpfun rest resource not found")


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


def _tracker() -> MintTracker:
    tracker = MintTracker(window_minutes=1440, cap=120)
    tracker.observe(
        TrackedMint(mint=TRACKED_NEEDS_IDENTITY, first_seen_at=T0, mcap_sol=Decimal("28"))
    )
    tracker.observe(
        TrackedMint(mint=TRACKED_ALREADY_IDENTIFIED, first_seen_at=T0, mcap_sol=Decimal("28"))
    )
    tracker.mark_polled(
        TRACKED_ALREADY_IDENTIFIED,
        T0 - timedelta(minutes=1),
        mcap_sol=Decimal("28"),
        source="pumpfun_rest",
    )
    return tracker


def _context(curves: Any, tracker: MintTracker, sources: SourcesState) -> RadarContext:
    return RadarContext(
        config=MemeConfig(),
        session_factory=lambda: _Session(),  # type: ignore[arg-type]
        tracker=tracker,
        state=RadarState(),
        events=None,  # type: ignore[arg-type]
        curves=curves,
        chain=None,  # type: ignore[arg-type]
        sources=sources,
    )


async def test_the_sweep_only_writes_tracked_mints_that_still_need_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(collect, "role_session", _no_role)
    curves = FakeCurves(
        [
            _state(TRACKED_NEEDS_IDENTITY, twitter="https://x.com/foo"),
            _state(TRACKED_ALREADY_IDENTIFIED, twitter="https://x.com/bar"),
            _state(UNTRACKED, twitter="https://x.com/baz"),
        ]
    )
    tracker = _tracker()
    written = await identity_sweep.identity_sweep_once(_context(curves, tracker, SourcesState()))
    assert written == 1
    assert curves.calls == [
        {"limit": identity_sweep.IDENTITY_SWEEP_LIMIT, "sort": "created_timestamp", "order": "DESC"}
    ]
    needs_identity = tracker.get(TRACKED_NEEDS_IDENTITY)
    already_identified = tracker.get(TRACKED_ALREADY_IDENTIFIED)
    assert needs_identity is not None and needs_identity.last_rest_polled_at == T0
    # already-identified and untracked mints are untouched
    assert (
        already_identified is not None
        and already_identified.last_rest_polled_at == T0 - timedelta(minutes=1)
    )
    assert tracker.get(UNTRACKED) is None


async def test_a_failed_listing_call_writes_nothing_and_never_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(collect, "role_session", _no_role)
    sources = SourcesState()
    written = await identity_sweep.identity_sweep_once(
        _context(FailingCurves(), _tracker(), sources)
    )
    assert written == 0
    stats = sources[PUMPFUN_REST]
    assert stats.consecutive_failures == 1
    assert stats.last_error == "pumpfun rest resource not found"


async def test_one_listing_call_is_one_request_however_many_mints_it_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Astra's must-fix (T4.97/R80 review): a batch of N persisted mints must not
    read as N requests against the one HTTP call that actually happened."""
    monkeypatch.setattr(collect, "role_session", _no_role)
    tracker = MintTracker(window_minutes=1440, cap=120)
    other_mint = "DR8NiRhVELdUtp9JcV29NnKKBSGMANHnvwi1fumRpump"
    tracker.observe(
        TrackedMint(mint=TRACKED_NEEDS_IDENTITY, first_seen_at=T0, mcap_sol=Decimal("28"))
    )
    tracker.observe(TrackedMint(mint=other_mint, first_seen_at=T0, mcap_sol=Decimal("28")))
    curves = FakeCurves(
        [
            _state(TRACKED_NEEDS_IDENTITY, twitter="https://x.com/foo"),
            _state(other_mint, twitter=None),
        ]
    )
    sources = SourcesState()
    written = await identity_sweep.identity_sweep_once(_context(curves, tracker, sources))
    assert written == 2
    stats = sources[PUMPFUN_REST]
    assert stats.last_observed_at is not None
    assert stats.used_60s.total(stats.last_observed_at) == 1


async def test_a_call_with_nothing_to_write_still_counts_as_one_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A listing call where every mint is untracked or already identified still
    reached pump.fun and answered — that must move ``last_observed_at`` off
    ``None``, or the source reads as ``never_observed`` while it is healthy."""
    monkeypatch.setattr(collect, "role_session", _no_role)
    sources = SourcesState()
    curves = FakeCurves([_state(UNTRACKED, twitter="https://x.com/foo")])
    written = await identity_sweep.identity_sweep_once(_context(curves, _tracker(), sources))
    assert written == 0
    stats = sources[PUMPFUN_REST]
    assert stats.last_observed_at is not None
    assert stats.consecutive_failures == 0
