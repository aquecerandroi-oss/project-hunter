"""The chain loop (T4.2f) over the live capture of 12/09/2026 13:07:58 UTC —
140 of the freshest coins in two ``getMultipleAccounts`` — through the real
decoder and the same persistence path as a REST photo: every SOL curve becomes a
``solana_rpc`` snapshot stamped with the slot's block time, feeds the
denominator and the tracker; every refusal is named and teaches the tracker
what it can; the REST poll narrows to identity reads while the chain covers,
and falls back when it does not. No socket, no database."""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from hunter_exchanges.base import RateLimited
from hunter_exchanges.pumpfun.quote import GlobalParams
from hunter_exchanges.pumpfun.rpc import CurveBatch
from hunter_exchanges.pumpfun.rpc_curves import (
    ACCOUNTS_PER_CALL,
    CURVE_EMPTIED,
    CURVE_NOT_FOUND,
    decode_curve_batch,
)
from hunter_exchanges.pumpfun.rpc_curves import (
    UNSUPPORTED_QUOTE as CHAIN_UNSUPPORTED_QUOTE,
)
from hunter_meme_worker.chain import chain_mints, chain_once
from hunter_meme_worker.collect import chain_covered, poll_once
from hunter_meme_worker.config import MemeConfig
from hunter_meme_worker.context import RadarContext, RadarState
from hunter_meme_worker.features import INSUFFICIENT_COVERAGE, RATE_LIMITED, UNSUPPORTED_QUOTE
from hunter_meme_worker.graduation import GLOBAL_PARAMS, GlobalParamsStore
from hunter_meme_worker.sources import SOLANA_RPC, SourcesState
from hunter_meme_worker.tracker import TIER_FINAL_READ, MintTracker, TrackedMint

pytestmark = pytest.mark.unit

FIXTURES = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "exchange-adapters"
    / "tests"
    / "fixtures"
    / "pumpfun"
)
SLOT = 446436963
BLOCK_TIME = datetime(2026, 9, 12, 13, 7, 47, tzinfo=UTC)
RECEIVED = datetime(2026, 9, 12, 13, 7, 58, tzinfo=UTC)
T0 = RECEIVED - timedelta(minutes=5)
ABSENT = "11111111111111111111111111111111"
PARAMS = GlobalParams(
    slot=354155511,
    signature="x",
    initial_virtual_token_reserves=1073000000000000,
    initial_virtual_sol_reserves=30000000000,
    initial_real_token_reserves=793100000000000,
    token_total_supply=1000000000000000,
    fee_basis_points=95,
    timestamp=1752856476446,
)


def _accounts() -> tuple[list[str], dict[str, Any]]:
    """Every captured curve account by mint, both batches, in capture order."""
    mints: list[str] = []
    accounts: dict[str, Any] = {}
    for index in (1, 2):
        meta = json.loads((FIXTURES / f"t42f_rpc_curves_batch{index}_addresses.json").read_text())
        raw = json.loads((FIXTURES / f"t42f_rpc_curves_batch{index}_raw.json").read_text())
        for (name, _), account in zip(meta["addresses"], raw["result"]["value"], strict=True):
            mint = name.removeprefix("ABSENT:")
            mints.append(mint)
            accounts[mint] = account
    return mints, accounts


def _kinds() -> dict[str, list[str]]:
    """The fixture's mints by what the chain says of them."""
    mints, accounts = _accounts()
    result = {"context": {"slot": SLOT}, "value": [accounts[m] for m in mints]}
    states, refused, _ = decode_curve_batch(
        mints, result, block_time=BLOCK_TIME, received_at=RECEIVED
    )
    kinds: dict[str, list[str]] = {"mayhem": [], "virgin": [], "midlife": []}
    for mint, state in states.items():
        if state.mayhem_enabled:
            kinds["mayhem"].append(mint)
        elif state.real_sol_reserves == 0:
            kinds["virgin"].append(mint)
        else:
            kinds["midlife"].append(mint)
    for mint, why in refused.items():
        kinds.setdefault(why, []).append(mint)
    return kinds


