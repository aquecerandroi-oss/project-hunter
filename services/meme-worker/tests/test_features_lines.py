"""T4.10 — the lines and the hype inside the fold: ``build_row`` writes the
``0026`` columns from the minute's own inputs, and non-anticipation holds for
the two new sources (a photo or a board row received after the close changes
nothing in the row).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_indicators.meme.lines import LinePoint
from hunter_meme_worker.features import FEATURES_VERSION, CurveObservation, MinuteInputs, build_row
from hunter_meme_worker.features_lines import BoardStanding, board_standing
from hunter_meme_worker.features_tape import HoldersObservation, TapeMinute
from hunter_meme_worker.repo_boards import BoardMinuteRow

pytestmark = pytest.mark.unit

END = datetime(2026, 9, 12, 12, 15, tzinfo=UTC)
SERIES: dict[int, str] = {
    -15: "41",
    -14: "40",
    -13: "38",
    -12: "36",
    -11: "39",
    -10: "42",
    -9: "45",
    -8: "43",
    -7: "41",
    -6: "44",
    -5: "47",
    -4: "49",
    -3: "50",
    -2: "52",
    -1: "53",
    0: "56",
}


def _points(late: LinePoint | None = None) -> list[LinePoint]:
    points = [
        LinePoint(END + timedelta(minutes=m), END + timedelta(minutes=m), Decimal(v))
        for m, v in SERIES.items()
    ]
    return [*points, late] if late is not None else points


def _snapshot(mcap: str = "56") -> CurveObservation:
    return CurveObservation(
        observed_at=END,
        source="pumpfun_rest",
        real_token_reserves=Decimal("666100000"),
        mcap_sol=Decimal(mcap),
        complete=False,
    )


def _tape(buys: int = 15, buyers: int = 10) -> TapeMinute:
    return TapeMinute(
        buys=buys,
        sells=2,
        unique_buyers=buyers,
        net_sol_flow=Decimal("1.5"),
        volume_sol=Decimal("3"),
        creator_sold=False,
        creator_net_seller=False,
    )


def _holders(snipers: int | None = 1) -> HoldersObservation:
    return HoldersObservation(
        observed_at=END - timedelta(seconds=20),
        received_at=END - timedelta(seconds=19),
        source="trenches_ws",
        holders=40,
        top10_share=Decimal("0.3"),
        dev_share=Decimal("0.05"),
        snipers=snipers,
    )


def _board_row(
    board: str = "new",
    position: int = 3,
    *,
    has_social: bool | None = True,
    received_at: datetime | None = None,
    mint: str = "MINT",
    minute_end: datetime = END,
) -> BoardMinuteRow:
    return BoardMinuteRow(
        observed_at=END - timedelta(seconds=30),
        board=board,
        mint=mint,
        minute_end=minute_end,
        received_at=received_at or END - timedelta(seconds=29),
        mint_updated_at=None,
        version=7,
        position=position,
        patches=0,
        first_seen_in_board_at=END - timedelta(minutes=2),
        last_seen_in_board_at=END - timedelta(seconds=30),
        left_board_at=None,
        exposure_censored=False,
        source="trenches_ws",
        has_social=has_social,
    )


def _inputs(**kw: object) -> MinuteInputs:
    defaults: dict[str, object] = {
        "mint": "MINT",
        "end_time": END,
        "created_at": END - timedelta(minutes=7),
        "initial_real_token_reserves": Decimal("793100000"),
        "snapshot": _snapshot(),
        "holders": _holders(),
        "tape": _tape(),
        "line_points": _points(),
        "board": BoardStanding(best_position=3, has_social=True),
    }
    defaults.update(kw)
    return MinuteInputs(**defaults)  # type: ignore[arg-type]


def test_the_version_is_v3_and_the_row_carries_the_line_and_the_hype() -> None:
    assert FEATURES_VERSION == "meme_features_v3"
    row = build_row(_inputs())
    assert row.features_version == "meme_features_v3"
    assert row.support_line_sol == Decimal("48.0000000000")
    assert row.support_line_slope == Decimal("1.000000")
    assert row.higher_lows is True and row.breakout_15m is True
    assert row.distance_to_support_pct == Decimal("0.166667")
    assert row.high_15m_sol == Decimal("56.0000000000")
    assert row.low_15m_sol == Decimal("36.0000000000")
    assert row.line_points == 15 and row.line_reason is None
    assert row.hype_score == Decimal("0.700000") and row.hype_reason is None


def test_a_photo_received_after_the_close_does_not_change_the_row() -> None:
    late = LinePoint(
        END - timedelta(minutes=3, seconds=30), END + timedelta(seconds=1), Decimal(20)
    )
    assert build_row(_inputs(line_points=_points(late))) == build_row(_inputs())
    on_time = replace(late, received_at=END)
    assert build_row(_inputs(line_points=_points(on_time))).low_15m_sol == Decimal("20.0000000000")


def test_a_board_row_received_after_the_close_is_not_the_minutes_standing() -> None:
    rows = [_board_row(received_at=END + timedelta(seconds=1))]
    assert board_standing(rows, mint="MINT", end_time=END) is None
    rows = [_board_row(received_at=END)]
    assert board_standing(rows, mint="MINT", end_time=END) == BoardStanding(3, True)


def test_the_standing_is_the_best_position_over_movers_and_new_only() -> None:
    rows = [
        _board_row("new", 25),
        _board_row("movers", 4, has_social=None),
        _board_row("graduating", 0),  # not one of the hype boards
        _board_row("new", 1, mint="OTHER"),
        _board_row("new", 0, minute_end=END - timedelta(minutes=1)),  # another minute
    ]
    assert board_standing(rows, mint="MINT", end_time=END) == BoardStanding(4, True)
    graduating_only = [_board_row("graduating", 0, has_social=False)]
    assert board_standing(graduating_only, mint="MINT", end_time=END) == BoardStanding(None, False)
    assert board_standing([], mint="MINT", end_time=END) is None


def test_the_hype_reasons_follow_the_two_sources() -> None:
    both_missing = build_row(_inputs(tape=None, board=None))
    assert both_missing.hype_score is None and both_missing.hype_reason == "no_tape_no_board"
    tape_only = build_row(_inputs(board=None))
    assert tape_only.hype_reason == "partial" and tape_only.hype_score == Decimal("0.400000")
    board_only = build_row(_inputs(tape=None))
    assert board_only.hype_reason == "partial" and board_only.hype_score == Decimal("0.400000")


def test_snipers_feed_the_score_from_the_same_holders_reading() -> None:
    assert build_row(_inputs(holders=_holders(snipers=None))).hype_score == Decimal("0.600000")
    assert build_row(_inputs(holders=None)).hype_score == Decimal("0.600000")
    assert build_row(_inputs(holders=_holders(snipers=7))).hype_score == Decimal("0.600000")


def test_the_line_reasons_reach_the_row() -> None:
    few = build_row(_inputs(line_points=_points()[-4:]))
    assert few.line_reason == "too_few_points" and few.line_points == 4
    assert few.support_line_sol is None and few.high_15m_sol is None
    none = build_row(_inputs(snapshot=None))
    assert none.line_reason == "no_snapshot" and none.line_points == 15
    assert none.mcap_sol is None and none.hype_score is not None, "hype does not need a photo"
    monotone = [
        LinePoint(END + timedelta(minutes=m), END + timedelta(minutes=m), Decimal(40 + m + 15))
        for m in range(-15, 1)
    ]
    flat = build_row(_inputs(line_points=monotone, snapshot=_snapshot("55")))
    assert flat.line_reason == "flat" and flat.support_line_sol is None
    assert flat.high_15m_sol is not None and flat.mcap_slope_15m is not None
