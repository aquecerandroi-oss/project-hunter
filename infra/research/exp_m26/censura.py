"""Estresse de censura da primária (§4, congelado; rodadas 2–4 da Astra).

Aplica-se às compras **preenchidas** sem desfecho precificável (motivo C). As sem fill (F)
não tiveram posição: ficam fora do PnL e só contam no teto.

- **Cenário que sustenta o rótulo:** C de `true` em perda integral (−`sol_spent`/`size_sol`,
  presa à unidade); C de `false` entram no n do estrato com a média dos `false` observados
  do estrato, recalculada em cada réplica. Estrato sem `false` observado não tem média
  imputável: fica fora (nunca se inventa quantil nem média de grupo vazio).
- **Diagnósticos, sempre publicados:** C de `true` a −0,50; ponto de inversão (o valor comum
  dos C de `true` que leva D a 0 e ao MRE: `D(x) = a + b·x` com suporte fixo); grade 2D.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import numpy as np

from infra.research.exp_m26.classes import Registro
from infra.research.exp_m26.constantes import PONTOS_GRADE
from infra.research.exp_m26.estimador import Estimativa, Unidades, estimar, unidades

_CLASSES = ("true", "false")


def unidades_primarias(
    regs: Sequence[Registro],
    *,
    estresse: bool,
    valor_true_c: float | None = None,
    valor_false_c: float | None = None,
) -> tuple[Unidades, list[str]]:
    """As unidades da primária e os seus mints (para o bootstrap por mint).

    Sem estresse: só os avaliáveis (A). Com estresse: A e C; o valor de um C de `true` é a
    sua perda integral (ou `valor_true_c`), o de um C de `false` é "sem valor" (ou
    `valor_false_c`, só na grade)."""
    est: list[str] = []
    grp: list[bool] = []
    val: list[float | None] = []
    mints: list[str] = []
    for r in regs:
        if r.classe not in _CLASSES or r.motivo not in ("A", "C"):
            continue
        if r.motivo == "C" and not estresse:
            continue
        if r.motivo == "A":
            v = r.y
        elif r.classe == "true":
            v = r.perda if valor_true_c is None else valor_true_c
        else:
            v = valor_false_c
        est.append(r.bloco)
        grp.append(r.classe == "true")
        val.append(v)
        mints.append(r.o.mint)
    return unidades(est, grp, val), mints


def diagnostico(regs: Sequence[Registro], valor_true_c: float) -> Estimativa:
    return estimar(unidades_primarias(regs, estresse=True, valor_true_c=valor_true_c)[0])


def inversao(regs: Sequence[Registro], alvo: float) -> float | None:
    """O valor comum dos C de `true` que leva D a `alvo`, ou `None` se não há solução
    única (sem C de `true` com peso num estrato válido, ou D indefinido)."""
    d0 = diagnostico(regs, 0.0).d
    d1 = diagnostico(regs, 1.0).d
    if not (math.isfinite(d0) and math.isfinite(d1)) or abs(d1 - d0) < 1e-15:
        return None
    return (alvo - d0) / (d1 - d0)


def _pontos(valores: list[float]) -> list[float]:
    """−1, meio, média, meio, p90 (numpy linear) dos observados do grupo."""
    media = float(np.mean(valores))
    p90 = float(np.quantile(valores, 0.9))
    return [-1.0, (-1.0 + media) / 2, media, (media + p90) / 2, p90][:PONTOS_GRADE]


def grade(regs: Sequence[Registro]) -> list[dict[str, Any]]:
    """D pontual para cada par (média ausente de `true`, média ausente de `false`)."""
    obs = {c: [r.y for r in regs if r.classe == c and r.y is not None] for c in _CLASSES}
    if not obs["true"] or not obs["false"]:
        return []
    out: list[dict[str, Any]] = []
    for xt in _pontos([float(v) for v in obs["true"]]):
        for xf in _pontos([float(v) for v in obs["false"]]):
            u, _ = unidades_primarias(regs, estresse=True, valor_true_c=xt, valor_false_c=xf)
            out.append({"true_ausente": xt, "false_ausente": xf, "d": estimar(u).d})
    return out