class FakeChain:
    """Serves the capture through the real decoder, 100 per call, like the client."""

    def __init__(self, *, fail: Exception | None = None) -> None:
        self.calls: list[list[str]] = []
        self.fail = fail
        _, self.accounts = _accounts()

    async def get_curve_state(self, mint: str, bonding_curve: str) -> Any:
        raise AssertionError("the chain loop never reads one account at a time")

    async def get_mayhem_flows(self, mints: Any) -> Any:
        raise AssertionError("not the Mayhem loop")

    async def get_curve_states(self, mints: Any, *, with_block_time: bool = True) -> CurveBatch:
        self.calls.append(list(mints))
        if self.fail is not None:
            raise self.fail
        states: dict[str, Any] = {}
        refused: dict[str, str] = {}
        slots: list[int] = []
        for start in range(0, len(mints), ACCOUNTS_PER_CALL):
            chunk = list(mints[start : start + ACCOUNTS_PER_CALL])
            result = {"context": {"slot": SLOT}, "value": [self.accounts.get(m) for m in chunk]}
            s, r, slot = decode_curve_batch(
                chunk, result, block_time=BLOCK_TIME, received_at=RECEIVED
            )
            states.update(s)
            refused.update(r)
            slots.append(slot)
        return CurveBatch(states=states, refused=refused, slots=tuple(slots), calls=2 * len(slots))


class _Session:
    def __init__(self, log: list[Any]) -> None:
        self.log = log

    async def execute(self, statement: Any, params: Any = None) -> None:
        self.log.append((str(statement)[:60], params))

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


class _Params:
    async def get_global_params(self, created_at_ms: int) -> GlobalParams:
        return PARAMS


def _no_role(factory: Any, db_role: str) -> Any:
    return factory()


def _tracked(mint: str, **kw: object) -> TrackedMint:
    return TrackedMint(mint=mint, first_seen_at=T0, created_at=T0, **kw)  # type: ignore[arg-type]


def _context(
    chain: Any, log: list[Any], *, tracked: list[TrackedMint], sources: bool = True
) -> RadarContext:
    tracker = MintTracker(window_minutes=1440, cap=200)
    for mint in tracked:
        tracker.observe(mint)
    return RadarContext(
        config=MemeConfig(),
        session_factory=lambda: _Session(log),  # type: ignore[arg-type]
        tracker=tracker,
        state=RadarState(),
        events=None,  # type: ignore[arg-type]
        curves=None,  # type: ignore[arg-type]
        chain=chain,
        sources=SourcesState() if sources else None,
        params=GlobalParamsStore(_Params(), refresh_s=3600),
    )


def _patch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hunter_meme_worker.collect.role_session", _no_role)


