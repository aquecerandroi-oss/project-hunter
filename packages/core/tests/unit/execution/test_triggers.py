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
from hunter_core.domain.market import NormalizedTrade
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


@pytest.mark.parametrize(
    ("label", "broken", "expected_reason"),
    [
        (
            "received_at in the future (another host's clock)",
            trade("101", trade_id="101").model_copy(update={"received_at": NOW + seconds(2)}),
            "trade_not_yet_received",
        ),
        (
            "a trade id that is not a number",
            trade("101", trade_id="not-a-number"),
            "trade_id_not_numeric",
        ),
        (
            "an exchange timestamp in the future",
            trade("101", trade_id="101", ts=NOW + seconds(2)),
            "trade_from_the_future",
        ),
    ],
)
def test_one_broken_print_never_erases_a_stop_the_batch_already_showed(
    label: str, broken: NormalizedTrade, expected_reason: str
) -> None:
    """Review of 2026-09-07, blocker 1: a position left without protection.

    ``[100@90]`` alone triggers the stop. Validating the **whole** batch first
    meant that ``[100@90, 101 <broken>]`` answered ``unavailable`` and threw the
    90 away; on the next cycle the 90 is stale and the stop is simply gone. The
    crossing is evaluated over the validated prefix, and the rest of the batch is
    published as undecided — never as a reason to forget what we did see.
    """
    batch = [trade("90", trade_id="100"), broken]
    result = check_triggers(POSITION, batch, now=NOW)
    assert (result.state, result.kind) == ("triggered", "stop"), label
    assert (result.trade_id, result.trade_price) == ("100", Decimal("90"))
    assert result.accepted_trade_id == 100
    assert result.undecided_reason == expected_reason


def test_a_broken_print_still_makes_the_rest_of_the_batch_unavailable() -> None:
    """Nothing crossed in the prefix, so the question stays open, not answered.

    The same batch shape as above with a harmless 100: reporting
    ``not_triggered`` would claim we saw a tape we could not read.
    """
    ahead = trade("100", trade_id="101", ts=NOW + seconds(2))
    result = check_triggers(POSITION, [trade("100", trade_id="100"), ahead], now=NOW)
    assert (result.state, result.reason) == ("unavailable", "trade_from_the_future")
    assert result.accepted_trade_id is None


def test_a_crossing_below_the_stop_already_reported_is_never_called_not_triggered() -> None:
    """Review of 2026-09-07, item 8: a price under the stop labelled "no trigger".

    The stop already fired on trade 102 at 94 and the watermark says so. Handing
    the same print back published ``not_triggered`` with ``trade_price=94`` — a
    row that reads, in the panel and in a query, as "the stop was not hit at 94".
    """
    result = check_triggers(
        POSITION, [trade("94", trade_id="102")], now=NOW, last_accepted_trade_id=102
    )
    assert (result.state, result.reason) == ("unavailable", "already_reported")
    assert result.trade_price == Decimal("94")
    assert result.accepted_trade_id == 102


def test_an_unread_print_before_a_target_never_lets_the_target_be_reported_first() -> None:
    """Astra, T3.4b review, MUST-FIX 1: the stop that the watermark walked past.

    Watermark 99. The tape prints 100 at 90 (a stop) with ``received_at`` two
    seconds ahead — unreadable *now* — and then 101 at 110 (a target). Publishing
    the target moved the watermark to 101, and two seconds later, when the 90
    finally became readable, it was dropped as a regression: the stop was never
    reported at all.

    Chronology is the rule (a batch that crosses both sides reports what came
    first), and an undecided print **before** a target makes that chronology
    unknown. So the target waits, the watermark does not move, and the next cycle
    reports the stop it could finally read.
    """
    unread = trade("90", trade_id="100").model_copy(update={"received_at": NOW + seconds(2)})
    batch = [unread, trade("110", trade_id="101")]
    first = check_triggers(POSITION, batch, now=NOW, last_accepted_trade_id=99)
    assert (first.state, first.reason) == ("unavailable", "trade_not_yet_received")
    assert first.accepted_trade_id == 99

    later = NOW + seconds(3)
    readable = [trade("90", trade_id="100", ts=NOW), trade("110", trade_id="101", ts=NOW)]
    second = check_triggers(POSITION, readable, now=later, last_accepted_trade_id=99)
    assert (second.state, second.kind, second.trade_id) == ("triggered", "stop", "100")


