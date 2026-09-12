"""``infra/scripts/meme_close_lessons.py`` — every lesson of the daily close
over a synthetic day of bets whose answer is known in advance.

No database. Run: ``uv run pytest infra/scripts/tests/test_meme_close_lessons.py -q``
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from meme_close_lessons import (  # noqa: E402
    ClosedBet,
    day_lessons,
    hour_block,
    leave_top_out,
    lesson_exits,
    lesson_flag,
    lesson_progress,
    lesson_tercile,
)

pytestmark = pytest.mark.unit

NOON_UTC = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)  # 09:00 BRT


def _bet(**overrides: Any) -> ClosedBet:
    base: dict[str, Any] = {
        "mint": "MINT",
        "rule_set": "meme_paper_v0/1",
        "exp_ref": "EXP-M1",
        "kind": "research_only",
        "entry_at": NOON_UTC,
        "exit_at": NOON_UTC + timedelta(minutes=5),
        "exit_reason": "time_stop",
        "r_multiple": Decimal("-0.2"),
        "pnl_sol": Decimal("-0.01"),
        "initial_risk_sol": Decimal("0.05"),
        "age_at_entry_s": 150,
        "progress_pct": Decimal("7"),
        "snipers": 1,
        "top10_share": Decimal("0.2"),
        "dev_share": Decimal("0.05"),
        "same_slot": False,
        "creator_prior_1h": 0,
        "symbol_dup_24h": 0,
    }
    base.update(overrides)
    return ClosedBet(**base)


def _day() -> list[ClosedBet]:
    """40 closed bets over six Brasília hours: 12 same-slot clones of a serial
    creator that all died at −1 R, and 28 ordinary ones alternating +0.3/−0.2."""
    bets: list[ClosedBet] = []
    for i in range(12):
        bets.append(
            _bet(
                mint=f"SLOT{i}",
                entry_at=NOON_UTC + timedelta(hours=i % 6, minutes=i),
                exit_reason="dead" if i % 2 else "rug_no_snapshot",
                r_multiple=Decimal("-1"),
                pnl_sol=Decimal("-0.05"),
                age_at_entry_s=45,
                progress_pct=Decimal("1"),
                snipers=6,
                same_slot=True,
                creator_prior_1h=3,
                symbol_dup_24h=4,
            )
        )
    for i in range(28):
        bets.append(
            _bet(
                mint=f"OK{i}",
                entry_at=NOON_UTC + timedelta(hours=i % 6, minutes=30 + i % 20),
                exit_reason="target" if i % 2 == 0 else "trailing",
                r_multiple=Decimal("0.3") if i % 2 == 0 else Decimal("-0.2"),
                pnl_sol=Decimal("0.015") if i % 2 == 0 else Decimal("-0.01"),
                age_at_entry_s=90 + 40 * (i % 5),
                progress_pct=Decimal(5 + i % 30),
                snipers=i % 3,
                top10_share=None if i % 7 == 0 else Decimal("0.1") + Decimal(i % 4) / 10,
            )
        )
    return bets


def test_the_hour_block_is_the_brasilia_hour() -> None:
    assert hour_block(NOON_UTC) == "09"
    assert hour_block(datetime(2026, 9, 13, 2, 59, tzinfo=UTC)) == "23"


def test_exits_by_reason_name_the_costliest_exit_and_what_it_would_change() -> None:
    lesson = lesson_exits(_day())
    assert lesson.n == 40 and lesson.sufficient
    labels = {(cell.group, cell.label): cell.interval for cell in lesson.cells}
    dead = labels[("meme_paper_v0/1", "dead")]
    assert dead.n == 6 and dead.total == Decimal("-6")
    assert lesson.note.startswith("Qual saída custou mais R")
    assert "`dead`" in lesson.note or "`rug_no_snapshot`" in lesson.note
    assert lesson.contrast is not None and lesson.contrast.n_a == 6
    # 6 exits of one reason is below the 10 a cell needs: measured, not promoted.
    assert lesson.measured is None
    assert lesson.change.startswith("nada muda")


def test_a_flag_lesson_passes_the_ruler_and_proposes_a_named_refusal() -> None:
    lesson = lesson_flag(
        _day(),
        key="mesmo_slot",
        title="Mesmo slot × R",
        feature="same_slot",
        flag=lambda b: b.same_slot,
        yes="mesmo slot (pool ≤ 1 s após a criação)",
        no="demais",
    )
    assert lesson.n == 40
    cells = {cell.label: cell.interval for cell in lesson.cells}
    assert cells["mesmo slot (pool ≤ 1 s após a criação)"].n == 12
    assert cells["demais"].n == 28 and cells["demais"].mean == Decimal("0.05")
    assert lesson.contrast is not None and lesson.contrast.delta == Decimal("-1.05")
    assert lesson.measured is not None and "Δ -1.05 R" in lesson.measured
    assert "IC 95 % por blocos de hora" in lesson.measured
    assert lesson.proposal is not None and "`same_slot`" in lesson.proposal
    assert "previsão `descartar`" in lesson.proposal
    assert lesson.change.startswith("amanhã o lote propõe um braço irmão que exclui")
    assert lesson.change.count(".") <= 4 and "\n" not in lesson.change


def test_bands_and_terciles_put_the_unknown_apart_and_pick_the_most_deviant_cell() -> None:
    progress = lesson_progress(_day())
    labels = {cell.label: cell.interval for cell in progress.cells}
    assert labels["< 5 %"].n == 12 and labels["< 5 %"].mean == Decimal("-1")
    assert "5–10 %" in labels and "10–30 %" in labels
    assert progress.contrast_label == "< 5 %"
    assert progress.measured is not None and "curve_progress_pct" in (progress.proposal or "")
    top10 = lesson_tercile(_day(), key="top10", title="Top-10 × R", feature="top10_share")
    labels = {cell.label for cell in top10.cells}
    assert "desconhecido" in labels and any(label.startswith("baixo") for label in labels)
    assert all("\n" not in cell.label for cell in top10.cells)


def test_below_thirty_bets_every_lesson_says_nothing_changes() -> None:
    few = _day()[:21]
    lessons = day_lessons(few)
    assert len(lessons) == 9
    for lesson in lessons:
        assert lesson.n == 21 and not lesson.sufficient
        assert lesson.change == "nada muda (n insuficiente: 21 < 30)"
        assert lesson.measured is None and lesson.proposal is None
    empty = day_lessons([])
    assert all(lesson.n == 0 and lesson.change.startswith("nada muda") for lesson in empty)


def test_leave_top_out_removes_the_best_bet_per_rule_set() -> None:
    bets = _day() + [_bet(mint="OTHER", rule_set="hype_probe_v0/1", r_multiple=Decimal("2"))]
    rows = {row.rule_set: row for row in leave_top_out(bets)}
    main = rows["meme_paper_v0/1"]
    assert main.n == 40 and main.total == Decimal("-10.6")
    assert main.best_mint == "OK0" and main.best_r == Decimal("0.3")
    assert main.without_best == Decimal("-10.9")
    assert rows["hype_probe_v0/1"].without_best == Decimal(0)
