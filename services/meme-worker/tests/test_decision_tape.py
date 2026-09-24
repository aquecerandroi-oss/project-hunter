"""T4.89 — what the event lane saw at the instant it decided (pure, no Docker).

R73 (``.claude/state/notes-R73.md`` §2/§6, KB-0153): the event lane decides on a
WS tape held in memory that was never persisted trade by trade, and
``meme_trades`` is a polling copy ~44 s late. ``capture_decision_tape`` is the
snapshot of that memory at the decision instant; these tests pin that it is
exactly the state at ``as_of`` — a trade that reached us later is never in it
(the look-ahead invariance pattern of ``.claude/state/r72/test_r72.py``).
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_exchanges.pumpfun.models import NormalizedCurveTrade
from hunter_meme_worker.decision_tape import (
    FEATURE,
    SLICE_MAX,
    STATE_AHEAD,
    DecisionTape,
    capture_decision_tape,
)
from hunter_meme_worker.decision_tape_creation import CREATION_SLOT_UNKNOWN
from hunter_meme_worker.event_gate_subscriptions import subscribe_at_create
from hunter_meme_worker.event_state import CurvePoint, MintEventState
from hunter_meme_worker.event_wallets import (
    COVERAGE_GAP,
    NOT_COVERED_FROM_BIRTH,
    TOKENS_UNKNOWN,
    WALLETS_OVERFLOW,
)
from hunter_meme_worker.features_tape import TapeTrade

from .test_event_gate_notify import MINT_A, NOW, FakeWs, _create, _runtime

pytestmark = pytest.mark.unit

BIRTH = datetime(2026, 9, 23, 20, 1, 0, tzinfo=UTC)
CREATOR = "HTkSYnCreator1111111111111111111111111111111"
SERIES = "meme_event_gate_v1"
SUPPLY = Decimal("1000000000")


def _trade(
    trader: str,
    side: str,
    *,
    at: datetime,
    sol: str,
    tokens: str | None = "1000",
    lag_ms: int = 400,
    real_sol: str = "10",
) -> NormalizedCurveTrade:
    return NormalizedCurveTrade(
        mint="AIRAAmint",
        slot=1000 + int((at - BIRTH).total_seconds()),
        signature=f"sig-{trader}-{at.isoformat()}",
        trader=trader,
        side=side,  # type: ignore[arg-type]
        lamports=Decimal(sol) * Decimal(1_000_000_000),
        token_amount=None if tokens is None else Decimal(tokens) * Decimal(1_000_000),
        virtual_sol_reserves=Decimal("40"),
        virtual_token_reserves=Decimal("800000000"),
        real_sol_reserves=Decimal(real_sol),
        real_token_reserves=Decimal("700000000"),
        creator=CREATOR,
        mayhem=False,
        block_time=at,
        received_at=at + timedelta(milliseconds=lag_ms),
    )


def _state(*, subscribed_at: datetime = BIRTH) -> MintEventState:
    state = MintEventState(
        mint="AIRAAmint", subscribed_at=subscribed_at, first_seen_at=BIRTH, total_supply=SUPPLY
    )
    state.creator = CREATOR
    return state


def _feed(state: MintEventState) -> datetime:
    """The creator buys 8 SOL at birth; A buys 2 then sells 0.5 worth; B buys
    1; C sells into it; a burst of small buys in the last 10 s. Returns the
    decision instant, 90 s after birth (the 60 s window is covered)."""
    state.apply_trade(
        _trade(CREATOR, "buy", at=BIRTH + timedelta(seconds=1), sol="8", tokens="200000000")
    )
    state.apply_trade(
        _trade("A", "buy", at=BIRTH + timedelta(seconds=40), sol="2", tokens="40000000")
    )
    state.apply_trade(
        _trade("B", "buy", at=BIRTH + timedelta(seconds=50), sol="1", tokens="19000000")
    )
    state.apply_trade(
        _trade("A", "sell", at=BIRTH + timedelta(seconds=70), sol="0.5", tokens="9000000")
    )
    state.apply_trade(
        _trade("C", "sell", at=BIRTH + timedelta(seconds=75), sol="0.25", tokens="5000000")
    )
    for i in range(3):
        at = BIRTH + timedelta(seconds=82 + i)
        state.apply_trade(
            _trade(f"D{i}", "buy", at=at, sol="0.1", tokens="1900000", real_sol="10.55")
        )
    return BIRTH + timedelta(seconds=90)


def test_the_windows_count_what_had_reached_us_and_the_60s_one_matches_the_gate() -> None:
    state = _state()
    as_of = _feed(state)
    tape = capture_decision_tape(state, as_of=as_of, series=SERIES)
    windows = tape.derived["windows"]
    assert windows["10s"] == {
        "buys": 3, "sells": 0, "buy_sol": "0.3", "sell_sol": "0", "net_sol": "0.3",
        "unique_buyers": 3,
    }  # fmt: skip
    assert windows["30s"]["buys"] == 3 and windows["30s"]["sells"] == 2
    assert windows["30s"]["net_sol"] == "-0.45"
    minute, reason = state.tape_minute(as_of)
    assert reason is None and minute is not None
    sixty = windows["60s"]
    assert (sixty["buys"], sixty["sells"], sixty["unique_buyers"]) == (
        minute.buys, minute.sells, minute.unique_buyers,
    )  # fmt: skip
    assert Decimal(sixty["net_sol"]) == minute.net_sol_flow


def test_the_largest_net_buyer_and_the_creator_since_birth_with_their_shares() -> None:
    state = _state()
    as_of = _feed(state)
    derived = capture_decision_tape(state, as_of=as_of, series=SERIES).derived
    top = derived["largest_net_buyer"]
    assert top["wallet"] == CREATOR and top["is_creator"] is True
    assert top["net_sol"] == "8" and top["net_tokens"] == "200000000"
    assert top["share_of_real_sol"] == str(
        (Decimal(8) / Decimal("10.55")).quantize(Decimal("0.000001"))
    )
    assert top["share_of_supply"] == "0.200000"
    assert derived["largest_holder"]["wallet"] == CREATOR
    creator = derived["creator"]
    assert creator["wallet"] == CREATOR and creator["buys"] == 1 and creator["sells"] == 0
    assert creator["net_sol"] == "8"
    ledger = derived["ledger"]
    # The seven wallets' net SOL is the curve's real SOL: seen since birth.
    assert ledger["reason"] is None and ledger["wallets"] == 7
    assert ledger["net_sol_total"] == "10.55" and ledger["reconcile_gap_sol"] == "0"
    assert derived["curve"]["real_sol"] == "10.55"


def test_a_trade_that_reached_us_after_the_decision_is_not_in_the_snapshot() -> None:
    """Look-ahead invariance: the snapshot is taken at ``as_of``; a fill that
    arrives later (even one whose block time is *before* ``as_of``) changes
    nothing already captured; and a capture asked for an instant the state
    has already moved past refuses by name rather than answer from a deque
    that may have evicted what that instant saw, or a ledger with the whale."""
    state = _state()
    as_of = _feed(state)
    before = capture_decision_tape(state, as_of=as_of, series=SERIES)
    frozen = json.dumps(before.reasons_block(), sort_keys=True)
    frozen_trades = json.dumps(before.trades_json(), sort_keys=True)
    late = _trade(
        "WHALE", "buy", at=as_of - timedelta(seconds=2), sol="30", tokens="300000000", lag_ms=5000
    )
    state.apply_trade(late)
    assert json.dumps(before.reasons_block(), sort_keys=True) == frozen
    assert json.dumps(before.trades_json(), sort_keys=True) == frozen_trades
    assert all(t["trader"] != "WHALE" for t in before.trades_json())
    assert before.derived["largest_net_buyer"]["wallet"] == CREATOR
    again = capture_decision_tape(state, as_of=as_of, series=SERIES)
    assert again.derived["reason"] == STATE_AHEAD
    assert again.trades == () and "windows" not in again.derived
    # At the new frontier the whale is there, and it is the largest buyer.
    later = capture_decision_tape(state, as_of=late.received_at, series=SERIES)
    assert later.derived["largest_net_buyer"]["wallet"] == "WHALE"


def test_the_slice_keeps_the_newest_known_trades_and_counts_the_window() -> None:
    state = _state()
    start = BIRTH + timedelta(seconds=61)
    for i in range(SLICE_MAX + 20):
        state.apply_trade(
            _trade(f"W{i}", "buy", at=start + timedelta(milliseconds=300 * i), sol="0.01")
        )
    as_of = start + timedelta(seconds=30)
    tape = capture_decision_tape(state, as_of=as_of, series=SERIES)
    assert tape.trades_in_window == SLICE_MAX + 20
    assert len(tape.trades) == SLICE_MAX
    rows = tape.trades_json()
    assert rows[-1]["trader"] == f"W{SLICE_MAX + 19}" and rows[0]["trader"] == "W20"
    assert set(rows[0]) == {"block_time", "received_at", "slot", "side", "sol", "tokens", "trader"}
    assert rows[0]["sol"] == "0.01" and rows[0]["tokens"] == "1000"
    assert rows[0]["slot"] == 1000 + int((start - BIRTH).total_seconds()) + 6  # W20, 300ms*20
    assert tape.derived["slice"] == {
        "trades": SLICE_MAX,
        "in_window": SLICE_MAX + 20,
        "max": SLICE_MAX,
    }


def test_a_ledger_that_did_not_see_the_birth_says_so_and_still_reports_since_when() -> None:
    late_subscription = BIRTH + timedelta(seconds=30)
    state = _state(subscribed_at=late_subscription)
    state.apply_trade(_trade("A", "buy", at=BIRTH + timedelta(seconds=40), sol="2"))
    as_of = BIRTH + timedelta(seconds=100)
    derived = capture_decision_tape(state, as_of=as_of, series=SERIES).derived
    assert derived["ledger"]["reason"] == NOT_COVERED_FROM_BIRTH
    assert derived["ledger"]["since"] == late_subscription.isoformat()
    assert derived["ledger"]["reconcile_gap_sol"] == "8"  # the curve holds 10, the ledger saw 2
    assert derived["largest_net_buyer"]["wallet"] == "A"


def test_a_coverage_gap_marks_the_ledger_and_the_uncovered_windows() -> None:
    state = _state()
    as_of = _feed(state)
    state.mark_gap(as_of - timedelta(seconds=20))
    derived = capture_decision_tape(state, as_of=as_of, series=SERIES).derived
    assert derived["ledger"]["reason"] == COVERAGE_GAP
    assert derived["ledger"]["gapped"] is True
    assert derived["windows"]["60s"] == {"reason": "window_not_covered"}
    assert derived["windows"]["30s"] == {"reason": "window_not_covered"}
    assert derived["windows"]["10s"]["buys"] == 0  # covered, and nothing since the gap


def test_the_curve_the_shares_divide_by_carries_its_two_clocks() -> None:
    """The newest photo that had reached us, whatever its source — and a photo
    that reaches the state after ``as_of`` is a state already ahead."""
    state = _state()
    as_of = _feed(state)
    photo = CurvePoint(
        observed_at=as_of - timedelta(seconds=3),
        received_at=as_of - timedelta(seconds=1),
        mcap_sol=None,
        real_sol=Decimal("10.55"),
        real_token=Decimal("1"),
        mayhem=False,
        source="account",
    )
    state.apply_photo(photo)
    curve = capture_decision_tape(state, as_of=as_of, series=SERIES).derived["curve"]
    assert curve["real_sol"] == "10.55" and curve["total_supply"] == "1000000000"
    assert curve["observed_at"] == photo.observed_at.isoformat()
    assert curve["received_at"] == photo.received_at.isoformat()
    state.apply_photo(replace(photo, received_at=as_of + timedelta(seconds=1)))
    ahead = capture_decision_tape(state, as_of=as_of, series=SERIES).derived
    assert ahead["reason"] == STATE_AHEAD and "curve" not in ahead


def test_the_reasons_block_is_json_and_named() -> None:
    state = _state()
    as_of = _feed(state)
    block = capture_decision_tape(state, as_of=as_of, series=SERIES).reasons_block()
    assert block["feature"] == FEATURE and block["version"] == 3
    assert block["kind"] == "evidence" and block["used_by_gate"] is False
    assert block["as_of"] == as_of.isoformat() and block["series"] == SERIES
    json.dumps(block)  # every value is already a JSON scalar (Decimal as str, UTC ISO)


def test_the_creator_buy_inside_the_create_is_seeded_once_and_never_twice() -> None:
    """The subscription opens after the create: the creator's own buy comes
    from the create frame; the same fill arriving over the WS after all (same
    signature) is not counted again."""
    state = _state()
    state.wallets.seed_initial_buy(
        CREATOR, sol=Decimal("8"), tokens=Decimal("200000000"), signature="sig-create"
    )
    echo = _trade(CREATOR, "buy", at=BIRTH, sol="8", tokens="200000000", real_sol="8")
    state.apply_trade(echo.model_copy(update={"signature": "sig-create"}))
    state.apply_trade(_trade("A", "buy", at=BIRTH + timedelta(seconds=5), sol="2", real_sol="10"))
    as_of = BIRTH + timedelta(seconds=70)
    derived = capture_decision_tape(state, as_of=as_of, series=SERIES).derived
    assert derived["creator"]["net_sol"] == "8" and derived["creator"]["buys"] == 1
    assert derived["ledger"]["creator_initial_buy_seeded"] is True
    assert derived["ledger"]["reason"] is None  # 8 + 2 = the curve's 10


def test_a_fill_without_a_token_amount_makes_token_sums_unknown_not_zero() -> None:
    state = _state()
    state.apply_trade(
        _trade("A", "buy", at=BIRTH + timedelta(seconds=1), sol="1", tokens=None, real_sol="1")
    )
    as_of = BIRTH + timedelta(seconds=70)
    derived = capture_decision_tape(state, as_of=as_of, series=SERIES).derived
    assert derived["ledger"]["reason"] == TOKENS_UNKNOWN
    assert derived["largest_holder"] is None
    top = derived["largest_net_buyer"]
    assert top["net_sol"] == "1" and top["net_tokens"] is None and top["share_of_supply"] is None


def test_a_full_ledger_says_its_maximum_is_partial(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hunter_meme_worker.event_wallets.MAX_WALLETS", 2)
    state = _state()
    for i, who in enumerate(("A", "B", "WHALE")):
        state.apply_trade(_trade(who, "buy", at=BIRTH + timedelta(seconds=1 + i), sol="1"))
    as_of = BIRTH + timedelta(seconds=70)
    derived = capture_decision_tape(state, as_of=as_of, series=SERIES).derived
    assert derived["ledger"]["reason"] == WALLETS_OVERFLOW and derived["ledger"]["overflow"] is True


async def test_subscribe_at_create_seeds_the_creators_buy_from_the_frame() -> None:
    rt = _runtime(FakeWs())
    event = _create(MINT_A, NOW).model_copy(
        update={
            "creator_initial_sol": Decimal("1.5"),
            "creator_initial_tokens": Decimal("50000000"),
        }
    )
    await subscribe_at_create(rt, event, now=NOW)
    state = rt.book.get(MINT_A)
    assert state is not None and state.wallets.seed_signature == "sig-create"
    flow = state.wallets.flows["CREATOR"]
    assert (flow.bought_lamports, flow.bought_subunits, flow.buys) == (
        1_500_000_000, 50_000_000_000_000, 1,
    )  # fmt: skip


async def test_a_create_frame_without_the_initial_buy_seeds_nothing() -> None:
    rt = _runtime(FakeWs())
    await subscribe_at_create(rt, _create(MINT_A, NOW), now=NOW)
    state = rt.book.get(MINT_A)
    assert state is not None and state.wallets.flows == {} and state.wallets.seed_signature is None


def test_the_ledger_reconciles_against_the_newest_trade_not_a_newer_account_photo() -> None:
    """The account subscription can run ahead of (or behind) the logs one: a
    photo showing a fill whose ``TradeEvent`` has not reached us would make a
    complete ledger look incomplete. The reconciliation reads the newest
    trade's own post-trade reserves; the shares still divide by the newest
    photo, and both are recorded."""
    state = _state()
    as_of = _feed(state)
    state.apply_photo(
        CurvePoint(
            observed_at=as_of - timedelta(seconds=1),
            received_at=as_of - timedelta(milliseconds=200),
            mcap_sol=None,
            real_sol=Decimal("12.55"),
            real_token=Decimal("1"),
            mayhem=False,
            source="account",
        )
    )
    derived = capture_decision_tape(state, as_of=as_of, series=SERIES).derived
    assert derived["ledger"]["reason"] is None
    assert derived["ledger"]["reconcile_real_sol"] == "10.55"
    assert derived["ledger"]["reconcile_gap_sol"] == "0"
    assert derived["curve"]["real_sol"] == "12.55"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(None, True), ("", True), ("on", True), ("off", False), (" OFF ", False), ("bogus", True)],
)
def test_the_decision_tape_kill_switch_defaults_on(
    monkeypatch: pytest.MonkeyPatch, raw: str | None, expected: bool
) -> None:
    from hunter_meme_worker.event_gate_config import decision_tape_enabled, load_event_gate_config

    if raw is None:
        monkeypatch.delenv("MEME_DECISION_TAPE", raising=False)
    else:
        monkeypatch.setenv("MEME_DECISION_TAPE", raw)
    assert decision_tape_enabled() is expected
    assert load_event_gate_config().decision_tape is expected


def test_creation_bundle_counts_sol_and_wallets_excluding_the_creator() -> None:
    """H-015: 3 wallets buy in the creation slot; a 4th buys later, in a
    different slot, and never counts toward the bundle."""
    state = _state()
    state.expects_create_slot = True
    state.wallets.seed_initial_buy(
        CREATOR, sol=Decimal("8"), tokens=Decimal("200000000"), signature="sig-create"
    )
    t0 = BIRTH + timedelta(seconds=1)
    state.apply_trade(_trade("X", "buy", at=t0, sol="1", real_sol="9"))
    state.apply_trade(_trade("Y", "buy", at=t0, sol="1", real_sol="10"))
    state.apply_trade(_trade("Z", "buy", at=t0, sol="1", real_sol="11"))
    later = t0 + timedelta(seconds=20)  # a different slot: outside the bundle
    state.apply_trade(_trade("LATER", "buy", at=later, sol="5", real_sol="16"))
    as_of = later + timedelta(seconds=60)
    bundle = capture_decision_tape(state, as_of=as_of, series=SERIES).derived["creation_bundle"]
    assert bundle["creation_slot"] == state.crowd.create_slot
    assert bundle["sol"] == "3" and bundle["wallets"] == 3
    assert bundle["creator_buy_sol"] == "8"
    assert bundle["reason"] is None
    assert bundle["slot_source"] == "first_trade_seen"
    assert bundle["create_signature"] is None  # seeded directly, not via subscribe_at_create
    assert bundle["early_slots"] == [
        {
            "slot": state.crowd.create_slot,
            "sol_others": "3",
            "wallets_others": 3,
            "creator_sol": "0",
        },
        {
            "slot": state.crowd.create_slot + 20,
            "sol_others": "5",
            "wallets_others": 1,
            "creator_sol": "0",
        },
    ]


def test_creation_bundle_excludes_a_creator_fill_seen_again_in_the_same_slot() -> None:
    """A creator buy that reaches the WS in the creation slot (not the seeded
    one, by signature) must never inflate the "other wallets" bucket."""
    state = _state()
    state.expects_create_slot = True
    state.wallets.seed_initial_buy(
        CREATOR, sol=Decimal("8"), tokens=Decimal("200000000"), signature="sig-create"
    )
    t0 = BIRTH + timedelta(seconds=1)
    state.apply_trade(_trade("X", "buy", at=t0, sol="1", real_sol="9"))
    state.apply_trade(_trade(CREATOR, "buy", at=t0, sol="2", real_sol="11"))
    as_of = t0 + timedelta(seconds=70)
    bundle = capture_decision_tape(state, as_of=as_of, series=SERIES).derived["creation_bundle"]
    assert bundle["sol"] == "1" and bundle["wallets"] == 1
    assert bundle["creator_buy_sol"] == "8"  # unchanged by the second, later fill
    # the second creator fill lands in early_slots' own creator_sol, never in sol_others
    assert bundle["early_slots"] == [
        {
            "slot": state.crowd.create_slot,
            "sol_others": "1",
            "wallets_others": 1,
            "creator_sol": "2",
        }
    ]


def test_creation_bundle_is_reported_when_only_the_token_amount_is_unknown() -> None:
    """Astra (T4.89b review), MEDIUM: ``tokens_unknown`` says a *token* amount
    is missing somewhere in the ledger — it says nothing about SOL, so it must
    never null out this SOL-only bundle."""
    state = _state()
    state.expects_create_slot = True
    t0 = BIRTH + timedelta(seconds=1)
    state.apply_trade(_trade("X", "buy", at=t0, sol="1", tokens=None, real_sol="1"))
    as_of = t0 + timedelta(seconds=70)
    derived = capture_decision_tape(state, as_of=as_of, series=SERIES).derived
    assert derived["ledger"]["reason"] == TOKENS_UNKNOWN
    bundle = derived["creation_bundle"]
    assert bundle["sol"] == "1" and bundle["wallets"] == 1 and bundle["reason"] is None


def test_creation_bundle_reason_is_named_when_the_mint_was_not_subscribed_at_create() -> None:
    state = _state()  # no subscribe_at_create: crowd.create_slot never learned
    as_of = _feed(state)
    bundle = capture_decision_tape(state, as_of=as_of, series=SERIES).derived["creation_bundle"]
    assert bundle["creation_slot"] is None
    assert bundle["reason"] == CREATION_SLOT_UNKNOWN
    assert bundle["sol"] is None and bundle["wallets"] is None
    assert bundle["creator_buy_sol"] is None  # never seeded either
    assert bundle["slot_source"] is None  # no slot to source
    assert bundle["create_signature"] is None


def test_creation_bundle_reason_mirrors_the_ledgers_coverage_gap() -> None:
    state = _state()
    state.expects_create_slot = True
    as_of = _feed(state)
    state.mark_gap(as_of - timedelta(seconds=20))
    derived = capture_decision_tape(state, as_of=as_of, series=SERIES).derived
    bundle = derived["creation_bundle"]
    assert bundle["creation_slot"] is not None
    assert bundle["reason"] == COVERAGE_GAP == derived["ledger"]["reason"]
    assert bundle["sol"] is None and bundle["wallets"] is None


def test_early_slots_are_bounded_to_five_in_arrival_order() -> None:
    """Coordinator decision (T4.89b, Astra's HIGH): raw evidence for research
    to align with the create tx's real slot, resolved retrospectively — kept
    even when the mint was not subscribed at create (``creation_slot`` stays
    unknown, but the first slots seen are still honest data)."""
    state = _state()
    t0 = BIRTH + timedelta(seconds=1)
    for i, who in enumerate(("A", "B", "C", "D", "E", "F")):  # 6 distinct slots
        state.apply_trade(_trade(who, "buy", at=t0 + timedelta(seconds=i), sol="1"))
    as_of = t0 + timedelta(seconds=70)
    bundle = capture_decision_tape(state, as_of=as_of, series=SERIES).derived["creation_bundle"]
    assert len(bundle["early_slots"]) == 5  # the 6th distinct slot (F) never gets a seat
    assert [e["slot"] for e in bundle["early_slots"]] == [
        1000 + i for i in range(1, 6)
    ]  # arrival order, not a later reshuffle
    assert bundle["early_slots"][0] == {
        "slot": 1001, "sol_others": "1", "wallets_others": 1, "creator_sol": "0",
    }  # fmt: skip


def test_early_slots_keep_updating_an_already_tracked_slot_after_the_cap() -> None:
    """Astra (T4.89b round 2) nice-to-have: the 5-slot cap bounds *distinct*
    slots, never a later trade landing in one already kept."""
    state = _state()
    t0 = BIRTH + timedelta(seconds=1)
    for i, who in enumerate(("A", "B", "C", "D", "E", "F")):  # A..E fill the cap; F is new
        state.apply_trade(_trade(who, "buy", at=t0 + timedelta(seconds=i), sol="1"))
    # a second buy lands back in A's own (already tracked) slot
    state.apply_trade(_trade("A2", "buy", at=t0, sol="4"))
    as_of = t0 + timedelta(seconds=70)
    bundle = capture_decision_tape(state, as_of=as_of, series=SERIES).derived["creation_bundle"]
    assert bundle["early_slots"][0] == {
        "slot": 1001, "sol_others": "5", "wallets_others": 2, "creator_sol": "0",
    }  # fmt: skip


def test_early_slots_wallets_others_is_bounded_and_trips_overflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Astra (T4.89b round 2), MEDIUM: a wallet set fed outside ``_flow`` must
    obey the same ``MAX_WALLETS`` ceiling — otherwise it grows past the
    ledger's bounded-memory guarantee, and a truncated count could be
    reported as exact."""
    monkeypatch.setattr("hunter_meme_worker.event_wallets.MAX_WALLETS", 2)
    state = _state()
    t0 = BIRTH + timedelta(seconds=1)
    for who in ("A", "B", "WHALE"):  # same slot: a 3rd distinct wallet overflows
        state.apply_trade(_trade(who, "buy", at=t0, sol="1"))
    as_of = t0 + timedelta(seconds=70)
    derived = capture_decision_tape(state, as_of=as_of, series=SERIES).derived
    assert derived["ledger"]["overflow"] is True
    bundle = derived["creation_bundle"]
    assert bundle["early_slots"][0]["wallets_others"] == 2  # never 3: the cap held
    assert bundle["sol"] is None and bundle["wallets"] is None  # overflow nulls the primary field


def test_creation_block_wallets_is_bounded_and_trips_overflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same guard as ``early_slots``, for the ``creation_slot``-gated bucket."""
    monkeypatch.setattr("hunter_meme_worker.event_wallets.MAX_WALLETS", 2)
    state = _state()
    state.expects_create_slot = True
    t0 = BIRTH + timedelta(seconds=1)
    for who in ("A", "B", "WHALE"):
        state.apply_trade(_trade(who, "buy", at=t0, sol="1"))
    as_of = t0 + timedelta(seconds=70)
    bundle = capture_decision_tape(state, as_of=as_of, series=SERIES).derived["creation_bundle"]
    assert len(state.wallets.creation_block_wallets) == 2  # never 3: the cap held
    assert bundle["sol"] is None and bundle["wallets"] is None


async def test_create_signature_is_recorded_even_without_an_initial_buy() -> None:
    """T4.89b (coordinator decision): research's handle to resolve the real
    creation slot over RPC must exist whether or not the creator also bought
    inside the ``create`` transaction."""
    rt = _runtime(FakeWs())
    event = _create(MINT_A, NOW)  # no creator_initial_sol/_tokens
    await subscribe_at_create(rt, event, now=NOW)
    state = rt.book.get(MINT_A)
    assert state is not None
    assert state.wallets.create_signature == event.signature == "sig-create"
    assert state.wallets.seed_signature is None  # no initial buy to seed
    as_of = NOW + timedelta(seconds=70)
    bundle = capture_decision_tape(state, as_of=as_of, series=SERIES).derived["creation_bundle"]
    assert bundle["create_signature"] == event.signature
    assert bundle["creator_buy_sol"] is None


def test_a_trades_slot_is_recorded_or_null_when_the_source_does_not_have_one() -> None:
    """Never invented: a fill built without a slot stays ``null`` in the row."""
    tape = DecisionTape(
        mint="M",
        series=SERIES,
        as_of=BIRTH,
        trades=(
            TapeTrade(
                block_time=BIRTH, received_at=BIRTH, trader="A", side="buy", sol_lamports=10**9
            ),
        ),
        trades_in_window=1,
        derived={},
    )
    assert tape.trades_json()[0]["slot"] is None


def test_a_capture_no_committed_row_explains_is_counted_unlinked() -> None:
    """code-reviewer (LOW): every insert lost its ``ON CONFLICT`` and no trail
    row of the instant is queued — the tape is lost, and counted; one still
    parked with its trail candidate is not lost (its trail write offers it)."""
    from hunter_meme_worker.event_gate_trail import record_tapes

    rt = _runtime(FakeWs())
    state = _state()
    tape = capture_decision_tape(state, as_of=_feed(state), series=SERIES)
    record_tapes(rt, "AIRAAmint", tape, [], None)
    assert rt.tapes.unlinked == 1 and rt.tapes.offered == 0
    rt.pending_tapes["AIRAAmint"] = tape
    record_tapes(rt, "AIRAAmint", tape, [], None)
    assert rt.tapes.unlinked == 1 and rt.pending_tapes["AIRAAmint"] is tape
