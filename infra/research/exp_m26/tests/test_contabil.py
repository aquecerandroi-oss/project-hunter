"""O cenário contábil "real-equivalente" (§4): remove as taxas de papel já debitadas e
aplica as alternativas, sem re-simular (r2 5e: nada de somar 3,5 % e descontar outra
constante; bases diferentes na compra e na venda)."""

from __future__ import annotations

from decimal import Decimal

from infra.research.exp_m26.contabil import pnl_alternativo
from infra.research.exp_m26.tests.fabrica import aposta


def test_equacao_com_as_bases_de_cada_perna() -> None:
    a = aposta(
        0.0,
        pnl_sol=Decimal("0.01"),
        fee_buy_sol=Decimal("0.001225"),
        fee_sell_sol=Decimal("0.0014"),
        sol_spent=Decimal("0.07"),
        curve_proceeds_sol=Decimal("0.08"),
    )
    rent = Decimal("0.00151384")
    esperado = (
        Decimal("0.01")
        + Decimal("0.001225")
        + Decimal("0.0014")
        - Decimal("0.01045") * Decimal("0.07")
        - Decimal("0.01045") * Decimal("0.08")
        - Decimal("0.0013") * Decimal("0.07")
        - rent
    )
    assert pnl_alternativo(a, rent) == esperado
    assert pnl_alternativo(a, Decimal("0")) == esperado + rent


def test_sem_numeros_de_taxa_nao_ha_cenario() -> None:
    assert pnl_alternativo(aposta(0.1, fee_sell_sol=None), Decimal("0")) is None
    assert pnl_alternativo(aposta(None), Decimal("0")) is None
