"""T4.91 (EXP-M24) against a real Postgres: the entry at the pullback on
the event lane. A copy of ``flow_v2/1`` with ``entry_pullback_pct "5"`` /
``entry_pullback_window_s 60`` arms at the gate pass instead of proposing;
deterministic synthetic tapes (``TradeEvent`` decode stubbed at the lane's own
seam, ``event_gate_eval.trade_events_from_logs``) then prove: the proposal is
emitted at the right trade with the quote of that moment and the block; no
pullback -> no proposal + a ``no_pullback`` trail row with its tape; a creator
sale during the wait kills the entry; a feed gap or a changed set is censored,
never a kill; a failed trail write keeps its rows; absent params -> the proposal is exactly
``evaluate_gate`` + the tape evidence, as before T4.91; and the 15-second lane
never proposes for a pullback set. Run alone (``timeout 590``).
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
from sqlalchemy import text

import hunter_meme_worker.event_gate_eval as event_gate_eval
import hunter_meme_worker.event_gate_pullback as event_gate_pullback
from hunter_core.db.session import role_session
from hunter_exchanges.pumpfun.models import NormalizedCurveTrade
from hunter_exchanges.pumpfun.rpc_ws_models import LogsNotification
from hunter_meme_worker.entry_pullback import (
    ARMED,
    EVENT_LANE_ONLY,
    NO_PULLBACK,
    EntryPullback,
    price_of,
)
from hunter_meme_worker.event_gate_eval import apply_notification, evaluate_mint
from hunter_meme_worker.event_gate_pullback import (
    expire_pullbacks,
    fire_pullbacks,
    flush_pullback_trail,
)
from hunter_meme_worker.event_gate_rows import SERIES_EVENT, build_event_row
from hunter_meme_worker.event_gate_trail import capture_tape, with_evidence
from hunter_meme_worker.lab_fast import fast_gate_step
from hunter_meme_worker.lab_repo import load_active_rule_sets
from hunter_meme_worker.lab_values import money_str
from hunter_meme_worker.proposals import evaluate_gate
from hunter_meme_worker.repo import insert_snapshot
from hunter_meme_worker.repo_fast import insert_fast_rows

from .test_event_gate_integration import (
    CREATED,
    INITIAL_REAL_TOKEN,
    WORKER,
    _holders_pair,
    _lab,
    _patch_holders,
    _prime_state,
    _proposal_count,
    _radar,
    _rt,
    _seed_caches,
)
from .test_lab_fast import _fast_row, _flow_set, _plant_token
from .test_lab_persistence import _snapshot

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

    from hunter_meme_worker.event_gate_runtime import EventGateRuntime
    from hunter_meme_worker.lab import LabContext

pytestmark = pytest.mark.integration

T0 = CREATED + timedelta(seconds=130)
VTOK = INITIAL_REAL_TOKEN * Decimal("1.10")
"""``_prime_state``'s reserves: 60 SOL over this many tokens is the state at t0."""
M0 = Decimal(60)


async def _seed_pullback_set(
    factory: async_sessionmaker[AsyncSession], engine: AsyncEngine, mint: str, *, lab: LabContext
) -> str:
    """``_seed_caches``' own shape, the copied set carrying the two keys in the
    database — so the params go through ``RuleSetSpec.from_params`` exactly as
    the worker loads them."""
    rule_set = await _flow_set(engine)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE meme_rule_sets SET params = params || CAST(:extra AS jsonb) WHERE id = :id"
            ),
            {"id": rule_set, "extra": '{"entry_pullback_pct": "5", "entry_pullback_window_s": 60}'},
        )
    await _plant_token(
        factory, mint, created_at=CREATED, creator=f"C_{mint}", symbol=f"S{mint[-6:]}"
    )
    photo = CREATED + timedelta(seconds=10)
    async with role_session(factory, db_role=WORKER) as session:
        await insert_snapshot(session, _snapshot(mint, photo, "34", "946000000"))
        await insert_fast_rows(session, [_fast_row(mint, photo + timedelta(seconds=1), photo)])
    async with role_session(factory, db_role=WORKER) as session:
        specs = [s for s in await load_active_rule_sets(session) if s.id == rule_set]
    assert specs[0].entry_pullback == EntryPullback(pct=Decimal(5), window_s=60)
    await fast_gate_step(lab, specs, {}, now=photo + timedelta(seconds=2))
    assert lab.caches is not None and [s.id for s in lab.caches.specs] == [rule_set]
    return rule_set


