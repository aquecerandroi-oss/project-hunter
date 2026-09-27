"""Cenário contábil "real-equivalente" (§4, descritivo; nunca entra no rótulo).

Não re-simula: mantém fills, gatilhos e impacto (o `target_x` incide sobre a marca líquida,
`exits.py:229`, e mudaria de lugar numa re-simulação). Sobre o mesmo `size_sol`:

    PnL_alt = PnL_papel + taxas_papel_debitadas − taxas_alternativas − custos_adicionais

- taxas de papel debitadas = `entry.fee_sol` + `exit.fee_sol` (as que o papel gravou);
- taxas alternativas = 1,045 % × `sol_spent` (compra) + 1,045 % × `curve_proceeds_sol`
  (venda) — a média da KB-0147 repartida por perna: é **cenário**, não a taxa exata;
- custos adicionais = 0,13 % × `size_sol` de rede + rent (0,00151384 SOL ou devolvido).
"""

from __future__ import annotations

from decimal import Decimal

from infra.research.exp_m26.constantes import REDE_IDA_E_VOLTA, TAXA_ALT_PERNA
from infra.research.exp_m26.modelo import Aposta


def pnl_alternativo(a: Aposta, rent: Decimal) -> Decimal | None:
    if (
        a.pnl_sol is None
        or a.fee_buy_sol is None
        or a.fee_sell_sol is None
        or a.curve_proceeds_sol is None
    ):
        return None
    debitadas = a.fee_buy_sol + a.fee_sell_sol
    alternativas = TAXA_ALT_PERNA * a.sol_spent + TAXA_ALT_PERNA * a.curve_proceeds_sol
    adicionais = REDE_IDA_E_VOLTA * a.size_sol + rent
    return a.pnl_sol + debitadas - alternativas - adicionais
