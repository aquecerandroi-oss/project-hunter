"""Calibração do erro tipo I sob nulos realistas (Astra R1, must-fix 3) — painéis SINTÉTICOS.

Nulo = a IA não sabe nada do futuro do dia, mas: (a) o mercado tem deriva por horário e a IA
tem política de relógio; (b) o mercado tem persistência dentro do dia e a IA escolhe um lado só
por dia. A permutação por pregão dentro do mês tem de rejeitar perto de 5 %, não muito acima.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np

from infra.research.b3.ia_grafico.estatistica import Celula, Painel, p_permutacao
from infra.research.b3.ia_grafico.resposta import Lado


def _nulo(rng: np.random.Generator) -> Painel:
    celulas: list[Celula] = []
    deriva = rng.normal(0, 4, size=12)  # deriva por horário, em bp
    pi_relogio = rng.uniform(0.2, 0.8, size=12)  # política de relógio
    for k in range(6 * 20):  # 6 meses de 20 pregões
        dia = date(2025, 1, 1) + timedelta(days=k * 30 // 20)
        choque_do_dia = rng.normal(0, 15)
        lado_do_dia = rng.random() < 0.5
        for slot in range(12):
            mov = deriva[slot] + 0.7 * choque_do_dia + rng.normal(0, 25)
            usa_dia = rng.random() < 0.5
            compra = lado_do_dia if usa_dia else rng.random() < pi_relogio[slot]
            lado = Lado.COMPRA if compra else Lado.VENDA
            celulas.append(
                Celula(
                    dia, slot, lado, mov - 1.3, -mov - 1.3, -40.0, -40.0, 38.0, 38.0, Lado.NENHUM
                )
            )
    return Painel.de_celulas(celulas)


def test_permutacao_por_pregao_rejeita_perto_de_5_por_cento_sob_o_nulo() -> None:
    rng = np.random.default_rng(20261017)
    ps = [p_permutacao(_nulo(rng), reps=99, semente=s) for s in range(120)]
    taxa = float(np.mean(np.array(ps) < 0.05))
    # 120 painéis: sob 5 % verdadeiro, P(taxa > 0,12) < 1 %
    assert taxa <= 0.12, taxa
