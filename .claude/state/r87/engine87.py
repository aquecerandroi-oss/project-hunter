"""R87 — motor da H-028 (com a emenda de 05/10 15:40Z): sinal S7, universo ponto-no-tempo, braços e a conta semanal.

Decisão na segunda T (00:00 UTC) lê só: volume à vista de colunas < T, datas de listagem e liquidações de funding com
fundingTime ≤ T − 1 h. A guarda de entrada lê as aberturas de T (o preço visto ao negociar). Todo o resto (aberturas de
T+7, máximas de marca, fins de série, funding recebido) só entra em `sim87.simulate_arm`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from panel import Panel

DAY_MS = 86_400_000
H_MS = 3_600_000
TOP, MIN_N, MIN_AGE, VOL_WINDOW, ALIVE = 20, 15, 35, 30, 14  # iguais ao R84
C_SPOT, C_PERP = 0.0015, 0.0010  # por lado, sobre o nocional negociado
MMR = 0.05
GUARD = 0.05
MAX_GAP = 9 * H_MS  # janela de funding completa: nenhum intervalo maior que isso
RECV_TOL = 30 * 60_000


@dataclass(frozen=True)
class Arm:
    kind: str  # "always" | "cond"
    enter: float = 0.0
    stay: float = 0.0
    stay_strict: bool = False  # True: fica com S7 > stay; False: S7 ≥ stay


ARMS = {
    "A0": Arm("always"),
    "A1": Arm("cond", enter=0.00125, stay=0.0, stay_strict=True),
    "A2": Arm("cond", enter=0.0065, stay=0.0021, stay_strict=False),
}
PLATEAU = {
    "A1": (Arm("cond", 0.000625, 0.0, True), Arm("cond", 0.0025, 0.0, True)),
    "A2": (Arm("cond", 0.0050, 0.0021, False), Arm("cond", 0.0080, 0.0021, False)),
}


@dataclass
class Market:
    p: Panel  # à vista (R84), colunas = dias UTC
    f_open: np.ndarray  # perpétuo (último negociado) alinhado à série à vista, NaN = sem vela
    f_high: np.ndarray
    f_close: np.ndarray
    mult: np.ndarray  # unidades do contrato por unidade à vista (1, 1e3, 1e6); NaN = sem perpétuo
    perp_segs: list[list[tuple[int, int, bool]]]  # por série: (1.ª col, última col, termina aí)
    fund_ms: list[np.ndarray]
    fund_rate: list[np.ndarray]
    m_open: np.ndarray | None = None  # preço de marca diário (NaN = sem vela de marca)
    m_high: np.ndarray | None = None
    m_low: np.ndarray | None = None
    excluded_syms: frozenset[str] = frozenset()  # só para a leitura de concentração (sem as 3 maiores)
    _seg_cache: dict = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if self.m_open is None:  # testes sintéticos: marca = negociado, faixa do dia = [abertura, máxima]
            self.m_open, self.m_high, self.m_low = self.f_open.copy(), self.f_high.copy(), self.f_open.copy()

    def t_ms(self, t: int) -> int:
        return (self.p.day0 + t) * DAY_MS


def s7(mk: Market, i: int, t: int) -> tuple[float, int]:
    """Soma das liquidações com fundingTime em (T − 7 d − 1 h, T − 1 h] e quantas são."""
    ms, r = mk.fund_ms[i], mk.fund_rate[i]
    hi = mk.t_ms(t) - H_MS
    a, b = np.searchsorted(ms, hi - 7 * DAY_MS, "right"), np.searchsorted(ms, hi, "right")
    return float(r[a:b].sum()), int(b - a)


def complete(ms: np.ndarray, lo: int, hi: int) -> bool:
    """Liquidações em (lo, hi] cobrem a janela: nenhum intervalo > 9 h entre lo, cada liquidação e hi."""
    a, b = np.searchsorted(ms, lo, "right"), np.searchsorted(ms, hi, "right")
    pts = np.concatenate(([lo], ms[a:b], [hi]))
    return bool(np.all(np.diff(pts) <= MAX_GAP))


def s7_complete(mk: Market, i: int, t: int) -> bool:
    hi = mk.t_ms(t) - H_MS
    return complete(mk.fund_ms[i], hi - 7 * DAY_MS, hi)


def seg_of(mk: Market, i: int, col: int) -> tuple[int, int, bool] | None:
    """Segmento do perpétuo que contém a última vela real ≤ col (ou None)."""
    for seg in mk.perp_segs[i]:
        if seg[0] <= col <= seg[1]:
            return seg
    prev = [s for s in mk.perp_segs[i] if s[1] < col]
    return prev[-1] if prev else None


def perp_ok(mk: Market, i: int, t: int) -> bool:
    """Perpétuo listado ≥ 35 d em T − 1 d no segmento corrente e com vela real em [T − 14, T − 1] (só datas)."""
    lo = max(t - ALIVE, 0)
    alive = np.flatnonzero(~np.isnan(mk.f_open[i, lo:t]))
    if alive.size == 0:
        return False
    seg = seg_of(mk, i, lo + int(alive[-1]))
    return seg is not None and seg[0] <= t - 1 - MIN_AGE


def universe(mk: Market, t: int) -> list[int]:
    """Filtra (à vista R84 + perpétuo + janela de funding completa) e depois pega os 20 de maior volume à vista."""
    key = ("u", t)
    if key in mk._seg_cache:
        return mk._seg_cache[key]
    p = mk.p
    lo = max(t - ALIVE, 0)
    alive = np.any(~np.isnan(p.close[:, lo:t]), axis=1)
    listed = (~p.excluded) & (p.first <= t - 1 - MIN_AGE) & alive
    cand = [int(i) for i in np.flatnonzero(listed) if np.isfinite(mk.mult[i]) and perp_ok(mk, i, t)
            and s7_complete(mk, i, t) and p.ids[i].split("#")[0] not in mk.excluded_syms]
    vol = {i: float(np.nansum(p.qvol[i, max(t - VOL_WINDOW, 0): t])) for i in cand}
    out = sorted(cand, key=lambda i: (-vol[i], p.ids[i]))[:TOP]
    mk._seg_cache[key] = out
    return out


def tradeable(mk: Market, i: int, t: int) -> bool:
    return bool(np.isfinite(mk.p.open[i, t]) and np.isfinite(mk.f_open[i, t]))


def guard_ok(mk: Market, i: int, t: int) -> bool:
    return abs(mk.f_open[i, t] / (mk.mult[i] * mk.p.open[i, t]) - 1.0) <= GUARD


def decide(mk: Market, t: int, u: list[int], on_prev: set[int], arm: Arm) -> set[int]:
    """Vagas que querem estar ligadas em T (antes de travas de negociação e da guarda de entrada)."""
    on: set[int] = set()
    for i in u:
        if arm.kind == "always":
            on.add(i)
            continue
        v = s7(mk, i, t)[0]
        if i in on_prev:
            if (v > arm.stay) if arm.stay_strict else (v >= arm.stay):
                on.add(i)
        elif v >= arm.enter:
            on.add(i)
    return on


def last_real(a: np.ndarray, i: int, c: int) -> float:
    ok = np.flatnonzero(~np.isnan(a[i, : c + 1]))
    return float(a[i, ok[-1]]) if ok.size else float("nan")


def received(mk: Market, i: int, q: float, lo_ms: int, hi_ms: int, bound: str, only_negative: bool = False) -> float:
    """Funding do vendido de q unidades nas liquidações com fundingTime em (lo, hi].

    F̂: 00:00 → abertura de marca do dia; outras → extremo da faixa de marca do dia, adverso no pessimista e
    favorável no otimista (sem marca no dia: a última abertura real de marca/negociado)."""
    ms, r = mk.fund_ms[i], mk.fund_rate[i]
    a, b = np.searchsorted(ms, lo_ms, "right"), np.searchsorted(ms, hi_ms, "right")
    tot = 0.0
    for k in range(a, b):
        rate = float(r[k])
        if only_negative and rate >= 0:
            continue
        c = int(ms[k] // DAY_MS - mk.p.day0)
        at_midnight = (ms[k] % DAY_MS) <= RECV_TOL
        lo_p, hi_p, op = mk.m_low[i, c], mk.m_high[i, c], mk.m_open[i, c]
        if at_midnight and np.isfinite(op):
            f = float(op)
        elif np.isfinite(lo_p) and np.isfinite(hi_p):
            adverse_low = rate > 0  # vendido recebe r·F: F baixo é o adverso quando r > 0
            f = float(lo_p if (adverse_low == (bound == "pes")) else hi_p)
        else:
            f = last_real(mk.m_open, i, c)
            if not np.isfinite(f):
                f = last_real(mk.f_open, i, c)
        tot += rate * f
    return q * tot / float(mk.mult[i])
