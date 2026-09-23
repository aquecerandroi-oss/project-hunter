"""R75 — testes do carregador da H-013 (dados sintéticos, valores esperados à mão)."""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from load import Thresholds, equilibrio, features, one_per_mint, parse

T = Thresholds(ratio=0.6, flow=Decimal("2"), progress=Decimal("25"))


def _raw(**kw: object) -> dict[str, str]:
    flow = {"feature": "flow", "buys_1m": 39, "sells_1m": 36, "net_sol_flow_1m": "0.4"}
    flow.update(kw.pop("flow", {}))  # type: ignore[arg-type]
    base = {
        "lane": "live", "bet_id": "b1", "mint": "M1", "symbol": "SHORT", "rule_set": "operator/5",
        "gate": "fluxo_e_holders/2", "series": "meme_event_gate_v1",
        "decided_at": "2026-09-23 20:39:16.35314+00",
        "entry_at": "2026-09-23 20:39:17.0+00", "exit_at": "2026-09-23 20:39:18.6+00",
        "exit_reason": "trailing", "size_sol": "0.0716", "pnl_sol": "-0.0134",
        "flow_json": json.dumps(flow), "progress_pct": "13.7",
    }
    base.update({k: str(v) for k, v in kw.items()})
    return base


def test_short_is_equilibrio() -> None:
    r = parse(_raw())
    assert r["ratio"] == pytest.approx(36 / 39)
    assert r["net_flow"] == Decimal("0.4") and r["progress"] == Decimal("13.7")
    assert equilibrio(r, T) is True
    assert r["hold_s"] == pytest.approx(1.6)
    assert r["ret"] == pytest.approx(float(Decimal("-0.0134") / Decimal("0.0716")))
    assert r["dia"] == "2026-09-23" and r["hora"] == "2026-09-23T20"


def test_each_condition_breaks_the_conjunction_and_boundaries() -> None:
    # vendas÷compras 0,6 exato conta (≥); 0,59 não
    assert equilibrio(parse(_raw(flow={"buys_1m": 10, "sells_1m": 6})), T) is True
    assert equilibrio(parse(_raw(flow={"buys_1m": 100, "sells_1m": 59})), T) is False
    # fluxo 2 exato NÃO conta (< 2)
    assert equilibrio(parse(_raw(flow={"net_sol_flow_1m": "2"})), T) is False
    assert equilibrio(parse(_raw(flow={"net_sol_flow_1m": "-3.5"})), T) is True
    # progresso 25 exato NÃO conta (< 25)
    assert equilibrio(parse(_raw(progress_pct="25")), T) is False
    assert equilibrio(parse(_raw(progress_pct="24.99")), T) is True


def test_missing_parts_are_undefined_not_false() -> None:
    assert equilibrio(parse(_raw(flow_json="")), T) is None
    assert equilibrio(parse(_raw(progress_pct="")), T) is None
    assert equilibrio(parse(_raw(flow={"net_sol_flow_1m": None})), T) is None
    # sem compras e sem vendas a razão não existe; sem compras e com vendas é infinita
    assert parse(_raw(flow={"buys_1m": 0, "sells_1m": 0}))["ratio"] is None
    assert equilibrio(parse(_raw(flow={"buys_1m": 0, "sells_1m": 3})), T) is True


def test_features_exposes_the_three_conditions_separately() -> None:
    f = features(parse(_raw(flow={"net_sol_flow_1m": "5"})), T)
    assert f == {"c_ratio": True, "c_flow": False, "c_prog": True, "equilibrio": False}


def test_one_per_mint_real_wins_then_oldest() -> None:
    rows = [
        parse(_raw(lane="paper", bet_id="p1", decided_at="2026-09-23 20:00:00+00")),
        parse(_raw(lane="live", bet_id="l2", decided_at="2026-09-23 20:05:00+00")),
        parse(_raw(lane="live", bet_id="l1", decided_at="2026-09-23 20:04:00+00")),
        parse(_raw(lane="paper", bet_id="p9", mint="M2", decided_at="2026-09-23 21:00:00+00")),
        parse(_raw(lane="paper", bet_id="p8", mint="M2", decided_at="2026-09-23 20:59:00+00")),
    ]
    kept = {r["mint"]: r["bet_id"] for r in one_per_mint(rows)}
    assert kept == {"M1": "l1", "M2": "p8"}


def test_money_stays_decimal() -> None:
    r = parse(_raw())
    assert isinstance(r["pnl_sol"], Decimal) and isinstance(r["size_sol"], Decimal)


def test_dedup_happens_before_censoring() -> None:
    """Achado da Astra: censurar antes deixava o papel tomar o lugar da real censurada."""
    from load import population

    rows = [
        parse(_raw(lane="live", bet_id="l1", progress_pct="")),  # real sem progresso
        parse(_raw(lane="paper", bet_id="p1", decided_at="2026-09-23 20:00:00+00")),
        parse(_raw(lane="paper", bet_id="p2", mint="M2", gate="sonda_de_hype/1")),
    ]
    kept, censored = population(rows)
    assert kept == [] and [r["bet_id"] for r in censored] == ["l1"]
