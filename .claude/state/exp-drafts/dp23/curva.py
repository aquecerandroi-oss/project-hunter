"""D-P23 — a curva de movimento do preco DEPOIS da entrada, em unidades de ATR.

DIAGNOSTICO, nao regua causal. A pergunta e descritiva: **onde, ao longo do
periodo de manutencao, o ganho bruto da mae se acumula** — e o horizonte de 80
min da irma de 5 min cai antes ou depois desse ponto. Nada aqui atribui causa a
diferenca de desempenho entre as duas versoes; a transposicao mudou tres coisas
de uma vez (tendencia 1 h -> 15 min, ATR 15 -> 5 min, horizonte 14 400 -> 4 800 s,
`mean_reversion_m5_v1.py:27`).

Definicoes, todas declaradas:

* `ret_atr(open_da_entrada, preco, atr) = (preco - open) / atr`, long-only (a
  populacao inteira e `long`, conferido no q00 §2). A base e o **open da barra de
  entrada**, nunca `virtual_entry` — que ja contem os 6 bps de spread+slippage
  (`pricing.py:47`). Por isso a curva e **bruta**.
* percentis por **interpolacao linear** (a convencao de `numpy.percentile`);
  mediana de amostra par e a media dos dois centrais.
* `frac_pos` conta positivos **estritos**; o numero de zeros exatos viaja ao lado
  para que a escolha seja auditavel.
* ausencia de endpoint e `nan` e **sai do denominador** daquele horizonte — nunca
  e preenchida com o preco anterior nem com zero. A cobertura e por horizonte.
* o Δ(h_longo − h_curto) e pareado **por decisao**: so a decisao que tem os dois
  pontos entra, e o estimador e a **media das diferencas**, nunca a diferenca das
  medias de duas populacoes diferentes (que e o erro que o teste
  `..._nao_a_diferenca_das_medias_...` fixa).
* o IC 95 % do Δ vem do bootstrap de **blocos de dia** de
  `.claude/state/exp-drafts/t362b/blocos90.py` (`ic_media`), **reusado e nao
  reimplementado**: decisoes do mesmo dia em mercados correlacionados dividem
  regime e choque, e o mesmo dia reamostrado alimenta os dois horizontes de uma
  vez (era a exigencia da Astra: "os mesmos dias reamostrados conjuntamente entre
  mercados e horizontes").

NumPy sobre janelas em memoria; nada de pandas. Nada aqui e dinheiro persistido,
entao nada aqui e ``Decimal`` (PIPELINE §9: a fronteira `Decimal` fica no banco).
"""

from __future__ import annotations

import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

_T362B = Path(__file__).resolve().parent.parent / "t362b"
if str(_T362B) not in sys.path:  # reuso do bootstrap ja testado, nao uma copia
    sys.path.insert(0, str(_T362B))

from blocos90 import ic_media  # noqa: E402

__all__ = [
    "Resumo",
    "DeltaPareado",
    "curva_por_horizonte",
    "delta_pareado_por_decisao",
    "resumo",
    "ret_atr",
]

_NAN = float("nan")


def ret_atr(*, entry_open: float, preco: float, atr: float) -> float:
    """(preco − open da entrada) / ATR. Long-only; ATR nao positivo e recusa."""
    if not atr > 0:
        raise ValueError(f"ATR nao positivo nao e unidade: {atr!r}")
    return (float(preco) - float(entry_open)) / float(atr)


@dataclass(frozen=True)
class Resumo:
    n: int
    media: float
    mediana: float
    p25: float
    p75: float
    frac_pos: float
    zeros: int = 0


def resumo(valores: np.ndarray) -> Resumo:
    """Media, mediana, p25/p75 e fracao positiva, ignorando ausencia (`nan`)."""
    v = np.asarray(valores, dtype=float)
    v = v[~np.isnan(v)]
    if v.size == 0:
        return Resumo(0, _NAN, _NAN, _NAN, _NAN, _NAN, 0)
    return Resumo(
        n=int(v.size),
        media=float(v.mean()),
        mediana=float(np.percentile(v, 50, method="linear")),
        p25=float(np.percentile(v, 25, method="linear")),
        p75=float(np.percentile(v, 75, method="linear")),
        frac_pos=float((v > 0).sum() / v.size),
        zeros=int((v == 0).sum()),
    )


