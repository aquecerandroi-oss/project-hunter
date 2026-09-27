"""Fábrica de dados SINTÉTICOS para os testes do spec J (EXP-M26 / H-022).

Nada aqui é dado do projeto: cada oportunidade e cada aposta é inventada pelo teste, com
valores conhecidos, para provar uma regra do protocolo congelado. Só vive em `tests/`.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from infra.research.exp_m26.constantes import RULE_SET_C
from infra.research.exp_m26.modelo import Aposta, Oportunidade

T0 = datetime(2026, 10, 1, 0, 0, tzinfo=UTC)
SIZE = Decimal("0.07")


def aposta(y: float | None = 0.1, **kw: Any) -> Aposta:
    """Aposta fechada e medida com `pnl_sol / size_sol = y` (None = aberta)."""
    entry = kw.pop("entry_at", T0 + timedelta(minutes=1))
    base = Aposta(
        entry_at=entry,
        fill_observed_at=entry,
        fill_source="chain",
        sol_spent=SIZE,
        size_sol=SIZE,
        status="closed" if y is not None else "open",
        exit_at=None if y is None else entry + timedelta(minutes=5),
        exit_reason=None if y is None else "target",
        pnl_sol=None if y is None else (SIZE * Decimal(str(y))),
        outcome_quality="measured",
        sale_observed_at=None if y is None else entry + timedelta(minutes=5),
        sale_complete=None if y is None else False,
        token_completed_at=None,
        token_migrated_at=None,
        high_water_x=Decimal("1.2"),
        fee_buy_sol=SIZE * Decimal("0.0175"),
        fee_sell_sol=Decimal("0.001"),
        curve_proceeds_sol=Decimal("0.08"),
    )
    return replace(base, **kw)


def oportunidade(
    mint: str = "m0",
    *,
    at: datetime = T0 + timedelta(minutes=5),
    classe: str = "true",
    y: float | None = 0.1,
    **kw: Any,
) -> Oportunidade:
    """Oportunidade de C avaliada em `at`, já com a aposta (ou sem ela, `y=None` e
    `aposta_=None`). `classe` escolhe os insumos de linha: true/false/flat/unknown."""
    lines: dict[str, Any] = {
        "true": {
            "line_reason": None,
            "higher_lows": True,
            "breakout_15m": True,
            "distance_to_support_pct": Decimal("0.10"),
        },
        "false": {
            "line_reason": None,
            "higher_lows": True,
            "breakout_15m": False,
            "distance_to_support_pct": Decimal("0.10"),
        },
        "flat": {
            "line_reason": "flat",
            "higher_lows": None,
            "breakout_15m": None,
            "distance_to_support_pct": None,
        },
        "unknown": {
            "line_reason": "too_few_points",
            "higher_lows": None,
            "breakout_15m": None,
            "distance_to_support_pct": None,
        },
    }[classe]
    bet = kw.pop("aposta_", "auto")
    base = Oportunidade(
        rule_set_id=RULE_SET_C,
        mint=mint,
        evaluated_at=at,
        features_end_time=at - timedelta(seconds=5),
        features_computed_at=at - timedelta(seconds=2),
        fidelity="faithful",
        coverage_status="covered",
        mcap_slope_15m=Decimal("0.5"),
        curve_progress_pct=Decimal("0.30"),
        proposal_refusals=(),
        no_proposal_reason=None,
        proposal_id=f"p-{mint}",
        proposal_status="filled",
        proposal_refusal=None,
        aposta=aposta(y) if bet == "auto" else bet,
        prior_other_bet=False,
        **lines,
    )
    return replace(base, **kw)