async def test_the_loop_photographs_every_tracked_mint_through_the_same_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch(monkeypatch)
    mints, _ = _accounts()
    kinds = _kinds()
    log: list[Any] = []
    chain = FakeChain()
    ctx = _context(chain, log, tracked=[_tracked(m) for m in mints])
    assert chain_mints(ctx.tracker) and set(chain_mints(ctx.tracker)) == set(mints)
    report = await chain_once(ctx)
    assert len(chain.calls) == 1 and set(chain.calls[0]) == set(mints), "one batch, every mint"
    assert report.tracked == 141 and report.read == 115 and report.calls == 4
    assert report.refused == {CHAIN_UNSUPPORTED_QUOTE: 23, CURVE_EMPTIED: 2, CURVE_NOT_FOUND: 1}
    assert report.emptied == 2 and not report.failed
    snapshots = [p for s, p in log if s.startswith("INSERT INTO meme_curve_snapshots")]
    assert len(snapshots) == 115
    assert all(
        p["source"] == "solana_rpc"
        and p["slot"] == SLOT
        and p["commitment"] == "finalized"
        and p["observed_at"] == BLOCK_TIME
        for p in snapshots
    ), "the chain's photo: slot, finality, the slot's block time as its instant"
    tokens = {p["mint"]: p for s, p in log if s.startswith("INSERT INTO meme_tokens")}
    assert len(tokens) == 115 and all(
        p["first_seen_source"] == "solana_rpc" for p in tokens.values()
    )
    # The denominator, by the same rules a REST photo obeys (T4.2d/T4.2e).
    for mint in kinds["midlife"]:
        assert tokens[mint]["progress_denominator_source"] == GLOBAL_PARAMS, mint
        assert tokens[mint]["initial_real_token_reserves"] == Decimal("793100000")
    assert kinds["virgin"] == [], (
        "0 of 79 SOL curves at real_sol = 0: a fresh coin carries its creator's buy, so "
        "observed_virgin is the exception on chain and global_params the rule"
    )
    for mint in kinds["mayhem"]:
        assert tokens[mint]["progress_denominator_source"] is None, "Mayhem claims nothing here"
        assert tokens[mint]["mayhem_enabled"] is True
    assert len(kinds["midlife"]) >= 20 and len(kinds["mayhem"]) == 45
    # The tracker and the minute: read from the chain, not from the mirror.
    for mint in kinds["midlife"][:5]:
        tracked = ctx.tracker.get(mint)
        assert tracked is not None and tracked.last_polled_at == BLOCK_TIME
        assert tracked.last_rest_polled_at is None, "a chain read is not an identity read"
        assert tracked.initial_real_token_reserves == Decimal("793100000")
        assert ctx.state.observations[mint].source == "solana_rpc"
        assert ctx.state.observations[mint].observed_at == BLOCK_TIME
    assert len(ctx.state.observations) == 115
    # Refusals teach what they can, and the minute says what it lacks.
    for mint in kinds[CHAIN_UNSUPPORTED_QUOTE]:
        tracked = ctx.tracker.get(mint)
        assert tracked is not None and tracked.quote_unsupported
        assert ctx.state.absences[mint] == UNSUPPORTED_QUOTE
    for mint in kinds[CURVE_EMPTIED]:
        tracked = ctx.tracker.get(mint)
        assert tracked is not None and tracked.complete and tracked.final_read_pending
        assert ctx.state.absences[mint] == INSUFFICIENT_COVERAGE
        assert ctx.tracker.tier(tracked, RECEIVED, {}) == TIER_FINAL_READ
    assert ctx.state.absences[ABSENT] == INSUFFICIENT_COVERAGE
    assert ctx.tracker.prune(RECEIVED)[0] == tuple(sorted(kinds[CHAIN_UNSUPPORTED_QUOTE])), (
        "a curve not quoted in SOL leaves the set, as after a REST refusal"
    )
    # Coverage of the REST poll: the chain covers, the heartbeat says so.
    assert ctx.state.chain_ok_at is not None and chain_covered(ctx, ctx.state.chain_ok_at)
    assert not chain_covered(ctx, ctx.state.chain_ok_at + timedelta(seconds=121))
    assert ctx.sources is not None
    now = ctx.state.chain_ok_at
    assert ctx.sources[SOLANA_RPC].used_60s.total(now) == 4, "four calls, counted once each"
    assert ctx.sources[SOLANA_RPC].last_observed_at == BLOCK_TIME
    fields = ctx.sources.heartbeat_fields(now, tracked=141)
    assert fields["chain_read_mints"] == "115" and fields["chain_tracked_mints"] == "141"
    assert fields["chain_calls_60s"] == "4" and fields["chain_refused_1h"] == "26"
    assert fields["chain_block_time_missing_60s"] == "0"