def curva_por_horizonte(
    linhas: Iterable[tuple[str, int, float]],
    *,
    horizontes: Sequence[int],
) -> dict[int, Resumo]:
    """``(decisao, horizonte, ret)`` → um :class:`Resumo` por horizonte pedido."""
    baldes: dict[int, list[float]] = {h: [] for h in horizontes}
    for _decisao, h, ret in linhas:
        if h in baldes:
            baldes[h].append(float(ret))
    return {h: resumo(np.array(baldes[h], dtype=float)) for h in horizontes}


@dataclass(frozen=True)
class DeltaPareado:
    n: int
    dias: int
    media: float
    mediana: float
    ic95: tuple[float, float]
    reamostragens: int
    n_so_curto: int = 0
    n_so_longo: int = 0


def delta_pareado_por_decisao(
    linhas: Iterable[tuple[str, str, int, float]],
    *,
    h_longo: int,
    h_curto: int,
    reamostragens: int = 20_000,
    seed: int = 20260910,
) -> DeltaPareado:
    """Δ = media[ret(h_longo) − ret(h_curto)] sobre a MESMA decisao.

    ``linhas`` e ``(decisao, dia, horizonte, ret)``. Uma decisao que so tem um
    dos dois pontos e contada (``n_so_curto``/``n_so_longo``) e **nao** entra:
    inventar o ponto que falta e exatamente o que a regra "ausencias nao
    preenchidas" proibe.
    """
    curto: dict[str, float] = {}
    longo: dict[str, float] = {}
    dia_de: dict[str, str] = {}
    for decisao, dia, h, ret in linhas:
        dia_de[decisao] = dia
        if np.isnan(float(ret)):
            continue
        if h == h_curto:
            curto[decisao] = float(ret)
        elif h == h_longo:
            longo[decisao] = float(ret)

    pares = sorted(set(curto) & set(longo))
    dias = [dia_de[d] for d in pares]
    diffs = np.array([longo[d] - curto[d] for d in pares], dtype=float)
    if diffs.size == 0:
        return DeltaPareado(
            0, 0, _NAN, _NAN, (_NAN, _NAN), 0,
            n_so_curto=len(set(curto) - set(longo)),
            n_so_longo=len(set(longo) - set(curto)),
        )
    intervalo = ic_media(dias, diffs, reamostragens=reamostragens, seed=seed)
    return DeltaPareado(
        n=int(diffs.size),
        dias=intervalo.dias,
        media=float(diffs.mean()),
        mediana=float(np.percentile(diffs, 50, method="linear")),
        ic95=intervalo.ic95,
        reamostragens=reamostragens,
        n_so_curto=len(set(curto) - set(longo)),
        n_so_longo=len(set(longo) - set(curto)),
    )


# --------------------------------------------------------------------------
# Anti-antecipacao: qual vela e o endpoint de +h, e qual NUNCA pode ser.
# --------------------------------------------------------------------------

_UM_MINUTO_EM_MIN = 1


def endpoint_open_time(entry_minuto: int, h: int) -> int:
    """O ``open_time`` (em minutos desde a entrada) da vela que FECHA em ``+h``.

    A entrada acontece no **open** da barra ``entry_minuto`` (o walker entra no
    open, `walker.py:42`), logo o instante da entrada e o inicio dessa vela. O
    preco ``h`` minutos depois e o **fechamento** da vela que termina em
    ``entrada + h``, e essa vela **abre** em ``entrada + h − 1``.

    Usar a vela que ABRE em ``+h`` (que fecha em ``+h+1``) acrescentaria um
    minuto ao horizonte e leria uma vela que, no instante ``+h``, ainda estava em
    formacao — o cenario de falha nomeado pela Astra (MUST-FIX 3) e a forma que a
    antecipacao tomaria nesta medicao.
    """
    if h < _UM_MINUTO_EM_MIN:
        raise ValueError(f"horizonte em minutos tem de ser >= 1: {h!r}")
    return entry_minuto + h - _UM_MINUTO_EM_MIN


