"""``infra/scripts/meme_diary_render.py`` and the pure helpers of ``meme_diary.py``
— no database: the note is a function of the rows.

Run: ``uv run pytest infra/scripts/tests/test_meme_diary.py -q``
"""

from __future__ import annotations

import sys
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from meme_diary import day_bounds, max_drawdown  # noqa: E402
from meme_diary_render import (  # noqa: E402
    BetLine,
    DiaryInputs,
    RuleSetDay,
    render_diary,
    required_daily_return,
)

pytestmark = pytest.mark.unit

DAY = date(2026, 9, 12)


def _rule_set(**overrides: object) -> RuleSetDay:
    base: dict[str, object] = {
        "name": "meme_paper_v0",
        "version": "1",
        "kind": "research_only",
        "exp_ref": "EXP-M1",
        "wallet_max_sol": Decimal("2.0"),
        "balance_start_sol": Decimal("2.0"),
        "balance_end_sol": Decimal("2.03"),
        "realized_day_sol": Decimal("0.03"),
        "realized_total_sol": Decimal("0.03"),
        "r_day": Decimal("0.6"),
        "r_total": Decimal("0.6"),
        "drawdown_day_sol": Decimal("0.02"),
        "drawdown_total_sol": Decimal("0.02"),
        "bets_day": 2,
        "closed_day": 2,
        "wins_day": 1,
        "rugs_day": 0,
    }
    base.update(overrides)
    return RuleSetDay(**base)  # type: ignore[arg-type]


def _inputs(**overrides: object) -> DiaryInputs:
    base: dict[str, object] = {
        "day": DAY,
        "generated_at": datetime(2026, 9, 12, 21, 0, tzinfo=UTC),
        "rule_sets": [_rule_set()],
        "bets": [
            BetLine(
                mint="5bmYxJJnvAKn23VMxvjiTfeBckEmMok7C3SxztaA9c38",
                rule_set="meme_paper_v0/1",
                exp_ref="EXP-M1",
                entry_at=datetime(2026, 9, 12, 12, 0, tzinfo=UTC),
                exit_at=datetime(2026, 9, 12, 12, 5, tzinfo=UTC),
                exit_reason="target",
                r_multiple=Decimal("1.1"),
                pnl_sol=Decimal("0.055"),
                pnl_usd=Decimal("5.58"),
                sol_usd_source="pumpfun_rest:/sol-price",
                sol_usd_observed_at="2026-09-12T12:05:00+00:00",
                initial_risk_sol=Decimal("0.05"),
            )
        ],
        "unfilled_by_refusal": {"no_later_snapshot": 1},
        "expired_proposals": 0,
        "gaps_by_stream_reason": {},
        "sol_usd": Decimal("101.4445"),
        "sol_usd_source": "pumpfun_rest:/sol-price",
        "sol_usd_observed_at": "2026-09-12T12:05:00+00:00",
        "clock_start": DAY,
        "lab_last_tick_at": datetime(2026, 9, 12, 20, 59, tzinfo=UTC),
    }
    base.update(overrides)
    return DiaryInputs(**base)  # type: ignore[arg-type]


def test_the_note_has_the_frontmatter_and_the_six_sections_in_order() -> None:
    note = render_diary(_inputs())
    assert note.startswith(
        "---\ntags: [operacoes, diario, meme, m4]\nstatus: registro\nowner: sexta-feira\nupdated: 2026-09-12\n---\n"
    )
    positions = [note.index(f"## {n}.") for n in range(1, 7)]
    assert positions == sorted(positions)
    assert "PAPEL — nenhuma transação real" in note
    assert "09:00:00 | 09:05:00 | target | 1.1 | 0.055 | 5.58 | pumpfun_rest:/sol-price @" in note
    assert "Retorno diário exigido:" in note and "%/dia com 30 dias restantes" in note
    assert "Retorno diário medido: 1.5 %/dia" in note  # 0.03 / (2.03 − 0.03)
    assert "`no_later_snapshot`: 1" in note
    assert "último tick às 2026-09-12 17:59:00 BRT" in note
    assert note.rstrip().endswith("(a preencher pelo arquivista — Sexta-feira)")


def test_a_number_nobody_observed_is_a_dash_with_a_reason_never_zero() -> None:
    note = render_diary(
        _inputs(
            bets=[],
            rule_sets=[_rule_set(r_day=None, drawdown_day_sol=None, closed_day=0, bets_day=0)],
            sol_usd=None,
            sol_usd_source=None,
            sol_usd_observed_at=None,
            lab_last_tick_at=None,
        )
    )
    assert "Nenhuma aposta aberta neste dia" in note
    assert "— (sem fechada)" in note
    assert "— (sem cotação SOL/USD observada)" in note
    assert "— (nenhuma aposta fechada no dia)" in note
    assert "laço parado ou nunca rodou" in note
    assert "| 0 |" not in note.split("## 4.")[1].split("## 5.")[0]


def test_the_goal_formula_is_the_decision_notes() -> None:
    rate = required_daily_return(Decimal(20_000), 30)
    assert rate is not None and abs(rate - Decimal("0.21563")) < Decimal("0.0001")
    assert required_daily_return(Decimal(0), 30) is None
    assert required_daily_return(Decimal(20_000), 0) is None


def test_the_day_is_brasilia_and_the_drawdown_is_the_deepest_fall() -> None:
    start, end = day_bounds(DAY)
    assert start.astimezone(UTC) == datetime(2026, 9, 12, 3, 0, tzinfo=UTC)
    assert (end - start).days == 1
    assert max_drawdown([]) is None
    assert max_drawdown(
        [Decimal("0.1"), Decimal("-0.05"), Decimal("-0.1"), Decimal("0.3")]
    ) == Decimal("0.15")
    assert max_drawdown([Decimal("-0.02")]) == Decimal("0.02"), "a first loss counts from zero"
