"""``hunter_meme_worker.event_state`` / ``event_book`` (T4.52b-2): the T4.52b-1
fixtures replayed through ``MintEventState`` give the same buys/sells/unique
buyers as counting the fixture directly; a trade received after ``as_of``
never counts; a window shorter than a minute is ``event_feed_warming``; the
drawdown guard is O(1) at the newest event and exact before it."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from hunter_exchanges.pumpfun.decode import BondingCurveAccount, decode_bonding_curve_account
from hunter_exchanges.pumpfun.models import NormalizedCurveTrade
from hunter_exchanges.pumpfun.trade_event import normalized_curve_trade, trade_events_from_logs
from hunter_indicators.meme.drawdown import STALE
from hunter_indicators.meme.fast import compute_fast
from hunter_meme_worker.event_book import EventBook
from hunter_meme_worker.event_state import (
    EVENT_FEED_WARMING,
    CurvePoint,
    MintEventState,
)
from hunter_meme_worker.features_tape import TapeTrade, tape_for

pytestmark = pytest.mark.unit

FIXTURES = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "exchange-adapters"
    / "tests"
    / "fixtures"
    / "pumpfun"
)
LAG = timedelta(milliseconds=500)
"""Synthetic receipt: half a second after the block time (the probe's p50)."""
SUBSCRIBED_AT = datetime(2026, 9, 18, 12, 48, 0, tzinfo=UTC)
"""A minute before the first fixture trade (12:49:04 UTC) — the tape is warm."""


def _fixture_trades() -> list[NormalizedCurveTrade]:
    trades: list[NormalizedCurveTrade] = []
    lines = (FIXTURES / "t452b_ws_logs_notifications_raw.jsonl").read_text().splitlines()
    for line in lines:
        result = json.loads(line)["params"]["result"]
        if result["value"]["err"] is not None:
            continue
        for event in trade_events_from_logs(result["value"]["logs"]):
            partial = normalized_curve_trade(
                event, slot=result["context"]["slot"], signature=result["value"]["signature"]
            )
            assert partial.block_time is not None
            trades.append(partial.model_copy(update={"received_at": partial.block_time + LAG}))
    assert len(trades) == 8, "the capture decoded eight TradeEvents (notes-T4.52b-1 §2)"
    return trades


def _fixture_accounts() -> list[tuple[int, BondingCurveAccount]]:
    lines = (FIXTURES / "t452b_ws_account_notifications_raw.jsonl").read_text().splitlines()
    out: list[tuple[int, BondingCurveAccount]] = []
    for line in lines:
        result = json.loads(line)["params"]["result"]
        value = result["value"]
        out.append(
            (
                result["context"]["slot"],
                decode_bonding_curve_account(value["data"][0], owner=value["owner"]),
            )
        )
    return out


TRADES = _fixture_trades()
ACCOUNTS = _fixture_accounts()
MINTS = sorted({t.mint for t in TRADES})


def _replay() -> EventBook:
    book = EventBook(max_mints=150)
    for trade in TRADES:
        state = book.touch(trade.mint, at=SUBSCRIBED_AT)
        assert state is not None
        state.apply_trade(trade)
    return book


def test_the_replay_counts_what_the_fixture_counts() -> None:
    """Five mints, eight fills: per mint, ``tape_minute`` at the last receipt
    equals ``tape_for`` over the same fills built by hand, and the creator's
    sell on ``HMfRWjo6…`` is seen by the flow."""
    book = _replay()
    assert len(book) == len(MINTS) == 5
    creator_sells_seen = 0
    for mint in MINTS:
        mine = [t for t in TRADES if t.mint == mint]
        as_of = max(t.received_at for t in mine)
        state = book.get(mint)
        assert state is not None
        tape, reason = state.tape_minute(as_of)
        assert reason is None and tape is not None
        by_hand = tape_for(
            [
                TapeTrade(
                    t.block_time or t.received_at, t.received_at, t.trader, t.side, int(t.lamports)
                )
                for t in mine
            ],
            end_time=as_of,
            creator=mine[0].creator,
            covered_since=SUBSCRIBED_AT,
        )
        assert by_hand is not None
        assert (tape.buys, tape.sells, tape.unique_buyers) == (
            sum(1 for t in mine if t.side == "buy"),
            sum(1 for t in mine if t.side == "sell"),
            len({t.trader for t in mine if t.side == "buy" and t.trader != mine[0].creator}),
        )
        assert (tape.net_sol_flow, tape.volume_sol) == (by_hand.net_sol_flow, by_hand.volume_sol)
        assert tape.as_of == as_of and tape.window_s == 60
        flow = state.creator_flow(as_of)
        if flow.sells:
            creator_sells_seen += 1
            assert flow.net_seller is True and tape.creator_net_seller is True
            assert flow.sold_lamports == sum(
                int(t.lamports) for t in mine if t.side == "sell" and t.trader == t.creator
            )
        else:
            assert tape.creator_net_seller is None, "not covered from birth: unknown, not False"
    assert creator_sells_seen == 1
    assert sum(len(book.get(m).trades) for m in MINTS if book.get(m)) == 8  # type: ignore[union-attr]


def test_a_trade_received_after_as_of_never_counts() -> None:
    """Non-anticipation: the mint with three fills judged an instant before
    the third reached us has two — in the tape and in the fast series."""
    book = _replay()
    mint = max(MINTS, key=lambda m: sum(1 for t in TRADES if t.mint == m))
    mine = sorted((t for t in TRADES if t.mint == mint), key=lambda t: t.received_at)
    assert len(mine) == 3
    state = book.get(mint)
    assert state is not None
    just_before = mine[2].received_at - timedelta(milliseconds=1)
    tape, reason = state.tape_minute(just_before)
    assert reason is None and tape is not None
    assert tape.buys + tape.sells == 2
    assert state.creator_flow(just_before).sells + state.creator_flow(just_before).buys <= 2
    dd_before = state.recent_drawdown(just_before)
    photos = state.fast_points()
    assert len(photos) == 3
    usable = [p for p in photos if p.received_at <= just_before]
    assert len(usable) == 2
    fast = compute_fast(photos, as_of=just_before, initial_real_token_reserves=None)
    assert fast.snapshot_observed_at is None or fast.snapshot_observed_at <= just_before
    at_latest = state.recent_drawdown(mine[2].received_at)
    assert dd_before.reason in (None, STALE) and at_latest.reason in (None, STALE)


def test_a_window_shorter_than_a_minute_is_warming_not_a_zero() -> None:
    received = TRADES[0].received_at
    state = MintEventState(mint=TRADES[0].mint, subscribed_at=received - timedelta(seconds=2))
    state.apply_trade(TRADES[0])
    tape, reason = state.tape_minute(received + timedelta(seconds=57))
    assert (tape, reason) == (None, EVENT_FEED_WARMING), "59 s of coverage is not a minute"
    tape, reason = state.tape_minute(received + timedelta(seconds=59))
    assert reason is None and tape is not None and tape.buys + tape.sells == 1
    state.mark_gap(received + timedelta(seconds=30))
    tape, reason = state.tape_minute(received + timedelta(seconds=59))
    assert (tape, reason) == (None, EVENT_FEED_WARMING), "a gap re-warms the tape"
    assert state.gaps == 1


def test_account_notifications_feed_the_photos_with_a_market_cap() -> None:
    state = MintEventState(mint="any", subscribed_at=SUBSCRIBED_AT)
    at = SUBSCRIBED_AT + timedelta(seconds=61)
    for i, (slot, account) in enumerate(ACCOUNTS):
        state.apply_account(account, slot=slot, received_at=at + timedelta(seconds=i))
    assert state.total_supply == Decimal(1_000_000_000)
    assert state.slot == max(slot for slot, _ in ACCOUNTS)
    newest = state.newest_point
    assert newest is not None and newest.source == "account"
    assert newest.mcap_sol is not None and newest.mcap_sol > 0
    assert newest.real_sol == Decimal(ACCOUNTS[-1][1].real_sol_reserves) / Decimal(10**9)
    assert all(p.mcap_sol is not None for p in state.fast_points())


def test_a_trade_before_any_account_has_no_market_cap_but_a_real_sol() -> None:
    state = MintEventState(mint=TRADES[1].mint, subscribed_at=SUBSCRIBED_AT)
    state.apply_trade(TRADES[1])
    photo = state.newest_point
    assert photo is not None and photo.mcap_sol is None, "no total supply yet: no quote"
    assert photo.real_sol == TRADES[1].real_sol_reserves
    known = MintEventState(
        mint=TRADES[1].mint, subscribed_at=SUBSCRIBED_AT, total_supply=Decimal(10**9)
    )
    known.apply_trade(TRADES[1])
    assert known.newest_point is not None and known.newest_point.mcap_sol is not None


def _photo(state: MintEventState, age_s: float, real_sol: str, *, at: datetime) -> None:
    observed = at - timedelta(seconds=age_s)
    state.apply_photo(
        CurvePoint(observed, observed + LAG, Decimal(30), Decimal(real_sol), Decimal(1), False)
    )


def test_the_drawdown_guard_is_o1_at_the_newest_event_and_exact_before_it() -> None:
    """KB-0118: the peak 67 s old is not recent with N = 60 s; 40 s old is;
    no photo for 30 s is unknown; an ``as_of`` before the newest receipt
    falls back to the exact fold without counting the future."""
    at = SUBSCRIBED_AT + timedelta(seconds=120)
    taxcoin = MintEventState(mint="TAXCOIN", subscribed_at=SUBSCRIBED_AT)
    for age, value in ((67, "29.638"), (55, "6"), (20, "5.5"), (3, "5.252")):
        _photo(taxcoin, age, value, at=at)
    assert taxcoin.recent_drawdown(at).drawdown_pct == Decimal("0.124667")
    assert taxcoin.recent_drawdown(at, window_s=120).drawdown_pct == Decimal("0.822795")
    fresh = MintEventState(mint="fresh", subscribed_at=SUBSCRIBED_AT)
    for age, value in ((40, "29.638"), (20, "12"), (3, "5.252")):
        _photo(fresh, age, value, at=at)
    dd, peak_age, reason = fresh.recent_drawdown(at)
    assert (dd, peak_age, reason) == (Decimal("0.822795"), Decimal("40.000"), None)
    assert len(fresh.peaks) == 3, "a falling series is all non-dominated: nothing popped"
    assert fresh.recent_drawdown(at + timedelta(seconds=28)) == (None, None, STALE)
    # Before the newest receipt: the 5,252 photo is in the future, so the
    # newest known is the 12 SOL photo and the fall is 1 − 12 / 29,638.
    earlier = at - timedelta(seconds=10)
    dd, peak_age, reason = fresh.recent_drawdown(earlier)
    assert reason is None and peak_age == Decimal("30.000")
    assert dd == (Decimal(1) - Decimal(12) / Decimal("29.638")).quantize(Decimal("0.000001"))


def test_the_book_is_bounded_and_evicts_the_idle() -> None:
    book = EventBook(max_mints=2)
    a = book.touch("a", at=SUBSCRIBED_AT)
    b = book.touch("b", at=SUBSCRIBED_AT + timedelta(seconds=10))
    assert a is not None and b is not None
    assert book.touch("c", at=SUBSCRIBED_AT) is None and book.refused == 1
    assert book.touch("a", at=SUBSCRIBED_AT + timedelta(seconds=99)) is a, (
        "touch never re-subscribes"
    )
    assert a.subscribed_at == SUBSCRIBED_AT
    b.apply_trade(TRADES[0].model_copy(update={"mint": "b"}))
    idle = book.evict_older_than(at=SUBSCRIBED_AT + timedelta(seconds=200), max_idle_s=150)
    assert idle == ["a"] and "a" not in book and len(book) == 1
    assert book.evict("b") is b and len(book) == 0
    with pytest.raises(ValueError):
        EventBook(max_mints=0)


def test_the_creator_booleans_are_false_only_when_covered_from_birth() -> None:
    trade = TRADES[3]  # a non-creator sell
    assert trade.trader != trade.creator
    born = trade.block_time or trade.received_at
    covered = MintEventState(mint=trade.mint, subscribed_at=born - LAG, first_seen_at=born)
    covered.apply_trade(trade)
    assert covered.covered_from_birth and covered.creator_flow().net_seller is False
    late = MintEventState(
        mint=trade.mint, subscribed_at=born + timedelta(seconds=6), first_seen_at=born
    )
    late.apply_trade(trade)
    assert not late.covered_from_birth and late.creator_flow().net_seller is None
    covered.mark_gap(born + timedelta(seconds=30))
    assert not covered.covered_from_birth, "a gap breaks the proof of coverage"


MINT_X = "4k3Dyjzvzp8eYnbNBGVfL5V1Z6VpAmoEsFmPtnxJhMKZ"
CREATOR_X = "CreatorWa11etAddress1111111111111111111111"


def _curve_trade(
    *, slot: int, side: str, trader: str, at: datetime, tokens: Decimal = Decimal(100)
) -> NormalizedCurveTrade:
    return NormalizedCurveTrade(
        mint=MINT_X,
        slot=slot,
        signature=f"sig-{slot}-{trader}",
        trader=trader,
        side=side,  # type: ignore[arg-type]
        lamports=Decimal(1_000_000),
        token_amount=tokens,
        virtual_sol_reserves=Decimal(31),
        virtual_token_reserves=Decimal(1_000_000_000),
        real_sol_reserves=Decimal(30),
        real_token_reserves=Decimal(900_000_000),
        creator=CREATOR_X,
        mayhem=False,
        block_time=at,
        received_at=at,
    )


def test_expects_create_slot_learns_the_slot_from_the_first_trade_only() -> None:
    """T4.70 (notes-T4.66.md §7, P0): a state subscribed at the ``create``
    instant (``expects_create_slot``) takes its ``crowd.create_slot`` from the
    very first trade notification only -- never a later one -- and the
    creator itself is never admitted as an early wallet (``crowd.py``'s own
    rule, unchanged)."""
    born = datetime(2026, 9, 20, 0, 0, tzinfo=UTC)
    state = MintEventState(mint=MINT_X, subscribed_at=born, first_seen_at=born)
    state.expects_create_slot = True
    # The creator's own dev-buy, in the create transaction itself: slot 100.
    state.apply_trade(_curve_trade(slot=100, side="buy", trader=CREATOR_X, at=born))
    assert state.crowd.create_slot == 100
    assert state.expects_create_slot is False
    assert state.creation_block_buyers == frozenset({CREATOR_X})
    # A second buyer in the same slot (bundled with the create) joins the set.
    state.apply_trade(_curve_trade(slot=100, side="buy", trader="EARLY_1", at=born))
    assert state.creation_block_buyers == frozenset({CREATOR_X, "EARLY_1"})
    # Slot 102 is still within the 3-slot rule (100, 101, 102); 103 is not.
    state.apply_trade(_curve_trade(slot=102, side="buy", trader="EARLY_2", at=born))
    state.apply_trade(_curve_trade(slot=103, side="buy", trader="TOO_LATE", at=born))
    assert state.crowd.early_wallets == frozenset({"EARLY_1", "EARLY_2"})
    assert "TOO_LATE" not in state.crowd.early_wallets
    assert CREATOR_X not in state.crowd.early_wallets  # never the creator
    # A later notification never overwrites the slot already learned.
    state.apply_trade(_curve_trade(slot=999, side="buy", trader="LATER", at=born))
    assert state.crowd.create_slot == 100


def test_a_mint_subscribed_late_never_infers_a_create_slot() -> None:
    """A mint the periodic sync (not ``subscribe_at_create``) subscribed to
    keeps ``expects_create_slot`` false by default -- the safe 10-buyers
    fallback (T4.66) stays, never a slot guessed from an arbitrary trade."""
    born = datetime(2026, 9, 20, 0, 0, tzinfo=UTC)
    state = MintEventState(mint=MINT_X, subscribed_at=born, first_seen_at=born)
    state.apply_trade(_curve_trade(slot=500, side="buy", trader="X", at=born))
    assert state.crowd.create_slot is None
    assert state.creation_block_buyers == frozenset()


def test_a_rule_set_names_the_guard_or_reads_exactly_as_frozen() -> None:
    """``lab_models._gate_from_params`` (T4.52b-2): the three keys parse from
    the JSON strings; a set without them is the same gate it always was."""
    from hunter_meme_worker.lab_models import RuleSetSpec

    from .test_paper_engine import PARAMS as V0_PARAMS

    identity = {
        "id": "01994d00-6c1a-7000-8000-000000000013",
        "name": "flow_v2",
        "version": "8",
        "kind": "research_only",
        "exp_ref": "EXP-M13",
        "status": "active",
        "code_ref": "hunter_indicators.meme.rules:evaluate_entry+evaluate_exit",
    }
    frozen = RuleSetSpec.from_params(**identity, params=V0_PARAMS)
    assert frozen.gate.max_recent_drawdown_pct is None
    assert (frozen.gate.recent_drawdown_window_s, frozen.gate.recent_drawdown_max_gap_s) == (60, 30)
    assert "max_recent_drawdown_pct" not in frozen.gate.as_parameters()
    guarded = RuleSetSpec.from_params(
        **identity,
        params={**V0_PARAMS, "max_recent_drawdown_pct": "0.50", "recent_drawdown_window_s": 120},
    )
    assert guarded.gate.max_recent_drawdown_pct == Decimal("0.50")
    assert guarded.gate.recent_drawdown_window_s == 120
    assert guarded.gate.recent_drawdown_max_gap_s == 30
    assert guarded.gate.as_parameters()["recent_drawdown_window_s"] == "120"
