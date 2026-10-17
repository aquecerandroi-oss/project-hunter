"""``copy_leaders_rule`` — the frozen, deterministic selection rule of the paper
copy-trade pilot (decision 2026-10-09). Pure functions over parsed board rows;
no network. Each test pins one clause of the rule text so a silent edit of a
threshold fails here before it can reach a frozen list.
"""

from __future__ import annotations

import dataclasses
import hashlib
import sys
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
for extra in (SCRIPTS_DIR, SCRIPTS_DIR / "tests"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import copy_leaders_rule as rule  # noqa: E402
from copy_leaders_rig import addr, wire_board, wire_entry  # noqa: E402


def parse(period: str, sort: str, *entries: dict[str, Any]) -> rule.ParsedBoard:
    return rule.parse_board(period, sort, wire_board(list(entries)))


def board_set(
    wallet: str, *, periods: Sequence[str] = ("weekly", "monthly"), **fields: Any
) -> list[rule.ParsedBoard]:
    """The wallet at rank 1 of ``combined`` and ``realized`` in each period."""
    out: list[rule.ParsedBoard] = []
    for period in periods:
        for sort in ("combined", "realized"):
            out.append(parse(period, sort, wire_entry(wallet, **fields)))
    return out


# --- parsing --------------------------------------------------------------


def test_parse_board_keeps_only_allowed_fields_as_decimals() -> None:
    board = parse(
        "daily", "combined", wire_entry(addr(1), realized="12.5", unrealized="-3.25", spend="40")
    )
    row = board.rows[0]
    assert row.address == addr(1)
    assert row.realized_pnl_sol == Decimal("12.5")
    assert row.unrealized_pnl_sol == Decimal("-3.25")
    assert row.buy_spend_sol == Decimal("40")
    assert row.position == 1
    assert not any(isinstance(getattr(row, f.name), float) for f in dataclasses.fields(row))
    assert "username" not in {f.name for f in dataclasses.fields(row)}
    assert board.window_start_sec == 1_789_900_000


def test_parse_board_counts_malformed_rows_and_never_invents_numbers() -> None:
    good = wire_entry(addr(1))
    no_address = wire_entry(addr(2))
    del no_address["walletAddress"]
    bad_number = wire_entry(addr(3))
    bad_number["realizedPnlSol"] = "not-a-number"
    missing_positions = wire_entry(addr(4))
    del missing_positions["positionsCount"]
    board = parse("daily", "combined", good, no_address, bad_number, missing_positions, "garbage")  # type: ignore[arg-type]
    assert [r.address for r in board.rows] == [addr(1)]
    assert board.malformed == 4


@pytest.mark.parametrize("payload", [None, [], {}, {"entries": "x"}, {"entries": []}])
def test_parse_board_refuses_a_board_without_rows(payload: object) -> None:
    with pytest.raises(rule.BoardShapeError):
        rule.parse_board("daily", "combined", payload)


# --- rule text ------------------------------------------------------------


def test_rule_text_states_every_threshold_and_is_hashed() -> None:
    text = rule.RULE_TEXT
    for needle in (rule.RULE_VERSION, "20", "10", "0,5", "101"):
        assert needle in text
    assert rule.RULE_SHA256 == hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_frozen_rule_hash_is_pinned() -> None:
    """Changing any threshold or word of the rule changes this hash. Updating the
    pin is a conscious act that requires a new ``RULE_VERSION`` and a new cohort."""
    assert rule.RULE_VERSION == "copy-leaders-rule/1"
    assert rule.RULE_SHA256 == "d0460e856adc5101d415d8aef652de9c5dda09803d2af7c5f6025f6ffa85e18c"


# --- eligibility ----------------------------------------------------------


def test_a_wallet_in_two_periods_with_realized_profit_is_selected() -> None:
    result = rule.select(board_set(addr(1)), [])
    assert [leader.address for leader in result.leaders] == [addr(1)]
    leader = result.leaders[0]
    assert leader.stratum == "regra"
    assert leader.rule_selected is True
    assert leader.rule_rank == 1
    assert leader.boards == [
        "monthly:combined",
        "monthly:realized",
        "weekly:combined",
        "weekly:realized",
    ]
    assert leader.reference_board == "monthly:combined"


def test_combined_and_realized_of_one_period_are_not_two_periods() -> None:
    result = rule.select(board_set(addr(1), periods=("daily",)), [])
    assert result.leaders == []
    assert result.funnel["rejected_one_period"] == 1


def test_non_solana_addresses_are_dropped() -> None:
    evm = "0x" + "ab" * 20
    result = rule.select(board_set(evm), [])
    assert result.leaders == []
    assert result.funnel["rejected_not_solana"] == 1


def test_realized_must_be_positive_in_every_row() -> None:
    boards = board_set(addr(1))
    boards.append(parse("daily", "combined", wire_entry(addr(1), realized="-0.5", unrealized="9")))
    result = rule.select(boards, [])
    assert result.leaders == []
    assert result.funnel["rejected_realized_not_positive"] == 1


def test_mostly_unrealized_pnl_is_marking_not_profit() -> None:
    # share = 10 / (10 + 30) = 0.25 < 0.5
    result = rule.select(board_set(addr(1), realized="10", unrealized="30"), [])
    assert result.leaders == []
    assert result.funnel["rejected_mostly_unrealized"] == 1


def test_share_exactly_one_half_passes_and_negative_unrealized_counts_as_zero() -> None:
    assert rule.select(board_set(addr(1), realized="10", unrealized="10"), []).leaders
    # unrealized -4: share is 1 (the loss is not credited), total 6 > 0
    assert rule.select(board_set(addr(2), realized="10", unrealized="-4"), []).leaders


def test_open_losses_larger_than_realized_gains_are_rejected() -> None:
    result = rule.select(board_set(addr(1), realized="10", unrealized="-100"), [])
    assert result.leaders == []
    assert result.funnel["rejected_net_not_positive"] == 1


def test_zero_cost_basis_is_rejected() -> None:
    result = rule.select(board_set(addr(1), spend="0"), [])
    assert result.leaders == []
    assert result.funnel["rejected_no_cost_basis"] == 1


def test_too_few_positions_are_rejected_but_ten_pass() -> None:
    assert rule.select(board_set(addr(1), positions=9), []).leaders == []
    assert len(rule.select(board_set(addr(2), positions=10), []).leaders) == 1


def test_high_activity_is_descriptive_only() -> None:
    result = rule.select(board_set(addr(1), positions=5000), [])
    assert len(result.leaders) == 1
    assert result.leaders[0].positions_per_day == Decimal(5000) / Decimal(30)


def test_reference_row_is_the_longest_period_and_prefers_combined() -> None:
    boards = [
        parse("daily", "combined", wire_entry(addr(1), realized="1", unrealized="0")),
        parse("weekly", "combined", wire_entry(addr(1), realized="5", unrealized="0")),
        parse("monthly", "realized", wire_entry(addr(1), realized="99", unrealized="0")),
        parse("monthly", "combined", wire_entry(addr(1), realized="77", unrealized="0")),
    ]
    leader = rule.select(boards, []).leaders[0]
    assert leader.reference_board == "monthly:combined"
    assert leader.realized_pnl_sol == Decimal("77")
    boards = boards[:3]
    assert rule.select(boards, []).leaders[0].reference_board == "monthly:realized"


# --- ranking --------------------------------------------------------------


def test_ranking_is_the_mean_position_in_the_three_realized_boards() -> None:
    a, b = addr(1), addr(2)
    boards: list[rule.ParsedBoard] = []
    for period in ("daily", "weekly", "monthly"):
        # a is 1st in two periods and absent from the third (101); b is 2nd in all
        if period == "monthly":
            boards.append(parse(period, "realized", wire_entry(b, rank=1)))
        else:
            boards.append(parse(period, "realized", wire_entry(a), wire_entry(b)))
        boards.append(parse(period, "combined", wire_entry(a), wire_entry(b)))
    result = rule.select(boards, [])
    scores = {e.address: e.score for e in result.evaluated}
    assert scores[a] == Decimal(1 + 1 + 101) / 3
    assert scores[b] == Decimal(2 + 2 + 1) / 3
    assert [leader.address for leader in result.leaders] == [b, a]
    assert [leader.rule_rank for leader in result.leaders] == [1, 2]


def test_position_is_the_place_in_the_returned_list_not_the_rank_field() -> None:
    first = wire_entry(addr(1), rank=77)
    second = wire_entry(addr(2), rank=3)
    board = parse("daily", "realized", first, second)
    assert [(r.address, r.position) for r in board.rows] == [(addr(1), 1), (addr(2), 2)]


def test_ties_break_by_address_ascending() -> None:
    # identical positions are impossible inside one board, so mirror the order across
    # periods: wallet 9 first in weekly, wallet 3 first in monthly -> the same mean
    boards = [
        parse("weekly", "realized", wire_entry(addr(9)), wire_entry(addr(3))),
        parse("weekly", "combined", wire_entry(addr(9)), wire_entry(addr(3))),
        parse("monthly", "realized", wire_entry(addr(3)), wire_entry(addr(9))),
        parse("monthly", "combined", wire_entry(addr(3)), wire_entry(addr(9))),
    ]
    result = rule.select(boards, [])
    assert [leader.address for leader in result.leaders] == sorted([addr(3), addr(9)])


def test_only_the_top_twenty_are_kept_and_fewer_is_fine() -> None:
    wallets = [addr(i) for i in range(25)]
    boards: list[rule.ParsedBoard] = []
    for period in ("weekly", "monthly"):
        for sort in ("combined", "realized"):
            boards.append(parse(period, sort, *[wire_entry(w) for w in wallets]))
    result = rule.select(boards, [])
    assert len(result.leaders) == 20
    assert [leader.address for leader in result.leaders] == wallets[:20]
    assert result.funnel["eligible"] == 25
    assert len(rule.select(board_set(addr(1)), []).leaders) == 1


# --- includes -------------------------------------------------------------


def test_include_enters_unfiltered_with_its_own_stratum() -> None:
    included = addr(50)
    result = rule.select(board_set(addr(1)), [included])
    by_address = {leader.address: leader for leader in result.leaders}
    assert by_address[included].stratum == "escolha_everton"
    assert by_address[included].everton_pick is True
    assert by_address[included].rule_selected is False
    assert by_address[included].boards == []
    assert by_address[included].realized_pnl_sol is None


def test_include_that_is_also_selected_appears_once_and_opens_no_slot() -> None:
    wallets = [addr(i) for i in range(25)]
    boards: list[rule.ParsedBoard] = []
    for period in ("weekly", "monthly"):
        for sort in ("combined", "realized"):
            boards.append(parse(period, sort, *[wire_entry(w) for w in wallets]))
    result = rule.select(boards, [wallets[0]])
    assert len(result.leaders) == 20
    first = next(leader for leader in result.leaders if leader.address == wallets[0])
    assert first.stratum == "regra"  # the rule would have chosen it anyway
    assert first.everton_pick is True
    assert first.rule_selected is True
    assert sum(leader.rule_selected for leader in result.leaders) == 20
    assert sum(leader.everton_pick for leader in result.leaders) == 1


def test_include_on_a_board_but_failing_the_filters_keeps_its_numbers() -> None:
    boards = board_set(addr(1), realized="1", unrealized="50")  # mostly unrealized
    result = rule.select(boards, [addr(1)])
    leader = result.leaders[0]
    assert leader.stratum == "escolha_everton"
    assert leader.rule_selected is False
    assert leader.realized_pnl_sol == Decimal("1")


@pytest.mark.parametrize("bad", ["", "0xabc", "short", "I" * 44, "A" * 50])
def test_include_must_be_a_solana_address(bad: str) -> None:
    with pytest.raises(rule.RuleError):
        rule.validate_includes([bad])


def test_includes_are_deduplicated_and_capped() -> None:
    assert rule.validate_includes([addr(1), addr(1)]) == [addr(1)]
    with pytest.raises(rule.RuleError):
        rule.validate_includes([addr(i) for i in range(rule.MAX_INCLUDES + 1)])


# --- explainability -------------------------------------------------------


def test_every_evaluated_wallet_records_its_first_rejection() -> None:
    boards = board_set(addr(1)) + board_set(addr(2), positions=3)
    result = rule.select(boards, [])
    reasons = {e.address: e.reject_reason for e in result.evaluated}
    assert reasons[addr(1)] is None
    assert reasons[addr(2)] == "too_few_positions"
    assert result.universe_wallets == 2
    assert result.funnel["wallets_seen"] == 2


# --- review fixes: duplicates, trailing newline, boundaries, include order ---------------


def test_a_duplicate_address_inside_a_view_is_a_malformed_row() -> None:
    """Otherwise the reference row took the first occurrence and the score the last."""
    first = wire_entry(addr(1), rank=1)
    other = wire_entry(addr(2), rank=2)
    again = wire_entry(addr(1), rank=3)
    board = parse("weekly", "realized", first, other, again)
    assert [r.address for r in board.rows] == [addr(1), addr(2)]
    assert board.malformed == 1


def test_is_solana_address_rejects_a_trailing_newline() -> None:
    assert rule.is_solana_address(addr(1))
    assert not rule.is_solana_address(addr(1) + "\n")


def test_a_newline_variant_of_an_include_is_rejected_and_never_makes_a_leader() -> None:
    with pytest.raises(rule.RuleError):
        rule.validate_includes([addr(1), addr(1) + "\n"])


def test_net_exactly_zero_is_rejected() -> None:
    result = rule.select(board_set(addr(1), realized="10", unrealized="-10"), [])
    assert result.leaders == []
    assert result.funnel["rejected_net_not_positive"] == 1


def test_realized_exactly_zero_is_rejected_without_dividing_by_zero() -> None:
    boards = board_set(addr(1)) + [parse("daily", "combined", wire_entry(addr(1), realized="0"))]
    result = rule.select(boards, [])
    assert result.leaders == []
    assert result.funnel["rejected_realized_not_positive"] == 1
    # an included wallet whose reference row has realized 0 keeps a null share, no error
    zero = board_set(addr(2), realized="0", unrealized="5")
    leader = rule.select(zero, [addr(2)]).leaders[0]
    assert leader.realized_share is None


def test_includes_are_sorted_canonically() -> None:
    assert rule.validate_includes([addr(9), addr(3), addr(5)]) == sorted(
        [addr(3), addr(5), addr(9)]
    )