def test_a_stop_is_published_even_with_an_unread_print_before_it() -> None:
    """The asymmetry, declared: protection first.

    A target waits for chronology because booking a profit that a hidden print
    may have preceded with a stop is the expensive mistake. A **stop** never
    waits: the print that crossed it really crossed it, and holding the
    protection back for a print we cannot read is the failure this whole module
    exists to prevent.
    """
    unread = trade("101", trade_id="100").model_copy(update={"received_at": NOW + seconds(2)})
    result = check_triggers(POSITION, [unread, trade("94", trade_id="101")], now=NOW)
    assert (result.state, result.kind, result.trade_id) == ("triggered", "stop", "101")
    assert result.undecided_reason == "trade_not_yet_received"


def test_a_broken_print_older_than_the_budget_blocks_nothing() -> None:
    """It could never decide anything, so it may not hold a target hostage.

    A malformed id from 45 s ago is past the age budget: even readable it would
    be ``stale_trade``. Treating it as "undecided" would block every target for
    as long as the caller keeps handing that window back.
    """
    ancient = trade("100", trade_id="not-a-number", ts=NOW - seconds(45))
    result = check_triggers(POSITION, [ancient, trade("110", trade_id="101")], now=NOW)
    assert (result.state, result.kind) == ("triggered", "target")
    assert result.undecided_reason == ""


def test_a_target_we_cannot_publish_never_hides_a_stop_that_printed_after_it() -> None:
    """Astra, T3.4b round 2, MUST-FIX 1: blocking the target lost the stop.

    Watermark 99. The batch is ``[100 unreadable, 101 at 110 (target),
    102 at 90 (stop)]``. Refusing to publish the target because print 100 is
    undecided returned ``unavailable`` immediately and never looked further —
    eleven seconds later the whole batch was stale and the stop at 90 had never
    been reported.

    Protection first: the stop really was crossed, so it is published, with the
    unread print travelling as ``undecided_reason``.
    """
    unread = trade("100", trade_id="100").model_copy(update={"received_at": NOW + seconds(20)})
    batch = [unread, trade("110", trade_id="101"), trade("90", trade_id="102")]
    result = check_triggers(POSITION, batch, now=NOW, last_accepted_trade_id=99)
    assert (result.state, result.kind, result.trade_id) == ("triggered", "stop", "102")
    assert result.undecided_reason == "trade_not_yet_received"
    assert result.accepted_trade_id == 102


def test_the_earliest_unreadable_print_decides_whether_a_target_may_be_published() -> None:
    """Astra, T3.4b round 2, MUST-FIX 2: only the first defect was remembered.

    Prints do not arrive in id order. The batch is ``[103 from the future,
    100 at 90 not yet received, 101 at 110 (target)]``: keeping only the defect
    seen *first* (103, which sits after the target) published the target and
    moved the watermark to 101, so the 90 — a stop — was dropped as a regression
    on the next cycle. The defect that matters is the **earliest** one.
    """
    ahead = trade("100", trade_id="103", ts=NOW + seconds(20))
    not_yet = trade("90", trade_id="100").model_copy(update={"received_at": NOW + seconds(2)})
    batch = [ahead, not_yet, trade("110", trade_id="101")]
    first = check_triggers(POSITION, batch, now=NOW, last_accepted_trade_id=99)
    assert (first.state, first.reason) == ("unavailable", "trade_not_yet_received")
    assert first.accepted_trade_id == 99

    later = NOW + seconds(3)
    readable = [ahead, trade("90", trade_id="100"), trade("110", trade_id="101")]
    second = check_triggers(POSITION, readable, now=later, last_accepted_trade_id=99)
    assert (second.state, second.kind, second.trade_id) == ("triggered", "stop", "100")


