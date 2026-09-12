"""The ``0023`` columns of the minute — holders from the boards, the tape from
``swap-api`` — and the non-anticipation rule that decides what a minute may
know: only what had **reached us** by ``end_time``.

The look-ahead test is the one that matters: a reading or a trade stamped
inside the minute but received one second after it closes changes nothing.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from hunter_exchanges.pumpfun import trenches_state
from hunter_exchanges.pumpfun.swap_api import parse_trades_page
from hunter_meme_worker.features import (
    NO_HOLDERS_READER,
    NO_TRADE_FEED,
    REASON_VOCABULARY,
    MinuteInputs,
    build_row,
)
from hunter_meme_worker.features_tape import (
    NO_SELLS,
    HoldersObservation,
    TapeTrade,
    holders_for,
    tape_for,
)

pytestmark = pytest.mark.unit

FIXTURES = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "exchange-adapters"
    / "tests"
    / "fixtures"
    / "pumpfun"
)
END = datetime(2026, 9, 12, 7, 35, tzinfo=UTC)
CREATOR = "dev12bVcv5ZLjo7eYgZcSmZ7KBjEVfnfvorwqdZ14fo"
"""A trader of the real ``swap_api_trades_5ejA_raw.json`` capture (a buy at
07:13:03 Z), used here as the creator so the creator columns read a real row."""


def _reading(
    received: datetime, holders: int = 94, source: str = "trenches_ws"
) -> HoldersObservation:
    return HoldersObservation(
        observed_at=received - timedelta(milliseconds=200),
        received_at=received,
        source=source,
        holders=holders,
        top10_share=Decimal("0.773048"),
        dev_share=Decimal("0.00282"),
        snipers=33,
    )


def _real_tape() -> list[TapeTrade]:
    """The 30 curve trades of the T4.8 capture, received one second after block time."""
    raw = json.loads((FIXTURES / "swap_api_trades_5ejA_raw.json").read_text(), parse_float=Decimal)
    page = parse_trades_page("MINT", raw, received_at=END)
    return [
        TapeTrade(
            block_time=t.observed_at,
            received_at=t.observed_at + timedelta(seconds=1),
            trader=t.trader,
            side=t.side,
            sol_lamports=t.sol_lamports or 0,
        )
        for t in page.trades
    ]


def test_holders_for_takes_the_newest_reading_received_by_the_close() -> None:
    early = _reading(END - timedelta(seconds=40), holders=90)
    late = _reading(END - timedelta(seconds=2), holders=94)
    after = _reading(END + timedelta(seconds=1), holders=99)
    assert holders_for([after, early, late], end_time=END) is late
    assert holders_for([after], end_time=END) is None
    assert holders_for([], end_time=END) is None


def test_a_real_board_entry_becomes_the_minutes_holders_with_provenance() -> None:
    capture = json.loads((FIXTURES / "trenches_graduated.json").read_text(encoding="utf-8"))
    snapshot = json.loads(capture["frames"][0]["raw"], parse_float=Decimal)
    entry = trenches_state.parse_entry(
        snapshot["entries"][0],
        board="graduated",
        position=0,
        version=1,
        observed_at=END - timedelta(seconds=30),
        received_at=END - timedelta(seconds=29),
    )
    reading = HoldersObservation(
        observed_at=entry.observed_at,
        received_at=entry.received_at,
        source=entry.source,
        holders=entry.holders,
        top10_share=entry.top10_share,
        dev_share=entry.dev_share,
        snipers=entry.snipers,
    )
    row = build_row(_inputs(holders=reading))
    assert row.holders == 94 and row.holders_reason is None
    assert row.holders_observed_at == entry.observed_at and row.holders_source == "trenches_ws"
    assert row.top10_share == Decimal("0.773048") and row.top10_share_reason is None
    assert row.dev_share == Decimal("0.002820") and row.dev_share_reason is None
    assert row.snipers == 33 and row.snipers_reason is None


def _inputs(**kw: object) -> MinuteInputs:
    defaults: dict[str, object] = {
        "mint": "MINT",
        "end_time": END,
        "created_at": END - timedelta(minutes=30),
        "initial_real_token_reserves": None,
        "snapshot": None,
    }
    defaults.update(kw)
    return MinuteInputs(**defaults)  # type: ignore[arg-type]


def test_the_tape_of_the_minute_counts_only_what_had_arrived() -> None:
    tape = _real_tape()
    end = datetime(2026, 9, 12, 7, 35, tzinfo=UTC)  # the newest capture trade is 07:34:28
    minute = tape_for(tape, end_time=end, creator=CREATOR, covered_since=end - timedelta(hours=2))
    assert minute is not None
    assert (minute.buys, minute.sells) == (0, 1), "one sell at 07:34:28 inside (07:34, 07:35]"
    assert minute.unique_buyers == 0
    assert minute.net_sol_flow == Decimal("-0.7247169930")
    assert minute.volume_sol == Decimal("0.7247169930")
    assert minute.creator_sold is False and minute.creator_net_seller is False
    # Look-ahead: the same trade received two seconds *after* the close is not
    # in this minute — and it is in no minute, which the docstring declares.
    late = [
        TapeTrade(t.block_time, end + timedelta(seconds=2), t.trader, t.side, t.sol_lamports)
        for t in tape
    ]
    lookahead = tape_for(
        late, end_time=end, creator=CREATOR, covered_since=end - timedelta(hours=2)
    )
    assert lookahead is not None and (lookahead.buys, lookahead.sells) == (0, 0)
    assert lookahead.creator_sold is False


def test_an_uncovered_tape_is_none_not_zero_and_a_creator_unknown_is_none() -> None:
    tape = _real_tape()
    assert tape_for(tape, end_time=END, creator=CREATOR, covered_since=None) is None
    assert (
        tape_for(tape, end_time=END, creator=CREATOR, covered_since=END + timedelta(seconds=1))
        is None
    )
    minute = tape_for(tape, end_time=END, creator=None, covered_since=END - timedelta(hours=2))
    assert minute is not None and minute.creator_sold is None and minute.creator_net_seller is None


def test_the_creator_columns_read_the_whole_covered_tape_not_the_minute() -> None:
    tape = _real_tape()
    sells = [t for t in tape if t.side == "sell"]
    creator = sells[0].trader
    end = sells[0].block_time + timedelta(minutes=30)
    minute = tape_for(tape, end_time=end, creator=creator, covered_since=end - timedelta(days=2))
    assert minute is not None and minute.creator_sold is True
    bought = sum(t.sol_lamports for t in tape if t.trader == creator and t.side == "buy")
    sold = sum(t.sol_lamports for t in tape if t.trader == creator and t.side == "sell")
    assert minute.creator_net_seller is (sold > bought)


def test_build_row_fills_the_tape_columns_and_names_no_sells() -> None:
    tape = _real_tape()
    end = datetime(2026, 9, 12, 7, 14, tzinfo=UTC)  # two buys at 07:13:03 and 07:13:43
    minute = tape_for(tape, end_time=end, creator=CREATOR, covered_since=end - timedelta(hours=2))
    row = build_row(_inputs(end_time=end, tape=minute))
    assert (row.buys_1m, row.sells_1m) == (2, 0) and row.tape_reason is None
    assert row.unique_buyers == 1, "the creator's own buy is not a buyer"
    assert row.buy_sell_ratio is None and row.buy_sell_ratio_reason == NO_SELLS
    # 07:13:03 (the creator's 0.199703703 SOL) + 07:13:43 (0.500000001 SOL);
    # the 0.977777777 SOL buy at 07:14:09 is the next minute's.
    assert row.net_sol_flow_1m == Decimal("0.6997037030")
    assert row.curve_volume_1m_sol == Decimal("0.6997037030")
    assert row.creator_sold is False and row.creator_sold_reason is None
    assert row.creator_net_seller is False and row.creator_net_seller_reason is None
    assert row.holders is None and row.holders_reason == NO_HOLDERS_READER


def test_without_a_tape_every_tape_column_is_null_with_the_tapes_reason() -> None:
    row = build_row(_inputs(tape=None, tape_absence_reason="rate_limited"))
    assert row.buys_1m is None and row.tape_reason == "rate_limited"
    assert row.creator_net_seller is None and row.creator_net_seller_reason == "rate_limited"
    assert row.unique_buyers_reason == "rate_limited"
    default = build_row(_inputs())
    assert default.tape_reason == NO_TRADE_FEED and default.creator_sold_reason == NO_TRADE_FEED


def test_a_reading_without_holders_but_with_shares_keeps_each_columns_own_reason() -> None:
    reading = HoldersObservation(
        observed_at=END,
        received_at=END,
        source="indexer_rest:/in-memory-coin",
        holders=None,
        top10_share=Decimal("0.5"),
        dev_share=None,
        snipers=3,
    )
    row = build_row(_inputs(holders=reading))
    assert row.holders is None and row.holders_reason == NO_HOLDERS_READER
    assert row.holders_observed_at is None and row.holders_source is None
    assert row.top10_share == Decimal("0.500000") and row.snipers == 3
    assert row.dev_share is None and row.dev_share_reason == NO_HOLDERS_READER


def test_every_reason_the_new_columns_can_carry_is_in_the_vocabulary() -> None:
    rows = [
        build_row(_inputs()),
        build_row(_inputs(tape_absence_reason="unsupported_quote")),
        build_row(_inputs(holders=_reading(END))),
    ]
    reasons = {
        r
        for row in rows
        for r in (
            row.holders_reason,
            row.dev_share_reason,
            row.snipers_reason,
            row.tape_reason,
            row.creator_net_seller_reason,
            row.buy_sell_ratio_reason,
        )
        if r is not None
    }
    assert reasons <= REASON_VOCABULARY and NO_SELLS in REASON_VOCABULARY
