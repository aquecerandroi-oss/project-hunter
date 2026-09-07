"""Stop and target fire on the last **valid spot trade**, and on nothing else.

``docs/plans/M3.md``, joint decision item 3: the trigger is the last valid SPOT
trade — never ``mark_price``, which is a perpetual concept
(``docs/PIPELINE.md:205``) and does not transplant. "Valid" is the whole
question, so it is spelled out and tested: an age budget measured against the
exchange's own trade clock, and a strictly advancing trade id.

The third state is the one that matters most: **unavailable** is not
"not triggered". A tape we cannot see does not prove the stop was not hit, and
saying "no trigger" there is how a protection quietly disappears.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from hunter_core.domain.enums import TradeDirection
from hunter_core.execution.triggers import (
    MARKING_POLICY_VERSION,
    MarkingPolicy,
    ProtectedPosition,
    check_triggers,
)

from .conftest import NOW, seconds, trade

POSITION = ProtectedPosition(
    position_id=uuid.UUID(int=1),
    qty=Decimal("10"),
    direction=TradeDirection.LONG,
    stop_price=Decimal("95"),
    target_prices=(Decimal("110"), Decimal("120")),
)


def test_the_policy_is_versioned_and_named_after_the_trade_it_trusts() -> None:
    assert MARKING_POLICY_VERSION == "spot_last_trade_v1"
    assert MarkingPolicy().max_trade_age_s == Decimal(10)


def test_a_trade_above_the_stop_and_below_the_target_triggers_nothing() -> None:
    result = check_triggers(POSITION, [trade("100", trade_id="101")], now=NOW)
    assert result.state == "not_triggered"
    assert result.kind is None
    assert result.accepted_trade_id == 101


def test_a_trade_at_or_below_the_stop_fires_the_stop() -> None:
    result = check_triggers(POSITION, [trade("95", trade_id="101")], now=NOW)
    assert (result.state, result.kind) == ("triggered", "stop")
    assert result.trade_price == Decimal("95")
    assert result.trade_id == "101"
    assert result.marking_policy_version == MARKING_POLICY_VERSION


def test_a_trade_at_or_above_a_target_fires_the_target() -> None:
    result = check_triggers(POSITION, [trade("110", trade_id="101")], now=NOW)
    assert (result.state, result.kind) == ("triggered", "target")
    assert result.target_index == 0


def test_the_earlier_crossing_wins_when_the_batch_crosses_both_sides() -> None:
    """Chronology decides, not a preference for one protection.

    The tape prints 110 (target) and then 94 (stop) inside one batch. Reporting
    the stop because it is "more protective" would book an exit at a price the
    position reached *after* the target already fired, and the equity curve
    would show a loss the market never handed us.
    """
    batch = [trade("110", trade_id="101"), trade("94", trade_id="102")]
    result = check_triggers(POSITION, batch, now=NOW)
    assert (result.kind, result.trade_id) == ("target", "101")


def test_every_new_trade_is_examined_in_order_not_only_the_last_one() -> None:
    """The intermediate touch is the whole point.

    95 prints and the tape recovers to 101 in the same batch. Looking only at
    the newest trade would report "not triggered" for a stop that really was
    hit — the position keeps running with its protection already gone.
    """
    batch = [
        trade("101", trade_id="101"),
        trade("95", trade_id="102"),
        trade("101", trade_id="103"),
    ]
    result = check_triggers(POSITION, batch, now=NOW)
    assert (result.state, result.kind, result.trade_id) == ("triggered", "stop", "102")


def test_a_trade_older_than_the_age_budget_is_unavailable_never_not_triggered() -> None:
    stale = trade("100", trade_id="101", ts=NOW - seconds(45))
    result = check_triggers(POSITION, [stale], now=NOW)
    assert result.state == "unavailable"
    assert result.reason == "stale_trade"
    assert result.age_s == Decimal(45)


def test_a_trade_from_the_future_is_unavailable() -> None:
    ahead = trade("100", trade_id="101", ts=NOW + seconds(5))
    result = check_triggers(POSITION, [ahead], now=NOW)
    assert (result.state, result.reason) == ("unavailable", "trade_from_the_future")


def test_no_trade_at_all_is_unavailable() -> None:
    result = check_triggers(POSITION, [], now=NOW)
    assert (result.state, result.reason) == ("unavailable", "no_trade")


def test_a_known_tape_gap_is_unavailable_even_with_a_fresh_trade() -> None:
    """A gap in collection does not license the sentence "the stop was not hit"."""
    result = check_triggers(POSITION, [trade("100", trade_id="101")], now=NOW, tape_gap=True)
    assert (result.state, result.reason) == ("unavailable", "tape_gap")


def test_a_trade_id_that_went_backwards_is_dropped_and_the_watermark_holds() -> None:
    """Out-of-sequence prints are replays; they do not move the mark."""
    result = check_triggers(
        POSITION, [trade("95", trade_id="99")], now=NOW, last_accepted_trade_id=100
    )
    assert result.state == "unavailable"
    assert result.reason == "no_new_trade"
    assert result.accepted_trade_id == 100


def test_a_repeated_trade_does_not_refresh_freshness_but_stays_usable() -> None:
    """Astra, point 2: a duplicate does not renew the age, and the last accepted
    trade keeps working until it expires — requiring a *new* id every cycle would
    blind the stop in a quiet market."""
    same = trade("100", trade_id="100", ts=NOW - seconds(3))
    result = check_triggers(POSITION, [same], now=NOW, last_accepted_trade_id=100)
    assert result.state == "not_triggered"
    assert result.age_s == Decimal(3)
    assert result.accepted_trade_id == 100


def test_a_non_numeric_trade_id_is_unavailable_not_silently_ordered_as_text() -> None:
    """``"9" > "10"`` lexicographically; ordering ids as text is a silent bug."""
    result = check_triggers(POSITION, [trade("95", trade_id="abc")], now=NOW)
    assert (result.state, result.reason) == ("unavailable", "trade_id_not_numeric")


def test_a_position_without_protections_is_never_triggered() -> None:
    bare = POSITION.model_copy(update={"stop_price": None, "target_prices": ()})
    result = check_triggers(bare, [trade("1", trade_id="101")], now=NOW)
    assert result.state == "not_triggered"


def test_spot_has_no_short_side_so_a_short_position_is_refused() -> None:
    with pytest.raises(ValueError, match="spot"):
        ProtectedPosition(
            position_id=uuid.UUID(int=2),
            qty=Decimal("1"),
            direction=TradeDirection.SHORT,
            stop_price=Decimal("95"),
        )


def test_a_stop_above_a_target_is_refused_as_a_geometry_error() -> None:
    with pytest.raises(ValueError, match="below"):
        ProtectedPosition(
            position_id=uuid.UUID(int=3),
            qty=Decimal("1"),
            direction=TradeDirection.LONG,
            stop_price=Decimal("120"),
            target_prices=(Decimal("110"),),
        )


def test_the_age_budget_is_a_declared_number_not_a_measured_guarantee() -> None:
    """10 s is the declared initial budget (Astra: not empirically validated).

    Changing it changes the verdict, and the policy travels with the report so a
    later review can tell which budget produced which decision.
    """
    old = trade("95", trade_id="101", ts=NOW - seconds(15))
    assert check_triggers(POSITION, [old], now=NOW).state == "unavailable"
    generous = MarkingPolicy(max_trade_age_s=Decimal(30))
    assert check_triggers(POSITION, [old], now=NOW, policy=generous).kind == "stop"


def test_a_crossing_already_reported_is_not_reported_again_and_the_next_one_is() -> None:
    """A trigger is an observation, not a liquidation (Astra, T3.4 diff review 2).

    Position of 10 with a partial target of 4: the tape prints 110 then 94. The
    first call reports the target. Calling again with the watermark it returned
    must report the **stop** for the units still open — not the same target
    again, which would leave the remainder unprotected while the log looks busy.
    """
    batch = [trade("110", trade_id="101"), trade("94", trade_id="102")]
    first = check_triggers(POSITION, batch, now=NOW)
    assert (first.kind, first.trade_id, first.accepted_trade_id) == ("target", "101", 101)
    second = check_triggers(
        POSITION, batch, now=NOW, last_accepted_trade_id=first.accepted_trade_id
    )
    assert (second.kind, second.trade_id) == ("stop", "102")


def test_a_trade_we_have_not_received_yet_is_unavailable() -> None:
    """The exchange clock says 12:00:00, our socket has not seen it at 11:59:59.

    Deciding a stop from a print that has not arrived is deciding from the
    future: it cannot be reproduced, and after a restart the same evaluation
    would answer differently.
    """
    not_yet = trade("94", trade_id="101").model_copy(update={"received_at": NOW + seconds(5)})
    result = check_triggers(POSITION, [not_yet], now=NOW)
    assert (result.state, result.reason) == ("unavailable", "trade_not_yet_received")


def test_a_malformed_trade_id_never_erases_the_watermark() -> None:
    """Otherwise the next call accepts 99 after 100 was already processed."""
    result = check_triggers(
        POSITION, [trade("94", trade_id="abc")], now=NOW, last_accepted_trade_id=100
    )
    assert (result.state, result.reason) == ("unavailable", "trade_id_not_numeric")
    assert result.accepted_trade_id == 100