async def test_the_rest_poll_narrows_to_identity_reads_while_the_chain_covers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch(monkeypatch)
    monkeypatch.setattr("hunter_meme_worker.collect.refresh_open_bets", _no_bets)
    kinds = _kinds()
    log: list[Any] = []
    tracked = [_tracked(m) for m in kinds["midlife"][:6] + kinds["mayhem"][:2]]
    ctx = _context(FakeChain(), log, tracked=tracked)
    # Four standard mints had their identity read, two never; one Mayhem agent
    # was read a minute ago, the other six minutes ago (stale).
    for t in tracked[:4]:
        ctx.tracker.mark_polled(t.mint, T0, source="pumpfun_rest")
    never = {t.mint for t in tracked[4:6]}
    mayhem_fresh, mayhem_stale = kinds["mayhem"][0], kinds["mayhem"][1]
    ctx.tracker.observe(dataclasses.replace(ctx.tracker.get(mayhem_fresh), mayhem_state="active"))  # type: ignore[arg-type]
    ctx.tracker.mark_polled(mayhem_fresh, RECEIVED - timedelta(minutes=1), source="pumpfun_rest")
    ctx.tracker.observe(dataclasses.replace(ctx.tracker.get(mayhem_stale), mayhem_state="active"))  # type: ignore[arg-type]
    ctx.tracker.mark_polled(mayhem_stale, RECEIVED - timedelta(minutes=6), source="pumpfun_rest")
    curves = _FakeCurves()
    ctx = dataclasses.replace(ctx, curves=curves)
    await chain_once(ctx)
    monkeypatch.setattr(
        "hunter_meme_worker.collect.utcnow", lambda: RECEIVED + timedelta(seconds=1)
    )
    read = await poll_once(ctx)
    assert set(curves.calls) == never | {mayhem_stale}, (
        "only what the mirror alone teaches: the never-read mints and the stale agent"
    )
    assert read == 0 and mayhem_fresh not in curves.calls, "the fake mirror answers nothing"
    assert not [p for s, p in log if s.startswith("INSERT INTO meme_ingest_gaps")], (
        "the mints left to the chain are not a gap"
    )


async def test_a_failed_batch_is_counted_and_the_rest_poll_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch(monkeypatch)
    monkeypatch.setattr("hunter_meme_worker.collect.refresh_open_bets", _no_bets)
    kinds = _kinds()
    log: list[Any] = []
    tracked = [_tracked(m) for m in kinds["midlife"][:4]]
    ctx = _context(FakeChain(fail=RuntimeError("rpc down")), log, tracked=tracked)
    for t in tracked:
        ctx.tracker.mark_polled(t.mint, T0, source="pumpfun_rest")
    report = await chain_once(ctx)
    assert report.failed and report.read == 0 and log == []
    assert ctx.state.chain_ok_at is None and not chain_covered(ctx, RECEIVED)
    assert ctx.sources is not None and ctx.sources[SOLANA_RPC].last_error == "RuntimeError"
    curves = _FakeCurves()
    ctx = dataclasses.replace(ctx, curves=curves)
    monkeypatch.setattr("hunter_meme_worker.collect.utcnow", lambda: RECEIVED)
    await poll_once(ctx)
    assert set(curves.calls) == {t.mint for t in tracked}, "no chain: the full REST plan"
    limited = _context(
        FakeChain(fail=RateLimited("429", exchange="pumpfun", retry_after_s=5)),
        log,
        tracked=tracked,
    )
    report = await chain_once(limited)
    assert report.failed and all(limited.state.absences[t.mint] == RATE_LIMITED for t in tracked)
    assert limited.sources is not None and limited.sources[SOLANA_RPC].last_error == RATE_LIMITED


async def test_an_empty_tracked_set_costs_nothing_and_still_covers() -> None:
    ctx = _context(FakeChain(), [], tracked=[])
    report = await chain_once(ctx)
    assert report.calls == 0 and report.read == 0 and ctx.state.chain_ok_at is not None


class _FakeCurves:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def get_curve_state(self, mint: str) -> Any:
        self.calls.append(mint)
        raise RuntimeError("no mirror in this test")


async def _no_bets(ctx: Any) -> frozenset[str]:
    return frozenset()
