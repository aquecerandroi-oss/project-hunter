"""Do que foi avaliado ao ``Resumo`` do veredito, e os diagnósticos publicados sem decidir.

Diagnósticos (Astra R1: não são cláusulas): consistência do espelho (a leitura do gráfico
invertido deve dar o lado oposto) e autoconcordância (a mesma imagem pedida de novo dá o mesmo
lado?). Kappa indefinido é ``None``, nunca zero.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from itertools import combinations
from statistics import fmean

from infra.research.b3.ia_grafico.estatistica import (
    Painel,
    contraste,
    d_media_movel,
    ic_bootstrap_meses,
    metades,
    nivel,
    p_permutacao,
)
from infra.research.b3.ia_grafico.pipeline import Avaliacao
from infra.research.b3.ia_grafico.protocolo import REPLICAS, SEMENTE
from infra.research.b3.ia_grafico.resposta import Lado
from infra.research.b3.ia_grafico.veredito import Resumo

_OPOSTO = {Lado.COMPRA: Lado.VENDA, Lado.VENDA: Lado.COMPRA, Lado.NENHUM: Lado.NENHUM}


def _media(xs: Sequence[float]) -> float:
    return fmean(xs) if xs else float("nan")


def _meses(p: Painel) -> int:
    return len(
        {(p.dias[i].year, p.dias[i].month) for i in range(len(p.dias)) if p.mascara[i].any()}
    )


def resumir(
    *,
    primario: Avaliacao,
    patamar45: Avaliacao,
    patamar75: Avaliacao,
    holdout: Avaliacao | None,
    n_chamadas: int,
    n_invalidas: int,
    holdout_n_chamadas: int,
    holdout_n_invalidas: int,
    reps: int = REPLICAS,
    semente: int = SEMENTE,
) -> Resumo:
    _exigir_conjuntos(primario, patamar45, patamar75, holdout)
    p = Painel.de_celulas(primario.celulas)
    h = Painel.de_celulas(holdout.celulas) if holdout is not None else None
    vazio = p.n_operacoes == 0
    return Resumo(
        n_chamadas=n_chamadas,
        n_invalidas=n_invalidas,
        n_instantes=len(primario.celulas),
        n_operacoes=p.n_operacoes,
        n_censuradas=len(
            p.chaves_censuradas()
            | Painel.de_celulas(patamar45.celulas).chaves_censuradas()
            | Painel.de_celulas(patamar75.celulas).chaves_censuradas()
        )
        + primario.n_censuradas_completo,
        n_sem_preco_entrada=primario.n_sem_preco_entrada,
        n_meses=_meses(p),
        d=contraste(p),
        ic=(math.nan, math.nan) if vazio else ic_bootstrap_meses(p, reps=reps, semente=semente),
        p=math.nan if vazio else p_permutacao(p, reps=reps, semente=semente),
        nivel_direcional=nivel(p),
        nivel_completo=_media(primario.completo_bp),
        metades=metades(p),
        patamar=(
            contraste(Painel.de_celulas(patamar45.celulas)),
            contraste(Painel.de_celulas(patamar75.celulas)),
        ),
        d_mm=d_media_movel(p),
        holdout_operacoes=0 if h is None else h.n_operacoes,
        holdout_meses=0 if h is None else _meses(h),
        holdout_nivel_completo=None if holdout is None else _media(holdout.completo_bp),
        holdout_d=None if h is None or h.n_operacoes == 0 else contraste(h),
        ic_otimista=(math.nan, math.nan)
        if vazio
        else ic_bootstrap_meses(p, reps=reps, semente=semente, otimista=True),
        holdout_n_chamadas=holdout_n_chamadas,
        holdout_n_invalidas=holdout_n_invalidas,
        holdout_n_censuradas=0
        if holdout is None or h is None
        else h.n_censuradas + holdout.n_censuradas_completo,
        holdout_n_sem_preco_entrada=0 if holdout is None else holdout.n_sem_preco_entrada,
    )


def _exigir_conjuntos(
    primario: Avaliacao, p45: Avaliacao, p75: Avaliacao, holdout: Avaliacao | None
) -> None:
    """Astra R2: o caminho de análise verifica o que o texto promete (disjunção e mesmos instantes)."""
    chaves = {(c.dia, c.slot) for c in primario.celulas}
    for nome, outro in (("patamar 45 min", p45), ("patamar 75 min", p75)):
        if {(c.dia, c.slot) for c in outro.celulas} != chaves:
            raise ValueError(f"{nome}: instantes diferentes dos do primário")
    if holdout is not None and holdout.celulas and primario.celulas:
        if min(c.dia for c in holdout.celulas) <= max(c.dia for c in primario.celulas):
            raise ValueError("holdout precisa começar depois do último pregão do primário")


def consistencia_espelho(
    originais: Mapping[str, Lado | None], espelhados: Mapping[str, Lado | None]
) -> dict[str, object]:
    """Lado bruto do espelho (nas coordenadas da imagem invertida) contra o original."""
    pares = consistentes = none_concorda = 0
    for chave, lado in originais.items():
        outro = espelhados.get(chave)
        if lado is None or outro is None:
            continue
        if lado is Lado.NENHUM:
            none_concorda += outro is Lado.NENHUM
            continue
        pares += 1
        consistentes += outro is _OPOSTO[lado]
    return {
        "pares": pares,
        "consistentes": consistentes,
        "taxa": consistentes / pares if pares else None,
        "none_concorda": none_concorda,
    }


def autoconcordancia(
    primeira: Mapping[str, Lado | None], repeticoes: Mapping[str, Sequence[Lado | None]]
) -> dict[str, object]:
    """Concordância de lado em **todos os pares** entre as respostas válidas do mesmo instante."""
    pares: list[tuple[Lado, Lado]] = []
    for chave, lado in primeira.items():
        validas = [x for x in (lado, *repeticoes.get(chave, ())) if x is not None]
        pares += list(combinations(validas, 2))
    if not pares:
        return {"pares": 0, "iguais": 0, "taxa": None, "kappa": None}
    iguais = sum(a == b for a, b in pares)
    n = len(pares)
    po = iguais / n
    pe = sum(
        (sum(a is k for a, _ in pares) / n) * (sum(b is k for _, b in pares) / n) for k in Lado
    )
    kappa = None if math.isclose(pe, 1.0) else (po - pe) / (1 - pe)
    return {"pares": n, "iguais": iguais, "taxa": po, "kappa": kappa}
