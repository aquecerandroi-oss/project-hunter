"""``meme_daily_ficha_render.py`` — the Markdown, pure.

No database. Run: ``uv run pytest infra/scripts/tests/test_meme_daily_ficha_render.py -q``
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

from meme_daily_ficha_render import Ficha, render_day, render_week  # noqa: E402
from meme_daily_ficha_types import (  # noqa: E402
    DayFicha,
    DecisionFeatures,
    PaperArm,
    RealPosition,
    SpotPosition,
)

pytestmark = pytest.mark.unit

_NO_FEATURES = DecisionFeatures(
    curve_progress_pct=None,
    snipers=None,
    dev_share_pct=None,
    buys_1m=None,
    sells_1m=None,
    unique_buyers=None,
    net_flow_sol=None,
    creation_bundle_sol=None,
    creation_bundle_wallets=None,
)


def _position(**overrides: object) -> RealPosition:
    fixed: dict[str, object] = {
        "mint": "MintAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA1",
        "symbol": "RIGBY",
        "operator": "operator/5",
        "entry_at": datetime(2026, 9, 24, 13, 58, 35, tzinfo=UTC),
        "exit_at": datetime(2026, 9, 24, 14, 1, 45, tzinfo=UTC),
        "cost_sol": Decimal("0.07"),
        "sol_out": Decimal("0.0812"),
        "pnl_sol": Decimal("0.0112"),
        "high_water_sol": Decimal("0.0812"),
        "exit_reason": "target",
        "sell_attempts": 1,
        "fees_sol": Decimal("0.0016"),
        "rent_refund_sol": None,
        "round_trip_cost_sol": Decimal("0.0016"),
        "distinct_sellers_one_slot": None,
        "since_prior_exit": None,
        "features": _NO_FEATURES,
    }
    fixed.update(overrides)
    return RealPosition(**fixed)  # type: ignore[arg-type]


def _ficha(positions: list[RealPosition], **overrides: object) -> Ficha:
    fixed: dict[str, object] = {
        "day": date(2026, 9, 24),
        "generated_at": datetime(2026, 9, 25, 3, 0, tzinfo=UTC),
        "positions": positions,
        "spot": [],
        "paper_arms": [],
        "cumulative_pnl_sol": Decimal("-0.4707"),
    }
    fixed.update(overrides)
    data = DayFicha(**fixed)  # type: ignore[arg-type]
    return Ficha(data=data, generated_at=datetime(2026, 9, 25, 3, 0, tzinfo=UTC), git_sha="abc1234")


def test_frontmatter_carries_owner_generator_and_sha() -> None:
    body = render_day(_ficha([_position()]))
    assert "owner: sexta-feira" in body
    assert "generated_by: infra/scripts/meme_daily_ficha.py@abc1234" in body
    assert "data: 2026-09-24" in body


def test_a_winning_position_is_labeled_ganho_not_a_loss_class() -> None:
    body = render_day(_ficha([_position()]))
    assert "| ganho |" in body
    assert "| comprou_no_topo |" not in body  # not a table row: nobody lost that way
    assert "Nenhuma perda fechada neste dia." in body


def test_a_losing_position_shows_its_class_and_feeds_the_totals() -> None:
    losing = _position(
        pnl_sol=Decimal("-0.0556"),
        sol_out=Decimal("0.0156"),
        high_water_sol=Decimal("0.06"),  # below cost 0.07 -> comprou_no_topo
        exit_reason="creator_dump",
        exit_at=datetime(2026, 9, 24, 17, 4, 2, tzinfo=UTC),
    )
    body = render_day(_ficha([losing]))
    assert "| comprou_no_topo |" in body
    assert "## A classe de perda automática" in body
    assert "| comprou_no_topo | 1 |" in body
    assert "Maior vazamento do dia:** `comprou_no_topo`" in body


def test_open_position_never_invents_pnl_or_class() -> None:
    open_position = _position(exit_at=None, sol_out=None, pnl_sol=None, exit_reason=None)
    body = render_day(_ficha([open_position]))
    assert "— (posição aberta)" in body
    assert "posição ainda aberta" in body


def test_missing_features_print_dash_with_reason_never_a_zero() -> None:
    body = render_day(_ficha([_position()]))
    assert "## As métricas da decisão" in body
    assert "sem fita de decisão registrada" in body


def test_spot_and_paper_sections_render_with_and_without_data() -> None:
    empty = render_day(_ficha([_position()]))
    assert "Nenhuma posição real de `spot/1` neste dia." in empty
    assert "Nenhuma entrada de papel nas últimas 24 h." in empty

    spot = SpotPosition(
        market_symbol="TAOUSDT",
        mint="taoC6xyv2v8tDLcev4uaGUgV4vdQsWJrGft2kcBRrBY",
        entry_at=datetime(2026, 9, 25, 14, 30, tzinfo=UTC),
        exit_at=None,
        entry_price=Decimal("302.10"),
        target_price=Decimal("311.50"),
        stop_price=Decimal("295.83"),
        pnl_sol=None,
    )
    arm = PaperArm(
        rule_set="recuo_v1/1",
        entries=91,
        wins=41,
        pnl_sol=Decimal("0.1666"),
        avg_pct_per_ticket=Decimal("2.61"),
    )
    body = render_day(_ficha([_position()], spot=[spot], paper_arms=[arm]))
    assert "`TAOUSDT`" in body and "311.50" in body
    assert "`recuo_v1/1` | 91 | 41 | 0.1666 | 2.6 %" in body


def test_footer_links_the_three_notes() -> None:
    body = render_day(_ficha([_position()]))
    assert "[[Fila de Hipoteses]] · [[KB-0149-o-que-a-mesa-real-ensinou]] · " in body
    assert "[[09-OPERATIONS/Diario/2026-09-24|2026-09-24]]" in body


def test_render_week_rolls_up_loss_classes_across_days() -> None:
    by_day = {
        "2026-09-20": [_position(pnl_sol=Decimal("-0.03"), high_water_sol=Decimal("0.06"))],
        "2026-09-21": [_position(pnl_sol=Decimal("0.02"), high_water_sol=Decimal("0.09"))],
    }
    body = render_week(
        by_day, generated_at=datetime(2026, 9, 26, 3, 0, tzinfo=UTC), git_sha="abc1234"
    )
    assert "Operações reais na semana:** 2" in body
    assert "| comprou_no_topo | 1 |" in body
    assert "Maior vazamento da semana:** `comprou_no_topo`" in body


def test_render_week_with_no_losses_says_so() -> None:
    by_day = {"2026-09-20": [_position()]}
    body = render_week(
        by_day, generated_at=datetime(2026, 9, 26, 3, 0, tzinfo=UTC), git_sha="abc1234"
    )
    assert "Nenhuma perda fechada na semana." in body


def test_day_frontmatter_carries_dataview_fields_for_a_win() -> None:
    body = render_day(_ficha([_position()]))
    assert "dia: 2026-09-24" in body
    assert "operacoes: 1" in body
    assert "ganhos: 1" in body
    assert "pnl_sol: 0.0112" in body
    assert "perdas_comprou_no_topo_n: 0" in body
    assert "perdas_comprou_no_topo_sol: 0.0000" in body
    assert "perdas_golpe_do_criador_n: 0" in body
    assert "perdas_recompra_n: 0" in body
    assert "perdas_custo_n: 0" in body
    assert "perdas_saida_normal_n: 0" in body
    assert "maior_vazamento: null" in body


def test_day_frontmatter_carries_dataview_fields_for_a_loss() -> None:
    losing = _position(
        pnl_sol=Decimal("-0.0556"),
        sol_out=Decimal("0.0156"),
        high_water_sol=Decimal("0.06"),  # below cost 0.07 -> comprou_no_topo
        exit_reason="creator_dump",
    )
    body = render_day(_ficha([losing]))
    assert "operacoes: 1" in body
    assert "ganhos: 0" in body
    assert "pnl_sol: -0.0556" in body
    assert "perdas_comprou_no_topo_n: 1" in body
    assert "perdas_comprou_no_topo_sol: -0.0556" in body
    assert "maior_vazamento: comprou_no_topo" in body


def test_day_frontmatter_never_invents_a_zero_for_an_open_position() -> None:
    open_position = _position(exit_at=None, sol_out=None, pnl_sol=None, exit_reason=None)
    body = render_day(_ficha([open_position]))
    assert "operacoes: 1" in body
    assert "ganhos: 0" in body
    assert "pnl_sol: 0.0000" in body  # net over zero closed positions, not a guess
    assert "maior_vazamento: null" in body  # no closed loss at all to name


def test_week_frontmatter_carries_window_and_dataview_totals() -> None:
    by_day = {
        "2026-09-20": [_position(pnl_sol=Decimal("-0.03"), high_water_sol=Decimal("0.06"))],
        "2026-09-21": [_position(pnl_sol=Decimal("0.02"), high_water_sol=Decimal("0.09"))],
    }
    body = render_week(
        by_day, generated_at=datetime(2026, 9, 26, 3, 0, tzinfo=UTC), git_sha="abc1234"
    )
    assert "semana_inicio: 2026-09-20" in body
    assert "semana_fim: 2026-09-21" in body
    assert "operacoes: 2" in body
    assert "ganhos: 1" in body
    assert "pnl_sol: -0.0100" in body
    assert "perdas_comprou_no_topo_n: 1" in body
    assert "perdas_comprou_no_topo_sol: -0.0300" in body
    assert "maior_vazamento: comprou_no_topo" in body