def _stub_decode(monkeypatch: pytest.MonkeyPatch, trades: dict[str, NormalizedCurveTrade]) -> None:
    """The lane's own decode seam: a notification's single log line names the
    synthetic ``TradeEvent`` it carries."""

    def events(logs: tuple[str, ...]) -> tuple[str, ...]:
        return logs

    def normalized(event: str, **_kw: object) -> NormalizedCurveTrade:
        return trades[event]

    monkeypatch.setattr(event_gate_eval, "trade_events_from_logs", events)
    monkeypatch.setattr(event_gate_eval, "normalized_curve_trade", normalized)


def _trade(
    mint: str, key: str, *, s: float, ratio: str, trader: str = "OTHER", side: str = "buy"
) -> NormalizedCurveTrade:
    """A fill received ``s`` seconds after t0 whose post-trade price is
    ``ratio`` x the price at t0 (``vsol = 60 x ratio`` over the same tokens)."""
    at = T0 + timedelta(seconds=s)
    return NormalizedCurveTrade(
        mint=mint,
        slot=5000 + int(s * 10),
        signature=f"sig-{key}",
        trader=trader,
        side=side,  # type: ignore[arg-type]
        lamports=Decimal(100_000_000),
        token_amount=Decimal(1_000_000_000),
        virtual_sol_reserves=M0 * Decimal(ratio),
        virtual_token_reserves=VTOK,
        real_sol_reserves=Decimal(33),
        real_token_reserves=INITIAL_REAL_TOKEN * Decimal("0.90"),
        creator=f"C_{mint}",
        mayhem=False,
        block_time=at,
        received_at=at,
    )


def _feed(rt: EventGateRuntime, mint: str, trade: NormalizedCurveTrade, sub_id: int = 77) -> None:
    rt.subs_by_logical[sub_id] = mint
    notif = LogsNotification(
        subscription_id=sub_id,
        kind="logs",
        slot=trade.slot,
        signature=trade.signature,
        err=None,
        logs=(trade.signature.removeprefix("sig-"),),
        received_at=trade.received_at,
    )
    assert apply_notification(rt, notif) == mint
    rt.pullback.mark_processed(notif.received_at)


async def _fire(rt: EventGateRuntime, mint: str, now: datetime) -> None:
    """The lane decides synchronously; the insert is the pool's — joined here."""
    fire_pullbacks(rt, mint, now)
    await rt.pullback_inserts.join()


async def _rows(factory: async_sessionmaker[AsyncSession], sql: str, **params: Any) -> list[Any]:
    async with role_session(factory, db_role=WORKER) as session:
        return list((await session.execute(text(sql), params)).mappings())


