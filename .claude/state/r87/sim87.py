"""R87 — a conta semanal das duas pernas da H-028 (emenda de 05/10 15:40Z).

Vaga ligada: q = w ÷ (S_T + F_T/m) unidades à vista compradas e q/m contratos vendidos com margem q·F_T/m (1×).
Capital fixo: lucro retirado e perda reposta toda segunda; retorno semanal = soma dos resultados das vagas − custos.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from engine87 import (
    ALIVE,
    C_PERP,
    C_SPOT,
    DAY_MS,
    MIN_N,
    MMR,
    RECV_TOL,
    Arm,
    Market,
    complete,
    decide,
    guard_ok,
    last_real,
    received,
    seg_of,
    tradeable,
    universe,
)


@dataclass
class Pos:
    q: float
    f_ref: float  # preço do perpétuo no último reajuste
    k0: int
    w0: float
    pnl: float = 0.0


@dataclass
class ArmResult:
    weekly: np.ndarray
    funding: np.ndarray
    basis: np.ndarray
    costs: np.ndarray
    liq_loss: np.ndarray
    unhedged: np.ndarray
    exposure: np.ndarray
    n_t: np.ndarray
    liquidations: int = 0
    mark_fallback: int = 0
    guard_blocked: int = 0
    spot_ends: int = 0
    perp_ends: int = 0
    stuck: int = 0
    funding_missing: int = 0
    slot_weeks: int = 0
    episodes: list[dict] = field(default_factory=list)
    liq_events: list[dict] = field(default_factory=list)  # auditoria
    open_at_end: list[str] = field(default_factory=list)
    by_symbol: dict[str, float] = field(default_factory=dict)
    fund_by_symbol: dict[str, float] = field(default_factory=dict)


def _mark_high(mk: Market, i: int, d: int, res: ArmResult) -> float:
    if np.isfinite(mk.m_high[i, d]):
        return float(mk.m_high[i, d])
    if np.isfinite(mk.f_high[i, d]):
        res.mark_fallback += 1
        return float(mk.f_high[i, d])
    return float("nan")


def week_outcome(mk: Market, i: int, t: int, pos: Pos, bound: str, shift: int, res: ArmResult,
                 c_spot: float, c_perp: float) -> dict:
    p, q, m = mk.p, pos.q, float(mk.mult[i])
    s0, f0 = float(p.open_ff[i, t]), last_real(mk.f_open, i, t)
    margin0 = q * (2.0 * pos.f_ref - f0) / m  # saldo de margem no início da semana
    lo = mk.t_ms(t) + shift
    ev_l = None
    week_hi = np.nanmax(np.where(np.isfinite(mk.m_high[i, t:t + 7]), mk.m_high[i, t:t + 7], mk.f_high[i, t:t + 7]))
    ms, rr = mk.fund_ms[i], mk.fund_rate[i]
    a_, b_ = np.searchsorted(ms, lo, "right"), np.searchsorted(ms, mk.t_ms(t + 7) + shift, "right")
    worst_paid = q * float(np.sum(np.clip(-rr[a_:b_], 0, None))) * (week_hi if np.isfinite(week_hi) else 0.0) / m
    floor_trigger = m * (margin0 - worst_paid + q * f0 / m) / (q * (1.0 + MMR))
    scan = bool(np.isfinite(week_hi) and week_hi >= floor_trigger)
    for d in range(t, t + 7) if scan else ():
        mh = _mark_high(mk, i, d, res)
        if not np.isfinite(mh):
            continue
        bal = margin0 + received(mk, i, q, lo, mk.t_ms(d) + shift, bound)
        if mh >= m * (bal + q * f0 / m) / (q * (1.0 + MMR)):
            ev_l = d
            break
    ev_s = int(p.last[i]) if p.ended[i] and p.last[i] < t + 7 else None
    seg = seg_of(mk, i, t)
    ev_f = seg[1] if seg is not None and seg[2] and seg[1] < t + 7 and seg[1] + ALIVE >= t else None
    out = {"funding": 0.0, "basis": 0.0, "unhedged": 0.0, "cost": 0.0, "liq": 0.0, "closed": False, "kind": "normal"}
    events = [(d, kd) for d, kd in ((ev_l, 0), (ev_s, 1), (ev_f, 2)) if d is not None]

    def spot_leg(end: int | None) -> tuple[float, float]:
        if end is None:
            s1 = float(p.open_ff[i, t + 7])
            return q * (s1 - s0), c_spot * q * s1
        if bound == "pes":
            return -q * s0, 0.0
        sc = last_real(p.close, i, end)
        return q * (sc - s0), c_spot * q * sc

    if not events:
        hi = mk.t_ms(t + 7) + shift
        res.funding_missing += not complete(mk.fund_ms[i], lo, hi)
        s1, f1 = float(p.open_ff[i, t + 7]), last_real(mk.f_open, i, t + 7)
        out["funding"] = received(mk, i, q, lo, hi, bound)
        out["basis"] = q * (s1 - s0) - q * (f1 - f0) / m
        return out
    d1, kind = min(events)
    out["closed"], out["kind"] = True, ("liq", "spot_end", "perp_end")[kind]
    if kind == 0:
        day0 = mk.t_ms(d1) + shift
        fb = received(mk, i, q, lo, day0, bound) + received(mk, i, q, day0, mk.t_ms(d1 + 1) + shift, bound, True)
        res.funding_missing += not complete(mk.fund_ms[i], lo, day0)
        out["funding"], out["liq"] = fb, -margin0 - fb  # a perna perde o saldo inteiro
        out["unhedged"], out["cost"] = spot_leg(ev_s)
        res.liq_events.append({"sym": p.ids[i], "t": t, "day": d1, "f0": f0, "f_ref": pos.f_ref, "s0": s0,
                               "mark_hi": float(mk.m_high[i, d1]), "last_hi": float(mk.f_high[i, d1]),
                               "s1": float(p.open_ff[i, t + 7]), "q": q, "margin0": margin0, "m": m,
                               "net": out["funding"] + out["liq"] + out["unhedged"] - out["cost"]})
        return out
    hi = mk.t_ms(d1 + 1) - RECV_TOL
    res.funding_missing += not complete(mk.fund_ms[i], lo, hi)
    out["funding"] = received(mk, i, q, lo, hi, bound)
    fc = last_real(mk.f_close, i, d1)
    if kind == 2 and bound == "pes":
        fc = max(fc, _mark_high(mk, i, d1, res)) if np.isfinite(_mark_high(mk, i, d1, res)) else fc
    sp, sc = spot_leg(d1 if kind == 1 else ev_s)
    if kind == 1:
        out["basis"] = sp - q * (fc - f0) / m
    else:  # fim do perpétuo: a perna à vista fica descoberta até a saída
        out["basis"], out["unhedged"] = -q * (fc - f0) / m, sp
    out["cost"] = sc + c_perp * q * fc / m
    return out


def simulate_arm(mk: Market, ts: list[int], arm: Arm, bound: str, conv: str = "after", c_spot: float = C_SPOT,
                 c_perp: float = C_PERP) -> ArmResult:
    shift = RECV_TOL if conv == "after" else -RECV_TOL
    n_w = len(ts)
    res = ArmResult(*(np.zeros(n_w) for _ in range(8)))
    pos: dict[int, Pos] = {}

    def close_ep(i: int, k: int, censored: bool = False) -> None:
        ps = pos.pop(i)
        res.episodes.append({"sym": mk.p.ids[i], "k0": ps.k0, "k1": k, "ret": ps.pnl / ps.w0, "censored": censored})

    for k, t in enumerate(ts):
        u = universe(mk, t)
        n = len(u)
        res.n_t[k] = n
        evaluable = n >= MIN_N
        want = decide(mk, t, u, set(pos), arm)
        if not evaluable:
            want &= set(pos)
        cost = 0.0
        stuck = {i for i in pos if not tradeable(mk, i, t)}
        res.stuck += len(stuck)
        stuck_cap = sum(pos[i].q * (float(mk.p.open_ff[i, t]) + (2.0 * pos[i].f_ref - last_real(mk.f_open, i, t))
                                    / mk.mult[i]) for i in stuck)
        for i in sorted(set(pos) - stuck - want):
            c = pos[i].q * (mk.p.open[i, t] * c_spot + mk.f_open[i, t] / mk.mult[i] * c_perp)
            pos[i].pnl -= c
            cost += c
            close_ep(i, k)
        targets = []
        for i in sorted(want - stuck):
            if not tradeable(mk, i, t):
                continue
            if i not in pos and not guard_ok(mk, i, t):
                res.guard_blocked += 1
                continue
            targets.append(i)
        if evaluable and targets:
            w = min(1.0 / n, max(1.0 - stuck_cap, 0.0) / len(targets))
            for i in targets:
                s_t, f_t, m = float(mk.p.open[i, t]), float(mk.f_open[i, t]), float(mk.mult[i])
                if i not in pos:
                    pos[i] = Pos(q=0.0, f_ref=f_t, k0=k, w0=w)
                q_new = w / (s_t * (1.0 + c_spot) + f_t / m * (1.0 + c_perp))
                c = abs(q_new - pos[i].q) * (s_t * c_spot + f_t / m * c_perp)
                pos[i].q, pos[i].f_ref = q_new, f_t
                pos[i].pnl -= c
                cost += c
        res.exposure[k] = sum(ps.q * (float(mk.p.open_ff[i, t]) + last_real(mk.f_open, i, t) / mk.mult[i])
                              for i, ps in pos.items())
        tot = {"funding": 0.0, "basis": 0.0, "unhedged": 0.0, "cost": cost, "liq": 0.0}
        for i in sorted(pos):
            res.slot_weeks += 1
            o = week_outcome(mk, i, t, pos[i], bound, shift, res, c_spot, c_perp)
            for key in ("funding", "basis", "unhedged", "liq", "cost"):
                tot[key] += o[key]
            pnl = o["funding"] + o["basis"] + o["unhedged"] + o["liq"] - o["cost"]
            pos[i].pnl += pnl
            sym = mk.p.ids[i].split("#")[0]
            res.by_symbol[sym] = res.by_symbol.get(sym, 0.0) + pnl
            res.fund_by_symbol[sym] = res.fund_by_symbol.get(sym, 0.0) + o["funding"]
            if o["closed"]:
                res.liquidations += o["kind"] == "liq"
                res.spot_ends += o["kind"] == "spot_end"
                res.perp_ends += o["kind"] == "perp_end"
                close_ep(i, k + 1)
        if k == n_w - 1:  # fim da amostra: as posições abertas pagam a saída das duas pernas na última abertura
            res.open_at_end = sorted(mk.p.ids[i].split("#")[0] for i in pos)
            t1 = t + 7
            for i in sorted(pos):
                c = pos[i].q * (float(mk.p.open_ff[i, t1]) * c_spot + last_real(mk.f_open, i, t1) / mk.mult[i] * c_perp)
                tot["cost"] += c
                pos[i].pnl -= c
                close_ep(i, n_w, censored=True)
        res.funding[k], res.basis[k], res.costs[k], res.liq_loss[k] = tot["funding"], tot["basis"], tot["cost"], tot["liq"]
        res.unhedged[k] = tot["unhedged"]
        res.weekly[k] = tot["funding"] + tot["basis"] + tot["unhedged"] + tot["liq"] - tot["cost"]
    return res


__all__ = ["ArmResult", "DAY_MS", "Pos", "simulate_arm", "week_outcome"]