def escolhe_endpoint(
    velas: Iterable[tuple[int, float, bool]],
    *,
    entry_minuto: int,
    h: int,
) -> float | None:
    """O fechamento do endpoint de ``+h``, ou ``None`` — nunca um substituto.

    ``velas`` e ``(open_time_em_minutos, close, is_final)``. Uma vela nao final
    **nao existe** para esta leitura (PIPELINE §2, anti-look-ahead: bar-features
    usam so vela ``is_final``), e a ausencia devolve ``None`` em vez do preco
    anterior.
    """
    alvo = endpoint_open_time(entry_minuto, h)
    for open_time, close, is_final in velas:
        if open_time == alvo and is_final:
            return float(close)
    return None


# --------------------------------------------------------------------------
# IC da MEDIANA por blocos de dia.
# --------------------------------------------------------------------------

from blocos90 import Intervalo, _por_dia  # noqa: E402


def ic_mediana_blocos(
    dias: Sequence[str],
    valores: np.ndarray,
    *,
    reamostragens: int = 20_000,
    seed: int = 20260910,
) -> Intervalo:
    """IC 95 % da **mediana**, reamostrando dias inteiros com reposicao.

    Irmao de ``blocos90.ic_media``, mesmo bloco e mesma justificativa (KB-0010).
    Existe porque a media do Δ pareado e sensivel a cauda: sem um segundo
    estimador nao da para separar "muitas decisoes andam um pouco mais" de
    "poucas decisoes andam muito mais", e as duas leituras levam a experimentos
    diferentes. O campo ``media`` do :class:`Intervalo` guarda a estatistica
    pedida (aqui, a mediana) — reusar a estrutura evita um terceiro tipo com o
    mesmo conteudo, e o nome do chamador diz qual estatistica e.
    """
    v = np.asarray(valores, dtype=float)
    if v.size == 0:
        return Intervalo(0, 0, _NAN, (_NAN, _NAN), 0)
    ordem, baldes = _por_dia(list(dias), v)
    rng = np.random.default_rng(seed)
    idx = np.arange(len(ordem))
    amostras = np.empty(reamostragens, dtype=float)
    for k in range(reamostragens):
        escolhidos = rng.choice(idx, size=len(ordem), replace=True)
        amostras[k] = np.percentile(
            np.concatenate([baldes[i] for i in escolhidos]), 50, method="linear"
        )
    return Intervalo(
        n=int(v.size),
        dias=len(ordem),
        media=float(np.percentile(v, 50, method="linear")),
        ic95=(float(np.percentile(amostras, 2.5)), float(np.percentile(amostras, 97.5))),
        reamostragens=reamostragens,
    )


def diferencas_pareadas(
    linhas: Iterable[tuple[str, str, int, float]],
    *,
    h_longo: int,
    h_curto: int,
) -> tuple[list[str], np.ndarray]:
    """Os dias e as diferencas ``ret(h_longo) − ret(h_curto)`` das decisoes pareadas.

    A mesma selecao de :func:`delta_pareado_por_decisao`, exposta para que um
    segundo estimador (a mediana) leia **exatamente** a mesma populacao em vez de
    reconstrui-la com outra regra.
    """
    curto: dict[str, float] = {}
    longo: dict[str, float] = {}
    dia_de: dict[str, str] = {}
    for decisao, dia, h, ret in linhas:
        dia_de[decisao] = dia
        if np.isnan(float(ret)):
            continue
        if h == h_curto:
            curto[decisao] = float(ret)
        elif h == h_longo:
            longo[decisao] = float(ret)
    pares = sorted(set(curto) & set(longo))
    return [dia_de[d] for d in pares], np.array([longo[d] - curto[d] for d in pares], dtype=float)
