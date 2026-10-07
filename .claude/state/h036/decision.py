"""h036 — a função de decisão ÚNICA da H-036 (emenda de 2026-10-07): a mesma chamada decide na consulta real (uma
linha) e em cada caminho da simulação de poder (muitas linhas). Entra só o que a consulta conhece: por dia de calendário
(colunas), quantos trades houve (``c``), a soma do R primário (``s``, todo a mercado ao custo medido) e a soma do R no
estresse (``t``); e se a cobertura passou (``coverage_ok``).

Ordem de precedência, congelada (Astra must-fix 3): portões de dado e cobertura → CONFIRMA → (futilidade ou final)
REFUTA / NÃO CONFIRMA → continua. Os rótulos são mutuamente exclusivos; LIMITE não é um quarto veredito científico, é
motivo de dado/instrumento.

Eficácia: Haybittle-Peto com gasto de Bonferroni — α 0,0005 em L1, 0,0005 em L2 e ``ALPHA_FINAL`` em L3, cada um
convertido para t(G−1), G = semanas ISO com trade. A soma limita o erro do tipo I em qualquer distribuição da informação entre consultas (Astra
must-fix 1: o calendário não precisa acompanhar a informação). REFUTA usa o limite superior ``m + t(P_REF; G−1)·EP``,
com ``P_REF`` calibrado por simulação para P(REFUTA | θ = +0,10) ≤ 0,025 no procedimento inteiro (must-fix 2).
"""

from __future__ import annotations

from statistics import NormalDist

import numpy as np

import design

CONTINUA, CONFIRMA, REFUTA, NAO_CONFIRMA, LIMITE = 0, 1, 2, 3, 4
NOMES = {CONTINUA: "continua", CONFIRMA: "CONFIRMA", REFUTA: "REFUTA", NAO_CONFIRMA: "NÃO CONFIRMA",
         LIMITE: "LIMITE"}

ALPHA_INTERIM = 0.0005
ALPHA_FINAL = 0.024  # calibrado em run_design2.py (design2.txt): alfa simulado <= 0,0236 nos 5 cenários
P_REF = 0.9975  # calibrado em calib_pref.py: P(REFUTA | θ=+0,10) <= 0,019 nos 5 cenários
MRE_CONFIRM = 0.05
DELTA = 0.10
MIN_INTERIM = (20, 100)  # (dias com trade, trades) para qualquer rótulo numa intermediária; e >= 5 semanas
MIN_FINAL = (30, 150)
WEEK_OFFSET = 2  # T0 = 2026-10-07, quarta-feira
N = NormalDist()


def tq(p: float, df: np.ndarray) -> np.ndarray:
    """``design.t_quantile`` (exato) vetorizado em gl: calcula uma vez por gl distinto."""
    v = np.asarray(df, dtype=int)
    uniq, inv = np.unique(v, return_inverse=True)
    return np.array([design.t_quantile(p, int(x)) for x in uniq])[inv].reshape(v.shape)


def week_index(n_days: int, *, week_offset: int = WEEK_OFFSET) -> np.ndarray:
    """Semana ISO (segunda a domingo, UTC) de cada dia a partir de T0; ``week_offset`` = dia da semana de T0 (seg = 0)."""
    return (np.arange(n_days) + week_offset) // 7


def stats(c: np.ndarray, s: np.ndarray, *, week_offset: int = WEEK_OFFSET
          ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Média por trade (razão), EP agrupado por SEMANA ISO (CR1) e G = semanas com trade, por linha.

    Semana, não dia: na simulação com choques persistentes (blocos de 5 dias) o EP por dia deixava o alfa em 0,043
    (design2_calib.txt, S5) — perdas coletivas da reversão duram mais de um dia."""
    wk = week_index(c.shape[1], week_offset=week_offset)
    onehot = (wk[:, None] == np.arange(wk.max() + 1)[None, :]).astype(float)
    cw, sw = c @ onehot, s @ onehot
    g = (cw > 0).sum(axis=1)
    n = cw.sum(axis=1)
    m = sw.sum(axis=1) / np.maximum(n, 1)
    resid2 = ((sw - m[:, None] * cw) ** 2).sum(axis=1)
    se = np.sqrt(g / np.maximum(g - 1, 1) * resid2) / np.maximum(n, 1)
    return m, se, g


def _halves_positive(c: np.ndarray, s: np.ndarray, g: np.ndarray) -> np.ndarray:
    active = c > 0
    rank = np.cumsum(active, axis=1)
    first = active & (rank <= np.floor(g / 2)[:, None])  # "antes × a partir da mediana": o dia mediano vai à 2.ª
    second = active & ~first
    m1 = (s * first).sum(axis=1) / np.maximum((c * first).sum(axis=1), 1)
    m2 = (s * second).sum(axis=1) / np.maximum((c * second).sum(axis=1), 1)
    return (m1 > 0) & (m2 > 0)


def decide(c: np.ndarray, s: np.ndarray, t: np.ndarray, *, look: int, coverage_ok: np.ndarray,
           alpha_final: float = ALPHA_FINAL, p_ref: float = P_REF, final_look: int = 2,
           week_offset: int = WEEK_OFFSET) -> np.ndarray:
    final = look == final_look
    m, se, g = stats(c, s, week_offset=week_offset)  # g = semanas com trade (gl = g - 1)
    n = c.sum(axis=1)
    days = (c > 0).sum(axis=1)
    min_d, min_n = MIN_FINAL if final else MIN_INTERIM
    gate = coverage_ok & (days >= min_d) & (n >= min_n) & (g >= 5) & (se > 0)
    alpha = alpha_final if final else ALPHA_INTERIM
    df = np.maximum(g - 1, 1)
    bt = tq(1 - alpha, df)  # = design.t_boundary(Φ⁻¹(1 − α), gl)
    qref = tq(p_ref, df)
    mt = t.sum(axis=1) / np.maximum(n, 1)
    conf = gate & (m / np.where(se > 0, se, np.inf) >= bt) & (m >= MRE_CONFIRM) & _halves_positive(c, s, days) \
        & (mt > 0)
    stop = gate & ~conf & ((m <= 0) | final)
    out = np.full(len(m), CONTINUA)
    out[stop & (m + qref * se < DELTA)] = REFUTA
    out[stop & (m + qref * se >= DELTA)] = NAO_CONFIRMA
    out[conf] = CONFIRMA
    if final:
        out[~gate] = LIMITE
    return out
