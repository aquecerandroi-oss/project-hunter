"""``MintEventState.crowd`` (T4.66, EXP-M19): the T4.52b-1 fixtures replayed
through the state populate the four crowd features exactly as counting the
fixture by hand does; a subscription that did not cover the mint from birth
leaves the early set unknown; a gap propagates; ``build_event_row`` carries
the four onto the ``GateRow`` and the trail decodes them."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from hunter_indicators.meme.crowd import NO_EARLY_WALLETS, NOT_COVERED_FROM_BIRTH
from hunter_indicators.meme.rules import EntryFeatures, EntryGate
from hunter_meme_worker.event_book import EventBook
from hunter_meme_worker.gate_refusal_trail import decode_value_limit
from hunter_meme_worker.lab_models import _gate_from_params

from .test_event_state import LAG, MINTS, SUBSCRIBED_AT, TRADES

pytestmark = pytest.mark.unit

HELD_THEN_SOLD = "68EKa7Y5"
"""The one fixture mint with a buy: ``2taY1k…`` bought 1 007 046 290 932
subunits at 12:49:04 and sold exactly that at 12:49:54 (50 s later)."""


def _replay(*, from_birth: bool) -> EventBook:
    book = EventBook(max_mints=150)
    for trade in TRADES:
        state = book.touch(
            trade.mint, at=SUBSCRIBED_AT, first_seen_at=SUBSCRIBED_AT if from_birth else None
        )
        assert state is not None
        state.apply_trade(trade)
    return book


def test_the_replay_populates_the_crowd_features_from_the_fixture() -> None:
    book = _replay(from_birth=True)
    for mint in MINTS:
        mine = [t for t in TRADES if t.mint == mint]
        as_of = max(t.received_at for t in mine)
        state = book.get(mint)
        assert state is not None
        f = state.crowd_features(as_of)
        assert f.window_reason is None, mint  # subscribed a minute before: the window is covered
        start = as_of - timedelta(seconds=30)
        first_trade: dict[str, datetime | None] = {}
        for t in sorted(mine, key=lambda t: t.block_time or t.received_at):
            first_trade.setdefault(t.trader, t.block_time)
        in_window = [t for t in mine if t.block_time is not None and start < t.block_time <= as_of]
        assert f.new_wallets_30s == len(
            {t.trader for t in in_window if (first_trade[t.trader] or as_of) > start}
        )
        assert f.quick_flip_share_30s == Decimal(0)  # no fixture wallet sold within 20 s of buying
        if mint.startswith(HELD_THEN_SOLD):
            assert state.crowd.early_wallets == {mine[0].trader}
            assert f.early_retention_pct == Decimal("0.000000")
            assert f.early_age_s == Decimal("50.500")  # 12:49:04 buy, judged at 12:49:54 + lag
            assert f.early_reason is None
        else:
            assert (f.early_retention_pct, f.early_reason) == (None, NO_EARLY_WALLETS)


def test_the_retention_is_whole_before_the_early_wallet_sells() -> None:
    book = _replay(from_birth=True)
    mint = next(m for m in MINTS if m.startswith(HELD_THEN_SOLD))
    state = book.get(mint)
    assert state is not None
    mine = [t for t in TRADES if t.mint == mint]
    before_sell = mine[-1].received_at - timedelta(milliseconds=1)
    f = state.crowd_features(before_sell)
    assert f.early_retention_pct == Decimal("1.000000")
    assert f.early_age_s == Decimal("50.499")


def test_a_subscription_that_missed_the_birth_leaves_the_early_set_unknown() -> None:
    book = _replay(from_birth=False)
    mint = next(m for m in MINTS if m.startswith(HELD_THEN_SOLD))
    state = book.get(mint)
    assert state is not None
    as_of = max(t.received_at for t in TRADES if t.mint == mint)
    f = state.crowd_features(as_of)
    assert (f.early_retention_pct, f.early_age_s, f.early_reason) == (
        None,
        None,
        NOT_COVERED_FROM_BIRTH,
    )
    assert f.new_wallets_30s is not None  # the window criteria need only the window covered


def test_a_gap_propagates_to_the_crowd_ledger() -> None:
    book = _replay(from_birth=True)
    mint = next(m for m in MINTS if m.startswith(HELD_THEN_SOLD))
    state = book.get(mint)
    assert state is not None
    as_of = max(t.received_at for t in TRADES if t.mint == mint)
    state.mark_gap(as_of)
    f = state.crowd_features(as_of + timedelta(seconds=10))
    assert f.early_retention_pct is None and f.new_wallets_30s is None
    assert state.crowd.covered_since == as_of == state.covered_since


def test_the_trades_carry_their_token_amount_from_the_event_bytes() -> None:
    assert all(t.token_amount is not None and t.token_amount > 0 for t in TRADES)
    assert LAG == timedelta(milliseconds=500)


def test_gate_from_params_reads_the_four_keys_as_strings_and_the_trail_decodes_them() -> None:
    params = {
        "gate_key": "fluxo_e_holders",
        "gate_version": 3,
        "min_age_s": 30,
        "max_age_s": 300,
        "min_progress_pct": "5",
        "max_progress_pct": "50",
        "max_participation_pct": "1",
        "min_early_retention_pct": "0.70",
        "min_early_age_s": 60,
        "min_new_wallets_30s": 5,
        "max_quick_flip_share_30s": "0.20",
    }
    gate: EntryGate = _gate_from_params("flow_v2", "10", params)
    assert gate.min_early_retention_pct == Decimal("0.70")
    assert gate.min_early_age_s == 60
    assert gate.min_new_wallets_30s == 5
    assert gate.max_quick_flip_share_30s == Decimal("0.20")
    plain = _gate_from_params("flow_v2", "6", {k: v for k, v in params.items() if "early" not in k})
    assert plain.min_early_retention_pct is None and plain.min_early_age_s is None
    features = EntryFeatures(
        mint="M",
        age_s=90,
        progress_pct=Decimal(10),
        creator_net_seller=False,
        curve_volume_1m_sol=Decimal(10),
        intended_size_sol=Decimal("0.05"),
        early_retention_pct=Decimal("0.4"),
        early_age_s=Decimal(45),
        new_wallets_30s=2,
        quick_flip_share_30s=Decimal("0.5"),
    )
    assert decode_value_limit("early_retention_below_min", features, gate) == (
        Decimal("0.4"),
        Decimal("0.70"),
    )
    assert decode_value_limit("early_age_below_min", features, gate) == (Decimal(45), 60)
    assert decode_value_limit("new_wallets_below_min", features, gate) == (2, 5)
    assert decode_value_limit("quick_flip_above_max", features, gate) == (
        Decimal("0.5"),
        Decimal("0.20"),
    )
    assert decode_value_limit("early_retention_unknown", features, gate) == (None, None)


def test_build_event_row_carries_the_four_crowd_features_onto_the_gate_row() -> None:
    from hunter_indicators.meme.crowd import CrowdTrade
    from hunter_meme_worker.event_gate_rows import build_event_row

    from .test_event_gate_pure import NOW, _base_row, _state

    born = NOW - timedelta(seconds=120)
    state = _state("MINT", subscribed_at=born, first_seen_at=born)
    state.creator = "DEV"
    state.crowd.creator = "DEV"
    for i in range(10):
        at = born + timedelta(seconds=1 + i)
        state.crowd.push(CrowdTrade(at, at, f"S{i}", "buy", Decimal(100)))
    at = NOW - timedelta(seconds=10)
    state.crowd.push(CrowdTrade(at, at, "S0", "sell", Decimal(25)))
    state.crowd.push(CrowdTrade(at, at, "N1", "buy", Decimal(50)))
    base = _base_row("MINT", created_at=born)
    row = build_event_row(base, state, as_of=NOW, reserves=None, holders_readings=())
    assert row.early_retention_pct == Decimal("0.975000")  # 975 of 1 000 still held; N1 is the 11th
    assert row.early_age_s == Decimal("119.000")
    assert row.new_wallets_30s == 1
    assert row.quick_flip_share_30s == Decimal(0)
    assert base.early_retention_pct is None  # the 15-second row never carries them
