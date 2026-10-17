"""`would_delete_stop` (I-X-2) and the SLTP request guards (I-SL-1, I-SL-4, I-SL-6)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from hunter_exchanges.mt5.guards import (
    EntryEffect,
    entry_effect,
    entry_stop_refusal,
    sltp_refusal,
    would_delete_stop,
)
from hunter_exchanges.mt5.models import EntryKind, Side

from .factories import entry, position, sltp, spec

pytestmark = pytest.mark.unit

D = Decimal
QUOTE = (D("130400"), D("130405"))  # bid, ask: the default long position (sl 130000) is fine
SHORT_QUOTE = (D("129000"), D("129005"))


# ------------------------------------------------------------------ would_delete_stop


@pytest.mark.parametrize(
    ("pos_side", "pos_vol", "req_side", "req_vol", "effect"),
    [
        (None, "0", Side.BUY, "1", EntryEffect.OPEN),
        (Side.BUY, "1", Side.BUY, "1", EntryEffect.INCREASE),
        (Side.SELL, "2", Side.SELL, "1", EntryEffect.INCREASE),
        (Side.BUY, "3", Side.SELL, "1", EntryEffect.REDUCE),
        (Side.BUY, "3", Side.SELL, "3", EntryEffect.CLOSE),
        (Side.BUY, "3", Side.SELL, "4", EntryEffect.INVERT),
        (Side.SELL, "1", Side.BUY, "2", EntryEffect.INVERT),
    ],
)
def test_entry_effect_in_netting(
    pos_side: Side | None, pos_vol: str, req_side: Side, req_vol: str, effect: EntryEffect
) -> None:
    positions = [] if pos_side is None else [position(side=pos_side, volume=D(pos_vol))]
    assert entry_effect(entry(side=req_side, volume=D(req_vol)), positions) is effect


def test_effect_ignores_positions_on_other_symbols() -> None:
    other = position(symbol="WDOX26")
    assert entry_effect(entry(), [other]) is EntryEffect.OPEN


@pytest.mark.parametrize("kind", [EntryKind.MARKET, EntryKind.LIMIT])
def test_increase_with_sl_zero_would_delete_the_stop(kind: EntryKind) -> None:
    req = entry(kind=kind, sl=D("0"))
    assert would_delete_stop(req, [position()]) is True
    assert entry_stop_refusal(req, [position()]) == "would_delete_stop"


def test_invert_with_sl_zero_would_delete_the_stop() -> None:
    req = entry(side=Side.SELL, volume=D("2"), sl=D("0"))
    assert would_delete_stop(req, [position()]) is True


@pytest.mark.parametrize("req_vol", ["1"])
def test_close_and_reduce_are_never_refused_for_the_stop(req_vol: str) -> None:
    pos = position(volume=D("3"))
    reduce_ = entry(side=Side.SELL, volume=D(req_vol), sl=D("0"))
    close = entry(side=Side.SELL, volume=D("3"), sl=D("0"))
    assert would_delete_stop(reduce_, [pos]) is False
    assert would_delete_stop(close, [pos]) is False
    assert entry_stop_refusal(reduce_, [pos]) is None
    assert entry_stop_refusal(close, [pos]) is None


def test_increase_carrying_a_stop_is_not_a_deletion() -> None:
    assert would_delete_stop(entry(sl=D("130000")), [position()]) is False


def test_opening_from_flat_is_not_a_deletion_even_with_sl_zero() -> None:
    # No stop exists to delete; a naked entry is the risk engine's check 15, not this guard's.
    assert would_delete_stop(entry(sl=D("0")), []) is False


@pytest.mark.parametrize(
    ("pos_side", "pos_sl", "req_side", "req_sl", "refused"),
    [
        (Side.BUY, "130000", Side.BUY, "129000", True),  # long: lower sl is looser
        (Side.BUY, "130000", Side.BUY, "130000", False),
        (Side.BUY, "130000", Side.BUY, "130500", False),  # tighter
        (Side.SELL, "130000", Side.SELL, "131000", True),  # short: higher sl is looser
        (Side.SELL, "130000", Side.SELL, "130000", False),
        (Side.SELL, "130000", Side.SELL, "129500", False),
        (Side.BUY, "0", Side.BUY, "129000", False),  # naked position: nothing to loosen
    ],
)
def test_increase_that_loosens_the_stop_is_refused(
    pos_side: Side, pos_sl: str, req_side: Side, req_sl: str, refused: bool
) -> None:
    pos = position(side=pos_side, sl=D(pos_sl))
    req = entry(side=req_side, sl=D(req_sl))
    assert (entry_stop_refusal(req, [pos]) == "would_loosen_stop") is refused


def test_invert_with_a_stop_is_fine_a_new_position_has_its_own_stop() -> None:
    req = entry(side=Side.SELL, volume=D("2"), sl=D("131000"))
    assert entry_stop_refusal(req, [position(sl=D("130000"))]) is None


# ------------------------------------------------------------------ SLTP


def test_a_tightening_sltp_passes_every_guard() -> None:
    assert sltp_refusal(sltp(), position(), spec(), QUOTE) is None


def test_sltp_with_sl_zero_is_always_refused() -> None:
    assert sltp_refusal(sltp(sl=D("0")), position(), spec(), QUOTE) == "sl_missing"
    assert sltp_refusal(sltp(sl=D("0")), position(sl=D("0")), spec(), QUOTE) == "sl_missing"


def test_sltp_off_the_tick_grid_is_refused() -> None:
    assert sltp_refusal(sltp(sl=D("130102")), position(), spec(), QUOTE) == "sl_off_tick"
    assert sltp_refusal(sltp(tp=D("131003")), position(), spec(), QUOTE) == "tp_off_tick"


def test_sltp_may_clear_the_take_profit() -> None:
    assert sltp_refusal(sltp(tp=D("0")), position(tp=D("131000")), spec(), QUOTE) is None


def test_sltp_looser_than_the_confirmed_stop_is_refused_for_both_sides() -> None:
    long_ = position(sl=D("130000"))
    assert sltp_refusal(sltp(sl=D("129995")), long_, spec(), QUOTE) == "sl_looser_than_confirmed"
    short = position(side=Side.SELL, sl=D("130000"))
    assert (
        sltp_refusal(sltp(sl=D("130005"), floor_sl=D("130005")), short, spec(), QUOTE)
        == "sl_looser_than_confirmed"
    )
    assert (
        sltp_refusal(sltp(sl=D("129995"), floor_sl=D("130000")), short, spec(), SHORT_QUOTE) is None
    )


def test_sltp_looser_than_the_floor_is_refused_even_if_tighter_than_confirmed() -> None:
    pos = position(sl=D("130000"))
    req = sltp(sl=D("130050"), floor_sl=D("130100"))
    assert sltp_refusal(req, pos, spec(), QUOTE) == "sl_looser_than_floor"


def test_sltp_on_a_naked_position_only_needs_the_floor() -> None:
    pos = position(sl=D("0"))
    assert sltp_refusal(sltp(sl=D("130000"), floor_sl=D("130000")), pos, spec(), QUOTE) is None
    assert sltp_refusal(sltp(sl=D("129995"), floor_sl=D("130000")), pos, spec(), QUOTE) == (
        "sl_looser_than_floor"
    )


def test_sltp_needs_the_current_position_and_it_must_be_ours() -> None:
    assert sltp_refusal(sltp(), None, spec(), QUOTE) == "position_not_found"
    assert (
        sltp_refusal(sltp(), position(symbol="WDOX26"), spec(), QUOTE) == "position_symbol_mismatch"
    )
    assert sltp_refusal(sltp(), position(magic=1), spec(), QUOTE) == "position_magic_mismatch"
    assert (
        sltp_refusal(sltp(position_ticket=9), position(), spec(), QUOTE)
        == "position_ticket_mismatch"
    )


# ---------------------------------------------------------------- the touch (floor_unplaceable, I-SL-6)


def test_a_stop_on_the_wrong_side_of_the_touch_is_never_sent() -> None:
    bid, ask = QUOTE
    # Long: the stop must not sit above the bid (the position would be stopped out by the request).
    assert sltp_refusal(sltp(sl=bid), position(), spec(), QUOTE) is None  # at the bid: the bracket
    over = sltp(sl=bid + 5, floor_sl=bid + 5)
    assert sltp_refusal(over, position(), spec(), QUOTE) == "sl_wrong_side_of_touch"
    short = position(side=Side.SELL, sl=D("131000"))
    assert sltp_refusal(sltp(sl=ask, floor_sl=D("131000")), short, spec(), QUOTE) is None
    under = sltp(sl=ask - 5, floor_sl=D("131000"))
    assert sltp_refusal(under, short, spec(), QUOTE) == "sl_wrong_side_of_touch"


def test_the_target_must_not_be_on_the_wrong_side_either() -> None:
    bid, ask = QUOTE
    assert sltp_refusal(sltp(tp=ask), position(), spec(), QUOTE) is None
    assert sltp_refusal(sltp(tp=ask - 5), position(), spec(), QUOTE) == "tp_wrong_side_of_touch"
    short = position(side=Side.SELL, sl=D("131000"))
    ok = sltp(sl=D("130900"), tp=bid, floor_sl=D("131000"))
    assert sltp_refusal(ok, short, spec(), QUOTE) is None
    bad = sltp(sl=D("130900"), tp=bid + 5, floor_sl=D("131000"))
    assert sltp_refusal(bad, short, spec(), QUOTE) == "tp_wrong_side_of_touch"


def test_the_brokers_minimum_distance_moves_the_boundary() -> None:
    bid, _ = QUOTE
    far = spec(trade_stops_level=10)  # 10 points; point is 1
    assert sltp_refusal(sltp(sl=bid), position(), far, QUOTE) == "sl_wrong_side_of_touch"
    assert sltp_refusal(sltp(sl=bid - 10), position(), far, QUOTE) is None


def test_without_a_usable_quote_nothing_is_sent() -> None:
    assert sltp_refusal(sltp(), position(), spec(), None) == "quote_unavailable"
    for bad in ((D("0"), D("130405")), (D("130400"), D("0"))):
        assert sltp_refusal(sltp(), position(), spec(), bad) == "quote_invalid"