def test_a_known_gap_still_publishes_a_stop_we_can_actually_see() -> None:
    """Astra, T3.4b round 3: the gap swallowed a print that crossed the stop.

    ``tape_gap=True`` returned ``unavailable`` before looking at the batch at
    all, so a valid print at 90 — under a stop of 95 — was never reported; when
    the gap closed the same print was stale. A gap means "we may have missed
    prints", which is a reason to distrust *silence*, never a reason to unsee a
    trade that really printed through the stop.
    """
    result = check_triggers(
        POSITION, [trade("90", trade_id="100")], now=NOW, tape_gap=True, last_accepted_trade_id=99
    )
    assert (result.state, result.kind, result.trade_id) == ("triggered", "stop", "100")
    assert result.undecided_reason == "tape_gap"
    assert result.accepted_trade_id == 100


def test_a_known_gap_still_holds_back_a_target_and_the_silence() -> None:
    """The other half: what a gap does forbid is concluding anything else.

    A target during a gap is chronology we do not have (a missed print may have
    hit the stop first), and a quiet tape during a gap proves nothing.
    """
    target = check_triggers(POSITION, [trade("110", trade_id="101")], now=NOW, tape_gap=True)
    assert (target.state, target.reason) == ("unavailable", "tape_gap")
    quiet = check_triggers(POSITION, [trade("100", trade_id="101")], now=NOW, tape_gap=True)
    assert (quiet.state, quiet.reason) == ("unavailable", "tape_gap")


def test_a_trade_id_that_is_not_a_number_at_all_is_a_defect_not_a_crash() -> None:
    """Astra, T3.4b round 3: ``"--101"`` passed the check and crashed ``int()``.

    ``raw.lstrip("-").isdigit()`` is true for ``--101`` while ``int("--101")``
    raises, so reading the batch died with a ``ValueError`` escaping into the
    worker — and the stop at 90 in the same batch was never reported.
    """
    batch = [trade("90", trade_id="100"), trade("100", trade_id="--101")]
    result = check_triggers(POSITION, batch, now=NOW)
    assert (result.state, result.kind, result.trade_id) == ("triggered", "stop", "100")
    assert result.undecided_reason == "trade_id_not_numeric"


def test_a_malformed_id_already_past_the_budget_never_blocks_a_new_target() -> None:
    """And it expires like any other unreadable print, instead of raising."""
    ancient = trade("100", trade_id="--101", ts=NOW - seconds(45))
    result = check_triggers(POSITION, [ancient, trade("110", trade_id="102")], now=NOW)
    assert (result.state, result.kind) == ("triggered", "target")
    assert result.undecided_reason == ""


def test_a_stop_seen_behind_a_target_is_published_as_pending_not_forgotten() -> None:
    """Astra, T3.4b round 4: the second crossing could expire before the next call.

    One evaluation publishes one crossing, and the watermark stops at it so the
    next call reports the next one. That only works while the print is still
    inside the age budget. Astra's batch — id 100 at 110 (target) and id 101 at
    90 (stop), both stamped 12:00:00 and only received at 12:00:09 — publishes
    the target at 12:00:10 and, one second later, the stop is stale: the touch
    at 90 was observed and never acted on.

    So the stop seen behind the target travels **with** the target verdict. The
    caller (T3.5) can open both protections in the same transaction instead of
    depending on a second call arriving inside the budget.
    """
    target = trade("110", trade_id="100", ts=NOW).model_copy(
        update={"received_at": NOW + seconds(9)}
    )
    stop = trade("90", trade_id="101", ts=NOW + seconds(0.1)).model_copy(
        update={"received_at": NOW + seconds(9)}
    )
    first = check_triggers(
        POSITION, [target, stop], now=NOW + seconds(10), last_accepted_trade_id=99
    )
    assert (first.state, first.kind, first.trade_id) == ("triggered", "target", "100")
    assert first.pending_stop_trade_id == "101"
    assert first.pending_stop_price == Decimal("90")
    assert first.pending_stop_ts == NOW + seconds(0.1)

    # One second later the same batch can no longer decide anything — which is
    # exactly why the pending stop had to travel with the first verdict.
    second = check_triggers(
        POSITION, [target, stop], now=NOW + seconds(11), last_accepted_trade_id=100
    )
    assert (second.state, second.reason) == ("unavailable", "stale_trade")


def test_a_verdict_without_a_second_crossing_carries_no_pending_stop() -> None:
    result = check_triggers(POSITION, [trade("110", trade_id="101")], now=NOW)
    assert (result.state, result.kind) == ("triggered", "target")
    assert result.pending_stop_trade_id is None
    assert result.pending_stop_price is None