async def _armed(
    factory: async_sessionmaker[AsyncSession],
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[str, str, EventGateRuntime]:
    mint = f"PB_{uuid4().hex[:12]}"
    lab = _lab(factory)
    rule_set = await _seed_pullback_set(factory, engine, mint, lab=lab)
    rt = _rt(_radar(factory), lab)
    _prime_state(rt, mint, as_of=T0)
    _patch_holders(monkeypatch, mint, T0)
    await evaluate_mint(rt, mint, T0)
    assert await _proposal_count(factory, mint) == 0, "armed, not proposed"
    assert rt.pullback.size == 1 and rt.pullback.armed == 1
    # Re-judged while armed (every debounce): never re-armed, no tape captured, nothing queued.
    captured, queued = rt.tapes.pending, rt.pullback.drain_trail()
    await evaluate_mint(rt, mint, T0 + timedelta(milliseconds=200))
    assert rt.pullback.armed == 1 and rt.tapes.pending == captured
    assert rt.pullback.drain_trail() == [] and [row.refusal for row, _t in queued] == [ARMED]
    for row, tape in queued:  # back exactly as queued at t0 (with its tape)
        rt.pullback.queue_trail(row, tape)
    return mint, rule_set, rt


async def test_the_proposal_is_emitted_at_the_first_trade_that_touches_the_pullback(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mint, rule_set, rt = await _armed(db_session_factory, db_engine, monkeypatch)
    trades = {
        "up": _trade(mint, "up", s=5, ratio="1.10"),  # new max: 1.10 x M0
        "dip4": _trade(mint, "dip4", s=8, ratio="1.056"),  # 1.10 x 0.96: 4 %, not yet
        "dip5": _trade(mint, "dip5", s=12, ratio="1.045"),  # 1.10 x 0.95: exactly 5 % - fires
        "after": _trade(mint, "after", s=13, ratio="0.90"),
    }
    _stub_decode(monkeypatch, trades)
    for key in ("up", "dip4"):
        _feed(rt, mint, trades[key])
        await _fire(rt, mint, trades[key].received_at)
        assert await _proposal_count(db_session_factory, mint) == 0
    _feed(rt, mint, trades["dip5"])
    decided = T0 + timedelta(seconds=12, milliseconds=5)
    await _fire(rt, mint, decided)
    assert rt.pullback.triggered == 1 and rt.pullback.proposed == 1 and rt.pullback.size == 0
    (proposal,) = await _rows(
        db_session_factory,
        "SELECT id, proposed_at, features_end_time, quote, reasons, status FROM meme_proposals "
        "WHERE mint = :m",
        m=mint,
    )
    assert proposal["proposed_at"] == decided and proposal["features_end_time"] == T0
    assert proposal["status"] == "approved"
    block = proposal["reasons"][-1]
    prices = [price_of(M0 * Decimal(r), VTOK) for r in ("1", "1.10", "1.045")]
    t0_price, armed_max, trigger_price = (money_str(p) for p in prices if p is not None)
    assert block == {
        "feature": "entry_pullback",
        "version": 1,
        "t0": T0.isoformat(),
        "armed_max_price": armed_max,
        "t0_price": t0_price,
        "trigger_price": trigger_price,
        "trigger_at": (T0 + timedelta(seconds=12)).isoformat(),
        "trigger_signature": "sig-dip5",
        "trigger_slot": 5120,
        "pct": "5",
        "window_s": 60,
        "waited_s": "12.005",
    }
    assert proposal["reasons"][0]["series"] == SERIES_EVENT
    assert any(r.get("feature") == "decision_tape" for r in proposal["reasons"]), "t0's tape"
    # The quote is the market at the trigger, not at t0.
    assert proposal["quote"]["virtual_sol_reserves"] == money_str(M0 * Decimal("1.045"))
    # The trail: armed at t0 (limit = pct), the proposal (refusal NULL) at the decision.
    await flush_pullback_trail(rt)
    trail = await _rows(
        db_session_factory,
        'SELECT as_of, refusal, "limit" FROM meme_gate_refusals_by_mint '
        "WHERE mint = :m AND rule_set_id = CAST(:rs AS uuid) AND as_of >= :t0 ORDER BY as_of",
        m=mint,
        rs=rule_set,
        t0=T0,  # the seed's own too-young near-miss is not this test's
    )
    assert [(r["as_of"], r["refusal"]) for r in trail] == [(T0, ARMED), (decided, None)]
    assert trail[0]["limit"] == Decimal(5)
    # The tape of the decision instant is linked to the proposal.
    await rt.tapes.flush(db_session_factory)
    (tape,) = await _rows(
        db_session_factory,
        "SELECT proposal_ids FROM meme_decision_tapes WHERE mint = :m AND as_of = :at",
        m=mint,
        at=decided,
    )
    assert [str(i) for i in tape["proposal_ids"]] == [str(proposal["id"])]
    # A later dip never proposes twice.
    _feed(rt, mint, trades["after"])
    await _fire(rt, mint, T0 + timedelta(seconds=14))
    assert await _proposal_count(db_session_factory, mint) == 1


async def test_no_pullback_in_the_window_is_a_named_non_entry_with_its_tape(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mint, rule_set, rt = await _armed(db_session_factory, db_engine, monkeypatch)
    trades = {
        "a": _trade(mint, "a", s=10, ratio="1.20"),
        "b": _trade(mint, "b", s=20, ratio="1.16"),  # 3.33 % below 1.20: the deepest, not 5 %
        "c": _trade(mint, "c", s=60, ratio="1.30"),  # the deadline itself is inside - no fire
    }
    _stub_decode(monkeypatch, trades)
    for trade in trades.values():
        _feed(rt, mint, trade)
        await _fire(rt, mint, trade.received_at)
    expire_pullbacks(rt, T0 + timedelta(seconds=61))
    assert rt.pullback.size == 1, "no frame received after the deadline was folded yet"
    rt.pullback.mark_processed(T0 + timedelta(seconds=60, milliseconds=400))  # a slot frame
    expired_at = T0 + timedelta(seconds=61)
    expire_pullbacks(rt, expired_at)
    assert rt.pullback.size == 0 and rt.pullback.expired_no_pullback == 1
    await flush_pullback_trail(rt)
    assert await _proposal_count(db_session_factory, mint) == 0
    trail = await _rows(
        db_session_factory,
        'SELECT as_of, refusal, value, "limit" FROM meme_gate_refusals_by_mint '
        "WHERE mint = :m AND rule_set_id = CAST(:rs AS uuid) AND as_of >= :t0 ORDER BY as_of",
        m=mint,
        rs=rule_set,
        t0=T0,  # the seed's own too-young near-miss is not this test's
    )
    assert [(r["as_of"], r["refusal"]) for r in trail] == [(T0, ARMED), (expired_at, NO_PULLBACK)]
    assert trail[1]["value"] == Decimal("3.333333") and trail[1]["limit"] == Decimal(5)
    await rt.tapes.flush(db_session_factory)
    tapes = await _rows(
        db_session_factory,
        "SELECT as_of, cardinality(proposal_ids) AS n FROM meme_decision_tapes "
        "WHERE mint = :m ORDER BY as_of",
        m=mint,
    )
    assert [(t["as_of"], t["n"]) for t in tapes] == [(T0, 0), (expired_at, 0)]


async def test_a_creator_sale_during_the_wait_kills_the_entry(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mint, rule_set, rt = await _armed(db_session_factory, db_engine, monkeypatch)
    dump = _trade(mint, "dump", s=15, ratio="0.80", trader=f"C_{mint}", side="sell")
    _stub_decode(monkeypatch, {"dump": dump})
    _feed(rt, mint, dump)  # the creator's own sale is the pullback that fires
    killed_at = T0 + timedelta(seconds=15, milliseconds=3)
    await _fire(rt, mint, killed_at)
    assert rt.pullback.killed_by_recheck == 1 and rt.pullback.proposed == 0
    await flush_pullback_trail(rt)
    assert await _proposal_count(db_session_factory, mint) == 0
    trail = await _rows(
        db_session_factory,
        "SELECT as_of, refusal FROM meme_gate_refusals_by_mint "
        "WHERE mint = :m AND rule_set_id = CAST(:rs AS uuid) AND as_of >= :t0 ORDER BY as_of",
        m=mint,
        rs=rule_set,
        t0=T0,  # the seed's own too-young near-miss is not this test's
    )
    assert [(r["as_of"], r["refusal"]) for r in trail] == [
        (T0, ARMED),
        (killed_at, "pullback_killed:creator_sold_during_wait"),
    ]


async def test_a_changed_rule_set_censors_the_entry(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mint, _rule_set, rt = await _armed(db_session_factory, db_engine, monkeypatch)
    caches = rt.lab.caches
    assert caches is not None
    (spec,) = caches.specs
    caches.specs = (replace(spec, entry_pullback=EntryPullback(pct=Decimal(8), window_s=60)),)
    dip = _trade(mint, "dip", s=5, ratio="0.90")
    _stub_decode(monkeypatch, {"dip": dip})
    _feed(rt, mint, dip)
    await _fire(rt, mint, T0 + timedelta(seconds=6))
    assert rt.pullback.censored == 1 and rt.pullback.killed_by_recheck == 0
    assert await _proposal_count(db_session_factory, mint) == 0
    (row,) = [r for r, _tape in rt.pullback.drain_trail() if r.refusal != ARMED]
    assert row.refusal == "pullback_censored:spec_changed"


async def test_a_feed_gap_during_the_wait_is_censored_even_when_a_trade_fires(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Astra (diff review): the same gap must not be "did not enter" (0) when
    the price later touched the pullback and "censored" when it did not."""
    mint, _rule_set, rt = await _armed(db_session_factory, db_engine, monkeypatch)
    state = rt.book.get(mint)
    assert state is not None
    state.mark_gap(T0 + timedelta(seconds=3))  # a reconnect during the wait
    dip = _trade(mint, "dip", s=5, ratio="0.90")
    _stub_decode(monkeypatch, {"dip": dip})
    _feed(rt, mint, dip)
    await _fire(rt, mint, T0 + timedelta(seconds=6))
    assert (rt.pullback.censored, rt.pullback.killed_by_recheck, rt.pullback.proposed) == (1, 0, 0)
    (row,) = [r for r, _tape in rt.pullback.drain_trail() if r.refusal != ARMED]
    assert row.refusal == "pullback_censored:feed_gap"


async def test_a_failed_trail_write_keeps_the_rows_for_the_next_flush(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Astra (diff review): a timeout on the flush must not lose the ``armed``
    row — the population of EXP-M24 is those rows."""
    mint, rule_set, rt = await _armed(db_session_factory, db_engine, monkeypatch)

    async def broken(*_args: object, **_kwargs: object) -> int:
        raise TimeoutError("statement timeout")

    monkeypatch.setattr(event_gate_pullback, "write_refusal_trail", broken)
    with pytest.raises(TimeoutError):
        await flush_pullback_trail(rt)
    assert rt.pullback.trail_write_failed == 1
    monkeypatch.undo()
    await flush_pullback_trail(rt)
    trail = await _rows(
        db_session_factory,
        "SELECT refusal FROM meme_gate_refusals_by_mint "
        "WHERE mint = :m AND rule_set_id = CAST(:rs AS uuid) AND as_of = :t0",
        m=mint,
        rs=rule_set,
        t0=T0,
    )
    assert [r["refusal"] for r in trail] == [ARMED]


async def test_absent_params_propose_exactly_what_the_gate_and_the_tape_say(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pre-T4.91 contract, byte for byte: the inserted row is
    ``with_evidence(evaluate_gate(...).drafts, capture_tape(...))`` at the same
    instant (every column but the random id); nothing is armed."""
    mint = f"PB_{uuid4().hex[:12]}"
    lab = _lab(db_session_factory)
    await _seed_caches(db_session_factory, db_engine, mint, lab=lab)
    rt = _rt(_radar(db_session_factory), lab)
    _prime_state(rt, mint, as_of=T0)
    _patch_holders(monkeypatch, mint, T0)
    caches = lab.caches
    assert caches is not None
    (spec,) = caches.specs
    assert spec.entry_pullback is None
    state = rt.book.get(mint)
    assert state is not None
    row = build_event_row(
        caches.base_rows[mint],
        state,
        as_of=T0,
        reserves=rt.reserves.get(mint),
        holders_readings=_holders_pair(T0),
    )
    expected = with_evidence(
        evaluate_gate(
            spec,
            [row],
            now=T0,
            ttl_s=lab.config.lab_proposal_ttl_s,
            already_open=frozenset(),
            pedigree={mint: caches.pedigree[mint]} if mint in caches.pedigree else {},
            e2b=None,
        ).drafts,
        capture_tape(rt, state, as_of=T0, series=SERIES_EVENT),
    )
    await evaluate_mint(rt, mint, T0)
    assert rt.pullback.armed == 0 and rt.pullback.size == 0
    (stored,) = await _rows(
        db_session_factory,
        "SELECT rule_set_id::text, origin, status, proposed_at, expires_at, features_end_time, "
        "quote, reasons, suggested, decision, decided_by, decided_at FROM meme_proposals "
        "WHERE mint = :m",
        m=mint,
    )
    (draft,) = expected
    assert dict(stored) == {
        "rule_set_id": draft.rule_set_id,
        "origin": draft.origin,
        "status": draft.status,
        "proposed_at": draft.proposed_at,
        "expires_at": draft.expires_at,
        "features_end_time": draft.features_end_time,
        "quote": draft.quote,
        "reasons": draft.reasons,
        "suggested": draft.suggested,
        "decision": draft.decision,
        "decided_by": draft.decided_by,
        "decided_at": draft.decided_at,
    }


async def test_the_fifteen_second_lane_never_proposes_for_a_pullback_set(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    mint = f"PB_{uuid4().hex[:12]}"
    lab = _lab(db_session_factory)
    rule_set = await _seed_pullback_set(db_session_factory, db_engine, mint, lab=lab)
    photo = CREATED + timedelta(seconds=120)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await insert_snapshot(session, _snapshot(mint, photo, "34", "946000000"))
        await insert_fast_rows(session, [_fast_row(mint, photo + timedelta(seconds=2), photo)])
        specs = [s for s in await load_active_rule_sets(session) if s.id == rule_set]
    refusals: dict[str, Any] = {}
    _rows_seen, proposed = await fast_gate_step(
        lab, specs, refusals, now=photo + timedelta(seconds=3)
    )
    assert proposed == 0 and await _proposal_count(db_session_factory, mint) == 0
    assert refusals[specs[0].name][EVENT_LANE_ONLY] == 1
    as_of = photo + timedelta(seconds=2)
    trail = await _rows(
        db_session_factory,
        "SELECT refusal FROM meme_gate_refusals_by_mint "
        "WHERE mint = :m AND rule_set_id = CAST(:rs AS uuid) AND as_of = :at",
        m=mint,
        rs=rule_set,
        at=as_of,
    )
    assert trail == [], "a gate pass the lane cannot act on is not a proposal in the trail"
